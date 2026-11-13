# Telegram Processing Gateway

Telegram webhook ingress and bot workers, with heavy processing kept on local
or remote CPU/GPU machines. The repository contains an AWS JSON ingress path
and an alternative FastAPI/Celery path.

## Current architecture

The AWS admin path is implemented:

```text
Telegram → HTTP API Gateway → inline Lambda → SQS → admin JSON worker → aiogram
```

The admin worker runs sequentially on EC2 in Docker and stores bot records,
managed bot tokens, invitations and limits in SQLite on a separate EBS volume.
Lambda code lives directly in the CloudFormation templates: no Lambda ZIP
build, SAM or CodeBuild is required.

Managed bots have separate ingress templates:

```text
Telegram → managed HTTP API Gateway → inline Lambda → managed SQS
```

The managed JSON consumer and its connection to processing workers are still
unfinished. Creating the managed ingress does not establish end-to-end delivery.
The target architecture is recorded in [flow.mmd](deploy/aws/flow.mmd);
implementation status and remaining work are in
[the migration plan](deploy/aws/MIGRATION_PLAN.md).

The alternative gateway remains available for Celery-based bots:

```text
Telegram → FastAPI → Redis or Kombu SQS → Celery worker → aiogram
```

Raw JSON from the AWS Lambdas and Celery task envelopes are different queue
contracts. Do not connect a Celery worker to the raw JSON ingress queues.

## Repository layout

| Path | Purpose |
| --- | --- |
| `deploy/aws/` | Numbered CloudFormation templates, registration/deployment scripts and migration status |
| `api/` | Alternative FastAPI webhook gateway |
| `worker/` | Shared Celery factory and task dispatch |
| `shared/` | Settings, webhook secrets and HTTP job client |
| `bot_factories/admin_bot/` | Admin/managed bot routes, SQLite repositories and admin JSON worker |
| `bot_factories/echo_bot/` | Echo Celery bot |
| `bot_factories/faceswap_bot/` | FaceSwap Celery bot and FaceFusion integration |
| `deploy/docker/` | Nginx configuration and certificate helpers for the Docker gateway |

## Requirements

- Python 3.13 or 3.14 and Poetry for application development.
- A Telegram bot token; enable Bot Management Mode in BotFather for the admin bot.
- AWS CLI credentials and an existing EC2 key pair for AWS deployment.
- Docker/Compose on the application host (step 6 installs them on EC2).
- A domain and HTTPS certificate for the alternative Docker/Nginx gateway.
  AWS ingress uses the API Gateway HTTPS domain instead.

The inline AWS Lambdas use Python 3.12 independently of the application runtime.

## AWS deployment

Use `eu-central-1` consistently. The numbered files describe dependencies;
register the admin webhook only once its worker is ready to consume updates.
Secrets must already exist in Secrets Manager:

- Admin secret: JSON containing `ADMIN_BOT_TOKEN` and `ADMIN_BOT_OWNER_ID`.
- Webhook secret: a plaintext root secret shared by the admin worker and both
  ingress Lambdas. Managed bots use secrets derived from this root.

Keep secret values outside Git and CloudFormation parameters/outputs. Pass
secret ARNs to the templates. Customer-managed KMS keys need additional decrypt
permissions beyond the supplied policies.

### Admin ingress: steps 1–3

Deploy SQS, Lambda and API Gateway in that order, with the same `ProjectName`
(default `tgbot-queue`):

```bash
aws cloudformation deploy \
  --region eu-central-1 \
  --stack-name tgbot-queue-sqs \
  --template-file deploy/aws/1-sqs-stack.yaml

aws cloudformation deploy \
  --region eu-central-1 \
  --stack-name tgbot-queue-lambda \
  --template-file deploy/aws/2-lambda-stack.yaml \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides \
    WebhookSecretArn=arn:aws:secretsmanager:eu-central-1:ACCOUNT:secret:WEBHOOK

aws cloudformation deploy \
  --region eu-central-1 \
  --stack-name tgbot-queue-gateway \
  --template-file deploy/aws/3-gateway-stack.yaml
```

The admin Lambda validates the webhook secret, then forwards the request body
to SQS without JSON/schema validation. The admin worker validates the update. The gateway exposes `POST /webhook`; its `WebhookUrl`
output is used by steps 4 and 6. Function names must be available when creating
new stacks. The queue and DLQ are retained on stack deletion; Lambda is also
retained. Review retained resources before recreating stacks.

