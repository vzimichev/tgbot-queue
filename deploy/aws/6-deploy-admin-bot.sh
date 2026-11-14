#!/usr/bin/env bash
# Run locally to deploy a published GitHub branch to the step-5 EC2 instance.
set -euo pipefail

# Step 1: Choose the existing AWS infrastructure to deploy to.
region=${AWS_REGION:-eu-central-1}
worker_stack=${WORKER_STACK:-tgbot-queue-admin-worker}
gateway_stack=${GATEWAY_STACK:-tgbot-queue-gateway}
# Ask which published branch to deploy; Enter selects the local branch.
if [[ $# -ne 0 ]]; then
  echo 'Usage: 6-deploy-admin-bot.sh' >&2
  exit 1
fi
repo=$(cd "$(dirname "$0")/../.." && pwd)
current_branch=$(git -C "$repo" branch --show-current)
read -r -p "Git branch${current_branch:+ [$current_branch]}: " branch
branch=${branch:-$current_branch}
if [[ -z "$branch" ]] || ! git check-ref-format --branch "$branch" >/dev/null 2>&1; then
  echo 'Enter a valid Git branch.' >&2
  exit 1
fi
# Step 3: Prepare temporary deployment files and clean them up on exit.
repo=$(cd "$(dirname "$0")/../.." && pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# Step 4: Read AWS stack outputs to connect the app to the existing infrastructure.
aws cloudformation describe-stacks --region "$region" --stack-name "$worker_stack" > "$tmp/worker.json"
aws cloudformation describe-stacks --region "$region" --stack-name "$gateway_stack" > "$tmp/gateway.json"
python3 - "$tmp" "$region" <<'PY'
import json
import pathlib
import re
import sys

root = pathlib.Path(sys.argv[1])
stack = json.loads((root / 'worker.json').read_text())['Stacks'][0]
if stack['StackStatus'] not in ('CREATE_COMPLETE', 'UPDATE_COMPLETE'):
    raise SystemExit('Worker stack must be CREATE_COMPLETE or UPDATE_COMPLETE.')
outputs = {o['OutputKey']: o['OutputValue'] for o in stack['Outputs']}
gateway = json.loads((root / 'gateway.json').read_text())['Stacks'][0]
url = next(o['OutputValue'] for o in gateway['Outputs'] if o['OutputKey'] == 'WebhookUrl')
if not re.fullmatch(r'https://[a-zA-Z0-9.-]+/webhook', url):
    raise SystemExit('Unexpected gateway webhook URL.')
instance = outputs['InstanceId']
volume = outputs['DataVolumeId']
if not re.fullmatch(r'i-[0-9a-f]+', instance) or not re.fullmatch(r'vol-[0-9a-f]+', volume):
    raise SystemExit('Unexpected instance ID or EBS volume ID.')
queue = outputs['QueueUrl']
config = {
    'AWS_DEFAULT_REGION': sys.argv[2], 'SQS_REGION': sys.argv[2],
    'CELERY_BROKER': 'sqs', 'SQS_QUEUE_URL': queue,
    'SQS_QUEUE_NAME': queue.rsplit('/', 1)[-1],
    'ADMIN_BOT_CHILD_WEBHOOK_URL': url + '/managed',
    'ADMIN_BOT_SECRET_ARN': outputs['AdminBotSecretArn'],
    'WEBHOOK_SECRET_ARN': outputs['WebhookSecretArn'],
}
(root / 'runtime.json').write_text(json.dumps(config))
(root / 'instance').write_text(instance)
(root / 'volume').write_text(volume)

PY
instance=$(cat "$tmp/instance")
volume=$(cat "$tmp/volume")
# Deploy directly through SSM; no application archive is uploaded.
python3 - "$tmp" "$region" "$instance" "$volume" "$branch" <<'DEPLOY_PY'
import base64
import json
from pathlib import Path
import shlex
import subprocess
import sys
import time


def main():
    temporary, region, instance, volume, branch = sys.argv[1:]
    config = base64.b64encode((Path(temporary) / 'runtime.json').read_bytes()).decode()
    remote = r"""set -euo pipefail
install -d -m 0755 /opt/admin-bot
exec 9>/opt/admin-bot/deploy.lock
flock -n 9 || { echo 'Another deployment is running.' >&2; exit 1; }
echo 'Installing Git and Docker Compose...'
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq git docker.io docker-compose-v2
systemctl enable --now docker
mountpoint -q /var/lib/admin-bot || { echo 'Mount the database disk at /var/lib/admin-bot first.' >&2; exit 1; }
serial=$(lsblk -dn -o SERIAL "$(findmnt -n -o SOURCE --target /var/lib/admin-bot)")
[[ "$serial" == "${volume//-/}" ]] || { echo 'Unexpected database disk; refusing to deploy.' >&2; exit 1; }
install -d -m 0755 /opt/admin-bot
install -d -m 0700 /var/lib/admin-bot/db
cd /opt/admin-bot
cat > start.py <<'START_PY'
import json
import os
from pathlib import Path
import sys

import boto3

config = json.loads(Path('/run/admin-bot/config.json').read_text())
os.environ.update(config)
try:
    client = boto3.client('secretsmanager')
    admin = json.loads(client.get_secret_value(SecretId=config['ADMIN_BOT_SECRET_ARN'])['SecretString'])
    token = admin['ADMIN_BOT_TOKEN']
    owner = admin['ADMIN_BOT_OWNER_ID']
    if isinstance(owner, bool) or not isinstance(owner, (str, int)):
        raise ValueError('Invalid owner ID type')
    owner = str(owner)
    if not owner.isascii() or not owner.isdecimal() or int(owner) <= 0:
        raise ValueError('Owner ID must be a positive integer')
    secret = client.get_secret_value(SecretId=config['WEBHOOK_SECRET_ARN'])['SecretString']
    if not isinstance(token, str) or not token or not secret or token.startswith('REPLACE_ME') or secret.startswith('REPLACE_ME'):
        raise ValueError('Secret is empty or still a placeholder')
except Exception:
    sys.exit('Unable to load valid worker secrets from Secrets Manager')
os.environ.update(ADMIN_BOT_TOKEN=token, TELEGRAM_TOKEN=token,
                  ADMIN_BOT_OWNER_ID=owner, WEBHOOK_SECRET_TOKEN=secret)
if sys.argv[1:] == ['--check']:
    boto3.client('sqs').get_queue_attributes(
        QueueUrl=config['SQS_QUEUE_URL'], AttributeNames=['VisibilityTimeout'])
    sys.exit(0)
os.execvp(sys.executable, [sys.executable, '-m', 'bot_factories.admin_bot.json_worker'])
START_PY
cd /opt/admin-bot
mountpoint -q /var/lib/admin-bot || { echo 'Database disk is not mounted.' >&2; exit 1; }
echo "Downloading GitHub version: $ref"
if [[ ! -d repo/.git ]]; then
  git clone --no-checkout https://github.com/vzimichev/tgbot-queue.git repo
fi
git -C repo fetch --depth=1 https://github.com/vzimichev/tgbot-queue.git "refs/heads/$ref"
release=$(git -C repo rev-parse --verify "FETCH_HEAD^{commit}")
echo "Selected branch: $ref; Git commit: $release"
mkdir -p /opt/admin-bot/releases
source_dir=$(mktemp -d "/opt/admin-bot/releases/$release.XXXXXX")
git -C repo archive "$release" | tar -x -C "$source_dir"
export ADMIN_BOT_SOURCE="$source_dir" ADMIN_BOT_RELEASE="$release"
cat > compose.yaml <<'YAML'
name: admin-bot-aws
services:
  worker:
    image: admin-bot:${ADMIN_BOT_RELEASE:?}
    build:
      context: ${ADMIN_BOT_SOURCE:?}
      dockerfile: bot_factories/admin_bot/Dockerfile
    container_name: admin-bot-worker
    restart: unless-stopped
    entrypoint: [python, /run/admin-bot/start.py]
    volumes:
      - /var/lib/admin-bot/db:/app/bot_factories/admin_bot/.cache
      - /opt/admin-bot/runtime.json:/run/admin-bot/config.json:ro
      - /opt/admin-bot/start.py:/run/admin-bot/start.py:ro
    logging:
      driver: json-file
      options:
        max-size: 10m
        max-file: '3'
YAML
echo 'Stopping admin bot (downtime starts)...'
if systemctl cat admin-bot.service >/dev/null 2>&1; then
  systemctl disable --now admin-bot.service
fi
docker compose down
echo 'Building application image...'
docker compose build
expected_image=$(docker image inspect --format '{{.Id}}' "admin-bot:$release")
echo 'Checking secrets and SQS access...'
docker compose run --interactive=false -T --rm --no-deps worker --check
echo 'Starting admin bot...'
docker compose up -d --no-build --force-recreate
echo 'Waiting for JSON worker readiness...'
for attempt in $(seq 1 30); do
  actual_image=$(docker inspect --format '{{.Image}}' admin-bot-worker)
  [[ "$actual_image" == "$expected_image" ]] || { echo 'Container image differs from the built image.' >&2; exit 1; }
  state=$(docker inspect --format '{{.State.Status}} {{.RestartCount}}' admin-bot-worker)
  [[ "$state" == 'running 0' ]] || { echo "Worker failed startup: $state" >&2; exit 1; }
  if docker logs admin-bot-worker > worker-startup.log 2>&1 && grep -q 'Admin JSON worker ready\.' worker-startup.log; then
    echo "DEPLOY_OK commit=$release image=$actual_image"
    exit 0
  fi
  sleep 2
done
echo 'Worker did not become ready. Inspect: cd /opt/admin-bot && docker compose logs' >&2
exit 1
"""
    # Only non-secret configuration is sent through SSM.
    prefix = f'ref={shlex.quote(branch)}\nvolume={shlex.quote(volume)}\n'
    insert = f'umask 077; echo {config} | base64 -d > /opt/admin-bot/runtime.json\n'
    remote = prefix + remote.replace("cat > start.py", insert + "cat > start.py", 1)
    online = aws(region, 'describe-instance-information', '--filters', f'Key=InstanceIds,Values={instance}')
    if not any(item['PingStatus'] == 'Online' for item in online['InstanceInformationList']):
        raise SystemExit('Worker must be Online in SSM before deployment.')
    response = aws(region, 'send-command', '--instance-ids', instance,
                   '--document-name', 'AWS-RunShellScript', '--parameters',
                   json.dumps({'commands': ["bash -s <<'ADMIN_DEPLOY'\n" + remote + '\nADMIN_DEPLOY'],
                               'executionTimeout': ['3600']}))
    command_id = response['Command']['CommandId']
    print(f'Deploying {branch} on {instance}...', flush=True)
    deadline = time.monotonic() + 4200
    shown = ''
    while time.monotonic() < deadline:
        result = aws(region, 'get-command-invocation', '--command-id', command_id, '--instance-id', instance)
        if result:
            output = result.get('StandardOutputContent', '')
            if output.startswith(shown):
                print(output[len(shown):], end='', flush=True)
            shown = output
            if result['Status'] == 'Success':
                if not any(line.startswith('DEPLOY_OK commit=') for line in output.splitlines()):
                    raise SystemExit(f'Deployment did not confirm worker readiness. SSM command: {command_id}')
                print('Deployment complete. Verify the Telegram flow separately.')
                return
            if result['Status'] not in ('Pending', 'InProgress', 'Delayed'):
                print(result.get('StandardErrorContent', ''), file=sys.stderr)
                raise SystemExit(f"Deployment failed: {result['Status']}. SSM command: {command_id}")
        time.sleep(2)
    raise SystemExit(f'SSM command still running: {command_id}. Inspect it before retrying.')


def aws(region, *args):
    result = subprocess.run(['aws', 'ssm', *args, '--region', region, '--output', 'json', '--no-cli-pager'],
                            capture_output=True, text=True)
    if result.returncode:
        if 'InvocationDoesNotExist' in result.stderr:
            return None
        raise SystemExit(f'SSM {args[0]} failed; check credentials and permissions.')
    return json.loads(result.stdout)


if __name__ == '__main__':
    main()
DEPLOY_PY
