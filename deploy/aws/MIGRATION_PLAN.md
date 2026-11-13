# AWS migration: current status and remaining work

Last updated: 2026-11-13. This file describes the current repository and the
previously recorded deployment evidence; it is not a live AWS inventory.
Deployment commands are in [README.md](../../README.md).
[flow.mmd](flow.mmd) remains the target architecture, including components
that are not implemented yet.

## Current decisions

- Use CloudFormation in `eu-central-1` and API Gateway's HTTPS domain.
- Keep admin and managed ingress separate: each has its own HTTP API, inline
  Python Lambda, SQS queue and DLQ. No SAM, Lambda ZIP build or CodeBuild is
  needed by the current templates.
- Admin management consumes raw Telegram JSON sequentially through aiogram.
  Celery remains available for execution tasks and the alternative gateway.
- Keep admin/managed bot records, tokens, invitations and limits in SQLite on
  the EC2 worker's separate encrypted data disk.
- Read the admin token/owner ID and webhook root secret from Secrets Manager.
  The admin secret is JSON; the webhook secret is plaintext. Managed bot
  tokens remain in SQLite; managed webhook secrets derive from the root.
- Admin EC2 administration and deployment use Session Manager/SSM Run Command.
  No inbound security group rules are required. A key pair is still a required
  template parameter, but the deployment script does not use SSH.
- Deploy a published GitHub branch, resolving it to a commit at fetch time.
  Stop the previous worker before building; downtime is intentional. Failed
  builds leave it stopped. There is no automatic rollback.
- No automated database backup is configured. Retaining a disk is not a backup.
  Do not delete old infrastructure/data or run competing workers implicitly.

## Implemented in the repository

| Step | File | Responsibility |
| --- | --- | --- |
| 1 | `1-sqs-stack.yaml` | Admin SQS/DLQ, retention and DLQ alarm |
| 2 | `2-lambda-stack.yaml` | Inline admin Lambda, secret/queue permissions, logs and alarm |
| 3 | `3-gateway-stack.yaml` | Admin HTTP API: `POST /webhook` |
| 4 | `4-register-webhook.sh` | Register admin webhook from stack output and supplied credentials |
| 5 | `5-admin-bot-worker.yaml` | EC2, networking, SSM, IAM and persistent EBS volume |
| 6 | `6-deploy-admin-bot.sh` | Fetch published branch, build and start admin JSON worker over SSM |
| 7 | `7-managed-sqs-stack.yaml` | Separate managed SQS/DLQ |
| 8 | `8-managed-lambda-stack.yaml` | Inline managed Lambda with per-bot secret validation |
| 9 | `9-managed-gateway-stack.yaml` | Separate `POST /webhook/managed/{bot_id}` API |

Admin ingress publishes the original Telegram update as raw JSON. The admin
consumer (`bot_factories/admin_bot/json_worker.py`) validates a JSON object
with an integer `update_id`, dispatches it to aiogram and deletes the message
only after successful handling. Errors leave it for retry; no visibility
extension or exactly-once delivery is implemented.

Managed ingress publishes `{"bot_id": 123, "update": {"update_id": 456, ...}}`.
The admin JSON consumer cannot consume this envelope. The managed consumer,
its worker permissions/configuration and processing-task publication are
unfinished. Existing Celery managed handlers do not fill that gap automatically.

Step 6 validates the mounted disk against the stack's volume ID, fetches a
branch into a fresh source directory, locks concurrent deployments, stops the
old worker, builds, checks Secrets Manager/SQS access and starts the container.
Success requires the expected image, a running container without startup
restarts and the `Admin JSON worker ready.` message. The output records commit
and image IDs; it does not certify Telegram behavior.

## Previously recorded deployment evidence

These are historical observations from 2026-11-13, not checks repeated during
the documentation update. Older build artifacts and deployment iterations do
not establish the state of the current inline templates.

- Admin Lambda and API Gateway were deployed successfully. Earlier Lambda
  runtime checks returned 405 for GET and 403 for unauthenticated POST without
  publishing to SQS. The older gateway iteration also recorded managed-route
  checks; the current step-3 template exposes only the admin route.
- Recorded admin webhook URL:
  `https://ugltwyd3zf.execute-api.eu-central-1.amazonaws.com/webhook`.
  Read current stack outputs before deployment or registration.
- `tgbot-queue-admin-worker` deployment completed. Recorded instance:
  `i-086cc9f762f17a4b8`; retained volume: `vol-068095c5fdd6ad3a1`.
  SSM was Online and Run Command worked with no inbound access.
- During recovery from an old Celery container, published release
  `42b960c07829c5b7d7dbb4d31b43b1f4e10fd2f6` was deployed and container logs
  showed queued updates handled by aiogram. Fresh user command/response
  verification was still pending.
- Subsequent step-6 downtime/readiness hardening passed 12 local deployment
  tests at that checkpoint; a live deployment of those changes was not recorded.
- Steps 7–9 passed local YAML checks and seven mocked tests of the inline
  managed Lambda. No deployment or CloudFormation service validation of those
  templates was recorded. No managed webhook cutover was performed.

## Remaining work

### Managed delivery

- Implement a consumer of the managed JSON envelope and connect it to the
  managed handlers and intended execution-task queue.