### Admin webhook registration: step 4

Once the admin worker is ready:

```bash
./deploy/aws/4-register-webhook.sh
```

The script asks for the region, gateway stack and missing token/secret values
(or reads `ADMIN_BOT_TOKEN` and `WEBHOOK_SECRET_TOKEN` from the environment).
It registers `message`, `callback_query` and `managed_bot` updates and prints
Telegram's response. Its prompts are visible input. It does not read Secrets
Manager or verify `getWebhookInfo`; verify delivery separately.

### AWS admin worker: steps 5 and 6

`deploy/aws/5-admin-bot-worker.yaml` creates infrastructure only: an Ubuntu
26.04 x86_64 t3.micro, a public subnet with no inbound access by default, Session Manager access, an
instance role for the existing SQS queue and two Secrets Manager secrets,
a 24 GiB root disk and a separate encrypted 8 GiB SQLite disk. No HTTP ports,
Elastic IP, Redis, gateway software or bot process are created on EC2.
The public IP can change after stop/start; step 6 reads the current stack output.

Create both secrets beforehand. The admin bot SecretString must be a JSON object
with `ADMIN_BOT_TOKEN` (non-empty token string) and `ADMIN_BOT_OWNER_ID` (positive
numeric Telegram user ID, as a JSON integer or string). The webhook SecretString
must be the plain webhook root secret.
Use the same webhook secret ARN as the Lambda stack. AWS-managed secret keys
are supported; customer-managed KMS keys require an additional decrypt policy.
Never put secret values in template parameters or Git.

```bash
aws cloudformation deploy \
  --region eu-central-1 \
  --stack-name tgbot-queue-admin-worker \
  --template-file deploy/aws/5-admin-bot-worker.yaml \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides \
    KeyName=your-existing-key-pair \
    AdminBotSecretArn=arn:aws:secretsmanager:eu-central-1:ACCOUNT:secret:ADMIN \
    WebhookSecretArn=arn:aws:secretsmanager:eu-central-1:ACCOUNT:secret:WEBHOOK
```

Use the same ProjectName as step 1. The data disk is retained when the stack
is deleted or the volume is replaced. Retention is not a backup: a recreated
stack creates a fresh disk; reattaching retained data requires a separate,
explicit recovery operation. No automated backups are configured.

Deploy a published GitHub branch to EC2 by running step 6 locally:

```bash
./deploy/aws/6-deploy-admin-bot.sh
# Git branch [current-local-branch]:
```

Press Enter to deploy the current local branch, or enter another branch. In a
detached checkout, enter a branch explicitly. Uncommitted and unpushed changes
are not deployed. The script fetches the branch from the public GitHub repository
on EC2 and runs Docker Compose to build and start the worker.

Step 6 installs Git, Docker and Docker Compose on EC2 and enables Docker.
The step-5 data EBS volume must already be mounted at `/var/lib/admin-bot`.
The script does not format disks. The current step-5 template does not yet
mount the disk automatically.

Locally, AWS CLI credentials, Git and Python 3 are required. Optional settings:
`AWS_REGION` (default `eu-central-1`), `WORKER_STACK` (default
`tgbot-queue-admin-worker`), `GATEWAY_STACK` (default `tgbot-queue-gateway`).
The script reads CloudFormation outputs and executes one SSM command. The
instance must be Online in SSM. No SSH or inbound ports are required.

Runtime settings contain only secret ARNs; the container reads Secrets Manager
at startup. SQLite stays on the persistent data disk. Each deployment fetches the selected branch directly from GitHub and records
its commit SHA. That snapshot is extracted into a fresh directory. The worker
is stopped with `docker compose down` before `docker compose build` and
`docker compose up`; downtime includes the build and preflight checks. A failed
build leaves the worker stopped. An existing `admin-bot.service` is disabled
before the build. Concurrent deployments are rejected by a server-side lock.
Success requires the running container to use the built image ID, have no
startup restarts and emit the JSON worker readiness message. The final output
records the deployed commit and image ID. Branch updates after fetch belong
to the next deployment. There is no automatic
rollback. Stop workers on other hosts before the first production deployment.

SSM output may be buffered or truncated. Failures print the SSM command ID.
Interrupted remote execution may continue; inspect it before retrying. Full
server logs: `cd /opt/admin-bot && docker compose logs`.

