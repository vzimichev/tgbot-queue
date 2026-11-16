---
name: tgbot-queue-aws-deploy
description: Deploy or update tgbot-queue on AWS using its deploy/aws CloudFormation templates and worker script, including preflight, Telegram cutover, runtime verification and recovery. Use for this repository, not generic AWS deployments.
---

# Deploy tgbot-queue to AWS

## Scope and discovery

Locate the tgbot-queue checkout from the active workspace or ask for its path. Read applicable AGENTS.md, README.md (AWS sections), deploy/aws/MIGRATION_PLAN.md, current templates 1–5, script 6 and relevant application contracts. Read source before trusting dated migration notes: the current templates supersede historical build instructions. Do not require CodeBuild, SAM or a ZIP build when the current Lambda uses inline code.

Support inspection, first deployment, update, verification and recovery according to the user's request. Creating this skill does not authorize deployment. Treat “можно” as a question. Preserve existing execution authorization; ask only for missing decisions or authorization outside that scope. Never commit without an explicit instruction.

The intended flow is Telegram → HTTP API Gateway → Lambda → SQS → one EC2 Celery worker → admin/managed bot handlers and SQLite. Reuse the existing CloudFormation and shell workflow. Do not introduce Terraform, ECS, new dependencies or infrastructure architecture without approval. Prefer this skill over a new orchestration tool while deployment contracts are evolving.

## Preflight and concrete plan

Inspect git status and identify exactly which local source will be deployed, including uncommitted changes. Do not overwrite unrelated work. Confirm AWS CLI identity with sts get-caller-identity, explicit profile if used, account and region (repository default eu-central-1). Inspect existing stacks and outputs before creating anything. Never assume historical resource IDs still apply.

Resolve these inputs from current configuration or ask one important question at a time:

- AWS account, region, ProjectName and stack names; ProjectName controls cross-stack exports.
- Existing plain-SecretString admin token and webhook secret ARNs; Lambda and worker must share the webhook root secret. Do not accept JSON secrets where plaintext is expected. Reject placeholders before live use.
- Existing EC2 key pair name, readable local private key path and numeric admin Telegram owner ID.
- Initial deployment versus update, old worker location and intended cutover. Preserve existing SQLite on updates; a fresh database is only for an explicitly agreed initial migration.

Check local aws, curl, python3, tar and ssh availability and credentials lifetime. Check relevant IAM permissions and any customer-managed secret KMS decrypt requirements. Do not print credentials, tokens, secret values, full environment dumps or secret-bearing URLs. Do not enable shell tracing around secrets.

Present a short concrete plan with existing/new resources, source identity, state impact, expected interruption and rollback limits. Name unresolved blockers. Creating paid resources and changing the active Telegram webhook must be within the user's authorized scope. If approval remains necessary, first prepare and validate all local work so the approval concerns concrete actions. Work in small verifiable increments with checkpoints as required by repository instructions.

## Mandatory contract gate

Trace the actual producer and consumer before deploying or switching traffic. An HTTP 200 and an active worker do not establish compatibility.

- Verify SQS payload serialization and routing against worker/celery_factory.py and admin tasks. Raw Telegram JSON is not a Celery task envelope. For admin updates, establish delivery to telegram.process_update with the expected arguments; for managed updates, establish delivery to managed_bot.updates with bot ID and update arguments.
- Verify admin /webhook and managed /webhook/managed/{bot_id} routes, Lambda dispatch, invocation permissions and secret/HMAC conventions against the application. An allowed_updates entry named managed_bot does not create a managed webhook route.
- At skill creation, 2-lambda-stack.yaml publishes raw JSON while the worker consumes Celery tasks, and 3-gateway-stack.yaml exposes only the admin route. Recheck these facts each run. If still present, report that full application deployment is blocked and propose the smallest repair as a separate increment; do not silently change architecture or register a live webhook into the incompatible flow.
- Check handling time against SQS visibility timeout and current acknowledgement/retry behavior. Do not claim exactly-once delivery or handler-exception retries without evidence.

## Deployment sequence

Use current template parameters and outputs; the following is dependency order, not permission to recreate existing resources.

