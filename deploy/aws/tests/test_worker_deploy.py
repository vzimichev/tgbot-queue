"""Exercise local deployment orchestration without AWS or an SSH server."""
import ast
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import Mock, patch
import types


SCRIPT = Path(__file__).resolve().parents[1] / '6-deploy-admin-bot.sh'


class WorkerDeployTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / 'repo'
        target = self.repo / 'deploy/aws/6-deploy-admin-bot.sh'
        target.parent.mkdir(parents=True)
        shutil.copy2(SCRIPT, target)
        subprocess.run(['git', 'init', '-q', '-b', 'test-branch', str(self.repo)], check=True)
        commands = self.root / 'bin'
        commands.mkdir()
        fake = commands / 'fake'
        fake.write_text('''#!/usr/bin/env python3
import base64, json, os, pathlib, re, sys
root = pathlib.Path(os.environ['MOCK_ROOT'])
args = sys.argv
if 'cloudformation' in args:
    if 'tgbot-queue-admin-worker' in args:
        values = {'InstanceId': 'i-abcdef', 'DataVolumeId': 'vol-abcdef',
                  'QueueUrl': 'https://sqs.eu-central-1.amazonaws.com/123/updates',
                  'AdminBotSecretArn': 'arn:admin', 'WebhookSecretArn': 'arn:webhook'}
        print(json.dumps({'Stacks': [{'StackStatus': os.environ.get('MOCK_STATUS', 'CREATE_COMPLETE'),
              'Outputs': [{'OutputKey': k, 'OutputValue': v} for k, v in values.items()]}]}))
    else:
        print(json.dumps({'Stacks': [{'Outputs': [{'OutputKey': 'WebhookUrl',
              'OutputValue': 'https://example.execute-api.eu-central-1.amazonaws.com/webhook'}]}]}))
elif 'describe-instance-information' in args:
    print(json.dumps({'InstanceInformationList': [{'PingStatus': os.environ.get('MOCK_SSM', 'Online')}]}))
elif 'send-command' in args:
    command = json.loads(args[args.index('--parameters') + 1])['commands'][0]
    log = root / 'ssm_calls'
    count = int(log.read_text()) + 1 if log.exists() else 1
    log.write_text(str(count))
    (root / 'command').write_text(command)
    if "printf '%s'" in command:
        chunk = command.split("'", 4)[3]
        offset = int(re.search(r'seek=(\\d+)', command).group(1))
        path = root / 'upload.b64'
        with open(path, 'r+b' if path.exists() else 'wb') as stream:
            stream.seek(offset); stream.write(chunk.encode())
    if command.startswith('set -e; base64'):
        (root / 'upload.tgz').write_bytes(base64.b64decode((root / 'upload.b64').read_bytes()))
        (root / 'deployment_command').write_text(command)
    print(json.dumps({'Command': {'CommandId': 'command-' + str(count)}}))
elif 'get-command-invocation' in args:
    command = (root / 'command').read_text()
    status = 'Failed' if os.environ.get('MOCK_FAILURE') else 'Success'
    output = '' if os.environ.get('MOCK_NO_READY') else 'DEPLOY_OK commit=abc image=sha256:abc\\n'
    print(json.dumps({'Status': status, 'StandardOutputContent': output}))
else:
    sys.exit('Unexpected AWS command: ' + str(args))
''')
        fake.chmod(0o755)
        (commands / 'aws').symlink_to(fake)
        self.env = dict(os.environ, PATH=str(commands) + ':' + os.environ['PATH'],
                        MOCK_ROOT=str(self.root))
        self.script = target

    def run_script(self, *args, input_text=None):
        return subprocess.run(['bash', str(self.script), *args], env=self.env,
                              capture_output=True, text=True, input='\n' if input_text is None else input_text)

    def test_enter_deploys_current_branch_in_one_command(self):
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        command = (self.root / 'command').read_text()
        self.assertIn('ref=test-branch', command)
        self.assertIn('https://github.com/vzimichev/tgbot-queue.git', command)
        self.assertIn('docker compose up -d', command)
        self.assertIn('apt-get install -y -qq git docker.io docker-compose-v2', command)
        self.assertLess(command.index('apt-get install'), command.index('docker compose build'))
        self.assertEqual((self.root / 'ssm_calls').read_text(), '1')
        subprocess.run(['bash', '-n'], input=command, text=True, check=True)

    def test_success_without_readiness_is_rejected(self):
        self.env['MOCK_NO_READY'] = '1'
        result = self.run_script()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('did not confirm worker readiness', result.stderr)

    def test_downtime_order_and_release_verification(self):
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        command = (self.root / 'command').read_text()
        steps = ['git -C repo fetch', 'git -C repo archive', 'docker compose down',
                 'docker compose build', 'docker compose run --interactive=false -T',
                 'docker compose up -d', 'actual_image=$(docker inspect', 'DEPLOY_OK commit=']
        positions = [command.index(step) for step in steps]
        self.assertEqual(positions, sorted(positions))
        self.assertIn('FETCH_HEAD^{commit}', command)
        self.assertIn('mktemp -d "/opt/admin-bot/releases/$release.XXXXXX"', command)
        self.assertIn('"$actual_image" == "$expected_image"', command)
        self.assertIn('flock -n 9', command)

    def test_explicit_branch_overrides_current_branch(self):
        result = self.run_script(input_text='feature/deploy\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('ref=feature/deploy', (self.root / 'command').read_text())

    def test_invalid_branch_never_sends_command(self):
        result = self.run_script(input_text='--bad\n')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.root / 'ssm_calls').exists())

    def test_offline_ssm_never_sends_commands(self):
        self.env['MOCK_SSM'] = 'ConnectionLost'
        result = self.run_script()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.root / 'ssm_calls').exists())

    def test_failed_command_stops_deployment(self):
        self.env['MOCK_FAILURE'] = '1'
        result = self.run_script()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.root / 'ssm_calls').read_text(), '1')
        self.assertIn('command-1', result.stderr)

    def test_incomplete_stack_never_sends_commands(self):
        self.env['MOCK_STATUS'] = 'CREATE_IN_PROGRESS'
        result = self.run_script()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.root / 'ssm_calls').exists())

    def test_arguments_are_rejected_before_aws(self):
        result = self.run_script('0')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.root / 'ssm_calls').exists())