The admin worker consumes raw Telegram JSON from SQS and dispatches it directly
to aiogram, sequentially. It deletes each message only after successful handling;
failures remain for retry after the queue visibility timeout and eventually go
to the DLQ (five receives). Delivery can repeat, including after a successful
Telegram response if acknowledgement fails. Handlers must finish within the
queue visibility timeout; this worker does not extend it.
Readiness means configuration and SQS access passed, not that Telegram flows have
been verified. Check creation, activation, top-up, duplicate video debit and worker
restart separately. The admin gateway exposes only `/webhook`. Managed-bot delivery requires the
separate steps 7–9 and a compatible managed JSON consumer, which is not yet
implemented. Step 6 currently derives `ADMIN_BOT_CHILD_WEBHOOK_URL` from the
admin URL by appending `/managed`; this is not the separate managed gateway.
Wiring the managed gateway output into the worker remains unfinished.

```bash
# On EC2 through Session Manager:
cd /opt/admin-bot
sudo docker compose logs -f
sudo docker compose restart
```

### AWS managed webhook ingress: steps 7, 8 and 9

These templates create a separate HTTP API Gateway, Lambda and SQS/DLQ for
**all** managed bots. They do not change admin resources, deploy a managed
worker or register Telegram webhooks. Deploy in order in `eu-central-1`:

```bash
aws cloudformation deploy \
  --region eu-central-1 \
  --stack-name tgbot-queue-managed-sqs \
  --template-file deploy/aws/7-managed-sqs-stack.yaml

aws cloudformation deploy \
  --region eu-central-1 \
  --stack-name tgbot-queue-managed-lambda \
  --template-file deploy/aws/8-managed-lambda-stack.yaml \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides \
    WebhookSecretArn=arn:aws:secretsmanager:eu-central-1:ACCOUNT:secret:WEBHOOK

aws cloudformation deploy \
  --region eu-central-1 \
  --stack-name tgbot-queue-managed-gateway \
  --template-file deploy/aws/9-managed-gateway-stack.yaml
```

All three default to `ProjectName=tgbot-queue-managed`, keeping queue names and
CloudFormation exports separate from admin. If overriding it, use the same
value in all three stacks and a value different from the admin ProjectName.
The default Lambda name is `managed-to-sqs`; override `FunctionName` if it is
already used. Use the **same plaintext webhook root secret ARN as the admin
worker**: managed webhook registration derives each bot's secret from it.
Customer-managed KMS keys require additional decrypt permissions.

Step 9 outputs `ManagedWebhookBaseUrl`, ending in `/webhook/managed`. Once a
compatible managed worker is deployed, configure the admin worker's
`ADMIN_BOT_CHILD_WEBHOOK_URL` with that value. Telegram sends updates to
`POST /webhook/managed/{bot_id}`. The Lambda validates the per-bot HMAC secret
and publishes `{"bot_id": 123, "update": {"update_id": 456, ...}}` as raw JSON.
This is neither a Celery envelope nor an admin queue payload; the existing
admin JSON worker cannot consume it. Do not switch managed webhooks before
that consumer is ready. Existing managed bots require explicit webhook
re-registration; changing the base URL alone does not update Telegram.

SQS retries can deliver duplicates; consumers must handle them. The queues
are retained on stack deletion, and their default visibility timeout is
3600 seconds. Logs are retained for 14 days. Gateway and DLQ alarms have no
notification destinations configured. No end-to-end delivery is established
by creating these resources alone.

## Admin bot behavior

In the admin bot's private chat, **Выбрать пользователя** opens a selected
Telegram user's bot card. **Создать бота** asks for an initial limit in seconds.
Confirm creation using the offered button and keep the suggested username;
the admin operator remains the bot owner. The repository stores the token,
limit and one-time invitation. Opening the invitation binds the personal bot
to the recipient's actual Telegram ID and consumes the link.

Existing cards show the invitation or activated bot link; pending creations
show **Продолжить создание**. **Добавить лимит** adds seconds, and **Все боты**
lists saved bots. The default database is
`bot_factories/admin_bot/.cache/admin.sqlite3`.

Managed handlers accept a video only when its entire duration fits the balance
and guard against repeated debit for a retried update. These handlers exist in
the Celery path; the AWS managed JSON path still needs its consumer and worker
configuration before activation/video flows can be verified end to end.

## Alternative FastAPI/Celery deployment

This path is separate from the raw JSON AWS ingress. Copy the root
`.env.example` to `.env` for gateway credentials and broker settings. Settings
are loaded by `shared/config.py`. Bot credentials belong in ignored per-bot
files copied from the corresponding `.env.example`.