1. Validate current CloudFormation templates using AWS validate-template when authorized for read-only access, and run relevant local tests available in this checkout. Review a change set for replacements, retained volumes, IAM and import/export changes before applying updates. CloudFormation validation does not validate runtime behavior.
2. Deploy/reconcile deploy/aws/1-sqs-stack.yaml. Record QueueUrl, QueueArn and DLQ outputs. Never purge or consume production messages as a diagnostic shortcut.
3. Deploy/reconcile deploy/aws/2-lambda-stack.yaml with matching ProjectName, existing webhook secret ARN and correct FunctionName. Detect name collisions rather than deleting existing functions. Use CAPABILITY_IAM where required. Verify completion and Lambda state, configuration and logs without exposing secrets.
4. Deploy/reconcile deploy/aws/3-gateway-stack.yaml with matching ProjectName. Resolve WebhookUrl from outputs and verify integration and permission. Missing/wrong secret should return 403 without publication. Synthetic authorized publication is a side effect: use an isolated test queue or an explicitly agreed harmless update and prove worker consumption.
5. Deploy/reconcile deploy/aws/5-admin-bot-worker.yaml with matching ProjectName, KeyName and both secret ARNs. Record InstanceId, PublicIp, DataVolumeId and WorkerSecurityGroupId. Wait for instance/bootstrap readiness. Inspect the current template for SSM and SSH behavior rather than repeating obsolete migration decisions.
6. Before first production worker start, ensure the old worker has been stopped under the agreed cutover. Script 6 starts/restarts the new service and cannot stop other hosts. Run locally:

   ```sh
   AWS_REGION="$region" WORKER_STACK="$worker_stack" GATEWAY_STACK="$gateway_stack" \
     ./deploy/aws/6-deploy-admin-bot.sh "$ssh_key_path" "$admin_owner_id"
   ```

   The script temporarily opens SSH to the current public IPv4 /32 and removes its own rule on exit; verify cleanup after failures or interruption. Keep SSH host-key checking enabled. If a new host key needs operator verification, hand off that interaction rather than bypassing it. Confirm EBS identity and preserve existing SQLite. Retained EBS is not a backup and a recreated stack does not automatically reattach it.
7. Only after the contract gate and worker verification, register the admin webhook using deploy/aws/4-register-webhook.sh or a narrowly scoped secure equivalent. Inspect the current script first: its prompts may echo tokens and curl arguments can expose them to process inspection. Use a protected transient input mechanism when automating, never put secrets into tool-call text or logs, and clean up temporary secret material. Check Telegram JSON ok=true as well as HTTP status; do not drop pending updates without explicit authorization.
8. Call getWebhookInfo securely; compare URL and allowed updates and inspect pending/error state. Managed webhook registration follows the application's activation flow. Do not overwrite or delete old managed webhook registrations without the agreed migration scope.

## Verification and recovery

Verify admin command response, managed bot creation/activation, balance query and approved test top-up/video flows. Financial mutations need an agreed test bot/account. Verify repeated-update debit behavior, worker restart and SQLite persistence when those checks are authorized. If user interaction is needed, state the exact action and keep the result pending rather than declaring success.

Inspect service/container readiness, logs, queue/DLQ metrics and Lambda/API errors. Do not log message bodies or bot tokens. Worker readiness means SQS connection only. Distinguish tests passed, infrastructure ready, webhook switched and end-to-end verified in the final report. Alarm resources without notification actions do not provide operator notifications.

On failure, stop at the failed stage, inspect CloudFormation events or bounded relevant logs, and preserve successful resources and data. Do not repeatedly launch paid builds or retry unchanged deployment failures. Fix a demonstrated cause before retrying within authorization.

Record the prior webhook URL/configuration and worker release before cutover, without secrets. Recovery may require restoring the prior webhook and starting the old worker only after stopping the new one. Check queue payload compatibility before rollback. Do not promise automatic rollback: worker build inputs may be mutable, database changes may be incompatible, and the current script does not provide a complete rollback command. Never delete stacks, retained data, queues or the old server as implicit cleanup.

Report account/region, stack statuses, public endpoint, source/release identity, checks actually performed, blockers and next action. Update MIGRATION_PLAN.md with verified non-secret results when deployment work changes its state. Never mark full deployment complete while contract or end-to-end checks remain unresolved.