- Configure worker IAM and queue settings for the managed path.
- Wire the managed gateway's `ManagedWebhookBaseUrl` into the admin worker.
  Step 6 currently appends `/managed` to the admin gateway URL, which does not
  select the separate managed API. Its configuration generation must change.
- After consumer readiness, register managed webhooks against the correct base
  URL. Existing registrations are not changed by updating configuration alone.
  `bot_factories.admin_bot.register_webhooks` supports re-registration and a
  `--dry-run` mode using the configured repository/environment.
- Validate steps 7–9 with CloudFormation and deploy when explicitly requested.

### Reproduction and operations

- Add explicit data-volume initialization/mount/recovery instructions or tooling.
  Step 5 attaches the disk but does not format/mount it; step 6 requires it at
  `/var/lib/admin-bot` and refuses an unexpected volume.
- Record and verify a release procedure. Current deployments resolve a mutable
  branch to a commit and record image ID; images/base images and dependencies
  are not a fully immutable deployment artifact chain.
- Align or retire the Redis-oriented standalone admin Compose recipe: its
  Dockerfile now defaults to the JSON SQS consumer.
- Improve webhook verification: step 4 prints `setWebhook` response but does not
  call `getWebhookInfo`. Its interactive credential prompts use visible input.
- Configure alarm notification destinations if notifications are required;
  current alarms have none.
- Define explicit recovery from failed builds and retained disks. Remote SSM
  commands may continue after local interruption; inspect their status before
  retrying. Old releases/images are not automatically cleaned up.

### End-to-end verification and cutover

- Verify authenticated admin delivery from Telegram through Lambda/SQS to the
  deployed worker, including a fresh user command and response.
- Verify invalid secrets do not enqueue and dependency/publication errors are
  retryable on both paths. Managed ingress validates the update shape; admin
  ingress currently forwards the body without JSON/schema validation. Decide
  whether to reject malformed admin bodies before queue publication; currently
  the consumer rejects them and SQS eventually sends them to the DLQ.
- Verify failed handling, worker crash/restart, visibility expiry, malformed
  messages, secret lookup failure and eventual DLQ delivery.
- Verify SQLite persistence and duplicate handling for activation, top-up and
  video debit. Successful replies followed by failed acknowledgements can repeat.
- Verify managed bot creation → invitation → activation → balance → top-up →
  video → one debit for repeated delivery after the managed consumer is ready.
- Verify execution-task retry/acknowledgement behavior separately from the JSON
  consumer; Celery late acknowledgement alone does not guarantee exception retry.
- Recreate the deployment from declared inputs and document any manual steps.
- At cutover, stop competing old workers, explicitly handle existing managed
  webhook registrations and verify admin/managed flows. Keep old resources/data
  until removal is separately authorized. No historical record here authorizes
  a new cutover or deletion.

## Development workflow and local checks

Follow current user instructions and applicable `AGENTS.md`. Work in small
verifiable increments; ask before architecture/dependency changes. Treat
“можно” as a question. Commit only on explicit request. Local tests do not
prove deployed integration.

```bash
.venv/bin/python -m unittest discover -s deploy/aws/tests -q
.venv/bin/pytest bot_factories/admin_bot/tests/test_json_worker.py
bash -n deploy/aws/4-register-webhook.sh deploy/aws/6-deploy-admin-bot.sh
git diff --check
```

Update this status after meaningful implementation/deployment checkpoints.
Preserve what was actually verified and distinguish local tests, infrastructure
creation, worker readiness and end-to-end Telegram behavior.


## Managed Lambda deployment (step 8) — 2026-11-13

- User authorized step 8. Account 642155085753, region eu-central-1. Deployed local 8-managed-lambda-stack.yaml; no commit or push.
- AWS template validation and seven local inline Lambda tests passed. Confirmed function name unused and existing webhook secret uses AWS-managed encryption, without reading its value locally.
- Reviewed change set: Add only LambdaLogs, LambdaRole and WebhookFunction. tgbot-queue-managed-lambda reached CREATE_COMPLETE.
- Function managed-to-sqs is Active, LastUpdateStatus Successful, python3.12; ARN arn:aws:lambda:eu-central-1:642155085753:function:managed-to-sqs.
- Export tgbot-queue-managed-WebhookFunctionArn is ready for step 9. Configuration points to the step-7 managed queue and the same webhook root secret ARN as admin.
- Direct runtime invocation with bot_id=123 and no secret returned application HTTP 403, without FunctionError. Confirms initialization and secret access; no SQS publication attempted. Successful authenticated publication and managed consumer integration remain unverified.
- Step 9, workers, admin resources and Telegram webhooks were not changed.


## Managed Gateway deployment (step 9) — 2026-11-13

- User authorized step 9. Account 642155085753, region eu-central-1; deployed local 9-managed-gateway-stack.yaml.
- AWS validate-template passed. Reviewed change set: Add only API, integration, managed route, stage, Lambda invoke permission, log group and API error alarm.
- Stack tgbot-queue-managed-gateway reached CREATE_COMPLETE.
- ManagedWebhookBaseUrl: https://dci09s6pcl.execute-api.eu-central-1.amazonaws.com/webhook/managed
- POST /webhook/managed/123 without secret returned HTTP 403 Forbidden, verifying Gateway-to-managed-Lambda integration without publishing an SQS message. Authenticated publication and end-to-end managed processing remain unverified.
- Managed worker and Telegram webhook cutover remain separate work. Admin resources and webhook registrations were not changed. No commit or push.