The root `docker-compose.yml` runs FastAPI, Redis and Nginx. Configure
`deploy/docker/nginx.active.conf` and certificates under `/etc/letsencrypt`
before starting it (the active configuration is generated by
`deploy/docker/install.sh`):

```bash
docker compose up -d --build
```

FastAPI exposes `/webhook` and `/webhook/managed/{bot_id}`. For a regular bot,
register the externally reachable HTTPS `/webhook` URL with Telegram and use
the same `WEBHOOK_SECRET_TOKEN` as the gateway. Managed registration uses the
per-bot derived secret and the configured `ADMIN_BOT_CHILD_WEBHOOK_URL`.

### Local Celery workers

For Redis, configure the bot's SSH/Redis settings and token, then run:

```bash
./bot_factories/echo_bot/start_worker.sh
./bot_factories/faceswap_bot/start_worker.sh
```

The echo/FaceSwap launchers load the selected bot env file, open an SSH tunnel to Redis,
and start Celery with one solo worker. Stop with Ctrl+C. They currently open
the tunnel unconditionally, including when `CELERY_BROKER=sqs` is configured.
For SQS without a Redis tunnel, load the bot environment and invoke its Celery
app directly instead of using these launchers.

To run multiple echo bots, pass a separate env file to each launcher:

```bash
./bot_factories/echo_bot/start_worker.sh bot_factories/echo_bot/.env.echo1
./bot_factories/echo_bot/start_worker.sh bot_factories/echo_bot/.env.echo2
```

Use a separate gateway and broker queue per independent bot deployment to
prevent workers consuming another bot's updates. With Redis, use separate
Redis instances and matching tunnel ports; FaceSwap defaults to local port 6380.

### Celery broker configuration

Redis is the default (`CELERY_BROKER=redis`). Celery task results are disabled.
For Kombu SQS, set these values in both gateway and matching worker:

```dotenv
CELERY_BROKER=sqs
SQS_REGION=eu-central-1
SQS_QUEUE_NAME=telegram_updates
SQS_QUEUE_URL=https://sqs.eu-central-1.amazonaws.com/123456789012/telegram_updates
SQS_POLLING_INTERVAL=1
SQS_VISIBILITY_TIMEOUT=3600
```

The queue must already exist: `SQS_QUEUE_URL` is mandatory and registered as
a predefined Kombu queue. AWS clients use the standard credential provider
chain (local profile/environment or instance role). Grant the gateway
`sqs:SendMessage`; workers need receive/delete/change-visibility permissions
and queue attribute access as needed. Scope permissions to the queue ARN.
No Redis result backend is required for SQS.

SQS delivery can repeat. Set queue visibility above the longest job with a
margin; it is limited to 12 hours. Late acknowledgement alone does not ensure
retry after every Celery handler exception. Verify task retry behavior and
duplicate handling for the chosen worker. Redis-specific Celery control and
event behavior is not available through SQS.

### Admin Docker caveat

`bot_factories/admin_bot/Dockerfile` now starts the raw JSON SQS worker by
default. The standalone `bot_factories/admin_bot/docker-compose.yml` still
contains Redis-oriented configuration and is not a complete deployment recipe
for that default command. Use AWS step 6 for the JSON worker. A Celery admin
Compose deployment requires an explicit Celery command and matching settings.

## Custom bots and verification

Add a package in `bot_factories/` with routes, configuration, launch scripts
and bot-specific tests. For the Celery path, create an app through
`CeleryFactory.create_app(router=your_router)` and isolate its gateway/queue.
The shared modules provide dispatch and configuration; service-specific work
belongs in the bot package. An AWS JSON consumer requires a matching payload
contract rather than a Celery task app.

Run focused checks with the installed development/test dependencies:

```bash
.venv/bin/python -m unittest discover -s deploy/aws/tests -q
.venv/bin/pytest bot_factories/admin_bot/tests/test_json_worker.py
```

The FaceSwap integration test requires a running local FaceFusion HTTP service
and ignored media fixtures under `bot_factories/faceswap_bot/tests/data/`:

```bash
RUN_FACESWAP_INTEGRATION=1 .venv/bin/pytest bot_factories/faceswap_bot/tests/test_integration.py
```

Local tests do not verify deployed Telegram/AWS integration. See the migration
plan for the remaining delivery, persistence and recovery checks.

## License

MIT