class WorkerSecretTests(unittest.TestCase):
    def run_entrypoint(self, admin, check=True):
        code = SCRIPT.read_text().split("<<'DEPLOY_PY'\n", 1)[1].split('\nDEPLOY_PY\n', 1)[0]
        tree = ast.parse(code)
        node = next(n for n in ast.walk(tree) if isinstance(n, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == 'remote' for t in n.targets))
        remote = ast.literal_eval(node.value)
        entrypoint = remote.split("<<'START_PY'\n", 1)[1].split('\nSTART_PY\n', 1)[0]
        config = {'ADMIN_BOT_SECRET_ARN': 'arn:admin', 'WEBHOOK_SECRET_ARN': 'arn:webhook',
                  'SQS_QUEUE_URL': 'https://example/queue'}
        secrets = Mock()
        secrets.get_secret_value.side_effect = lambda **kwargs: {
            'SecretString': admin if kwargs['SecretId'] == 'arn:admin' else 'webhook-value'}
        sqs = Mock()
        boto = types.SimpleNamespace(client=lambda name: secrets if name == 'secretsmanager' else sqs)
        with patch.dict('sys.modules', boto3=boto), patch.dict(os.environ, {}, clear=True), \
                patch('pathlib.Path.read_text', return_value=json.dumps(config)), \
                patch('sys.argv', ['start.py'] + (['--check'] if check else [])), \
                patch('os.execvp', side_effect=lambda *args: (_ for _ in ()).throw(SystemExit(0))) as execute:
            with self.assertRaises(SystemExit) as stopped:
                exec(compile(entrypoint, 'start.py', 'exec'), {})
            result = (stopped.exception.code, dict(os.environ), sqs, execute.called)
        return result

    def test_json_identity_is_loaded_on_start(self):
        for owner in (12345, '12345'):
            with self.subTest(owner=owner):
                code, env, sqs, executed = self.run_entrypoint(json.dumps({
                    'ADMIN_BOT_TOKEN': 'test-token', 'ADMIN_BOT_OWNER_ID': owner}), check=False)
                self.assertEqual(code, 0)
                self.assertEqual(env['ADMIN_BOT_OWNER_ID'], '12345')
                self.assertEqual(env['TELEGRAM_TOKEN'], 'test-token')
                self.assertTrue(executed)
                sqs.get_queue_attributes.assert_not_called()

    def test_check_validates_same_secret_without_starting_worker(self):
        code, env, sqs, executed = self.run_entrypoint(json.dumps({
            'ADMIN_BOT_TOKEN': 'test-token', 'ADMIN_BOT_OWNER_ID': 42}))
        self.assertEqual(code, 0)
        self.assertFalse(executed)
        sqs.get_queue_attributes.assert_called_once()

    def test_invalid_secrets_fail_without_leaking_values(self):
        invalid = ['private-token', '{}', json.dumps({'ADMIN_BOT_TOKEN': 'private-token'})]
        for owner in (0, -1, True, 1.5, 'abc', '', None):
            invalid.append(json.dumps({'ADMIN_BOT_TOKEN': 'private-token', 'ADMIN_BOT_OWNER_ID': owner}))
        for token in ('', 'REPLACE_ME_TOKEN', 42, None):
            invalid.append(json.dumps({'ADMIN_BOT_TOKEN': token, 'ADMIN_BOT_OWNER_ID': 42}))
        for secret in invalid:
            with self.subTest(secret=secret):
                code, env, sqs, executed = self.run_entrypoint(secret)
                self.assertEqual(code, 'Unable to load valid worker secrets from Secrets Manager')
                self.assertNotIn('private-token', str(code))
                self.assertFalse(executed)
                sqs.get_queue_attributes.assert_not_called()


if __name__ == '__main__':
    unittest.main()
