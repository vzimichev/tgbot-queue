# Telegram Processing Gateway

AWS serverless migration: Lambda ZIP builds use Python scripts and CodeBuild. Templates,
build tools and reproduction commands are in [deploy/aws/lambda_build](deploy/aws/lambda_build/README.md).
Current decisions and unfinished migration steps are recorded in
[the migration plan](deploy/aws/MIGRATION_PLAN.md).

A lightweight **FastAPI + Celery** gateway for building Telegram bots that rely on **heavy local processing**—AI image/video generation, audio transcription, face-swapping, large ML models, or any CPU/GPU-intensive tasks.

## Why this project exists

Telegram bots deployed to the cloud cannot efficiently run heavy AI pipelines.

This project solves the problem with a hybrid approach:

- Deploy only a **lightweight webhook gateway** to any cheap cloud VM.

- Run the **heavy workers locally** (or anywhere with GPUs/CPUs).

This lets you prototype AI-powered bots **locally**, with full GPU access, while keeping cloud costs minimal.

## Features
### Core Functionality

- **Webhook Gateway** (FastAPI) — receives Telegram updates securely.

- **Queue** (Redis by default, or AWS SQS) — decouples your cloud and local machines.

- **Workers** (Celery) — execute heavy processing (AI/ML/audio/video/etc.).

- **Bot** (Aiogram) — write simple Aiogram handlers; everything else is handled automatically.

### Architecture Benefits

- Local/Remote Hybrid: run GPU tasks locally, gateway in the cloud.

- Fully Modular: gateway, worker, and bot logic are isolated.

- Easy Experimentation: ideal for prototyping creative AI bot ideas.

- Production-Friendly: keep heavy tasks off your cloud instance.

## Folder Structure

    /api                 – FastAPI webhook  
    /worker              – Celery setup  
    /bot_factories       – isolated aiogram bot implementations
    /shared              – configs, clients  

If you want to build a fully customized bot, place it inside
`bot_factories`.\
Bot customization is essentially about defining **aiogram routes and
handlers**.\
The rest of the architecture remains unchanged.

### Architecture Overview:

    Telegram → FastAPI → Celery Task → Redis or SQS → Worker → Aiogram Bot → Telegram API

Aiogram **does not receive webhooks directly** --- it runs inside a
Celery worker.

## Requirements

- Python 3.13 or 3.14
- Docker (only for the Docker deployment)
- Telegram Bot Token
- Domain name (Telegram requires HTTPS for webhooks)

## Configuration

The project root `.env` contains gateway credentials only. Start from
`.env.example`:

``` env
WEBHOOK_SECRET_TOKEN=super-secret

REDIS_HOST=redis
REDIS_PORT=6379
REDIS_PASSWORD=guest1

# Redis is the default broker. Celery task results are not stored.
CELERY_BROKER=redis

# Required only for CELERY_BROKER=sqs. The URL must be for an existing queue.
# SQS_REGION=eu-central-1
# SQS_QUEUE_NAME=telegram_updates
# SQS_QUEUE_URL=https://sqs.eu-central-1.amazonaws.com/123456789012/telegram_updates
# SQS_POLLING_INTERVAL=1
# SQS_VISIBILITY_TIMEOUT=3600

# Select the task and queue belonging to the worker this gateway serves.
```

All variables are loaded via `shared/config.py`.

### Choosing the Celery broker

Redis remains the default for local development. Set `CELERY_BROKER=sqs` in
both the gateway and the matching worker environment to use Celery's native
Kombu SQS transport. No application task code or `send_task`/`.delay()` calls
change. The gateway and worker must use the same `SQS_QUEUE_NAME` and
`SQS_QUEUE_URL`.

`SQS_QUEUE_URL` is mandatory in SQS mode. It is registered as a Kombu
predefined queue, so the application uses that existing queue and never
silently creates SQS infrastructure. `SQS_REGION` selects the AWS region,
`SQS_POLLING_INTERVAL` controls the empty-queue polling delay, and
`SQS_VISIBILITY_TIMEOUT` controls how long an in-progress task is hidden.

AWS credentials are intentionally not configured in this repository. Boto3
uses the standard AWS credential provider chain: environment credentials or
profile for development, and an IAM role for EC2, ECS, or EKS in production.
Grant the gateway `sqs:SendMessage`; grant workers `sqs:ReceiveMessage`,
`sqs:DeleteMessage`, and `sqs:ChangeMessageVisibility`. Grant
`sqs:GetQueueAttributes` when required by the queue policy or operational
tooling. Scope these permissions to the configured queue ARN.

Celery task results are intentionally disabled: the gateway never reads them,
and `task_acks_late` lets the broker retry failed tasks. Therefore, an SQS
deployment does not need Redis. Redis is needed only while
`CELERY_BROKER=redis` remains enabled.

SQS provides at-least-once delivery. The existing late acknowledgement and
single-message prefetch settings are preserved, but a task may run again if a
worker dies or exceeds its visibility timeout. Set `SQS_VISIBILITY_TIMEOUT`
above the longest FaceFusion job (up to SQS's 12-hour limit) with a safety
margin, and configure the SQS queue's own visibility timeout consistently.
Avoid relying on Redis-specific Celery remote-control/event behavior when
operating with SQS.

Local bot credentials belong in separate, ignored files:

| File | Used by |
| --- | --- |
| `bot_factories/echo_bot/.env` (or one file per echo bot) | Echo Celery worker and its SSH tunnel |
| `bot_factories/faceswap_bot/.env` | FaceSwap worker, SSH tunnel, and local FaceFusion API |
| `bot_factories/admin_bot/.env` | Admin Celery worker and its SSH tunnel |

Copy the matching `.env.example` file in each bot directory and fill in its
credentials. Each launcher loads its own file. To run two echo bots, copy
`bot_factories/echo_bot/.env.example` to `bot_factories/echo_bot/.env.echo1` and
`bot_factories/echo_bot/.env.echo2`. Give them separate Telegram tokens and
local Redis ports. Each bot must use its own Redis broker so its worker only
consumes that bot's updates. FaceSwap uses local port 6380 by default. Start the workers in separate
terminals:

```bash
./bot_factories/echo_bot/start_worker.sh bot_factories/echo_bot/.env.echo1
./bot_factories/echo_bot/start_worker.sh bot_factories/echo_bot/.env.echo2
./bot_factories/faceswap_bot/start_worker.sh
./bot_factories/admin_bot/start_worker.sh
```

Each bot needs its own gateway deployment, Redis broker, and webhook. The
gateway publishes `telegram.process_update` to `telegram_updates`.
The Compose file runs one gateway deployment.

### Admin bot factory

Copy `bot_factories/admin_bot/.env.example` to `bot_factories/admin_bot/.env`,
set `ADMIN_BOT_TOKEN`, your numeric `ADMIN_BOT_OWNER_ID`,
`WEBHOOK_SECRET_TOKEN` from that gateway's `.env`, and the SSH/Redis settings
for its gateway. `ADMIN_BOT_CHILD_WEBHOOK_URL` must point to that gateway's
`/webhook/managed` endpoint. Enable Bot Management Mode for the admin bot in
BotFather. Set the admin bot's webhook to that gateway's `/webhook` endpoint
with `allowed_updates=["message", "managed_bot", "callback_query"]`. The gateway publishes the
usual `telegram.process_update` task to `telegram_updates`; the admin worker
consumes it through its SSH tunnel. Give the admin bot a separate Redis broker
from other bots because they use the same task name and queue.

The admin worker and its persistent SQLite database can also run in their own
Docker Compose project while using the root gateway and Redis; use
`bot_factories/admin_bot/docker-compose.yml` for that setup. For a local run,
open the configured SSH tunnel to Redis, load the admin `.env`, and start the
`bot_factories.admin_bot.celery_app` Celery worker. In
the admin bot's private chat, **Выбрать пользователя** asks you to choose a
Telegram user and opens their bot card. If no bot exists, press **Создать бота**
and enter its initial limit in seconds.
Confirm managed bot creation yourself with the offered button and keep its
suggested username. You remain its owner. The admin bot saves the token and
limit and creates a one-time link to the personal bot. When the recipient opens
that link, the worker reads their real Telegram ID, restricts the bot to that
account, and consumes the link. If the user
already has a saved bot, selecting them shows the existing invitation (or the
ordinary bot link after activation). For a pending creation, it shows the
**Продолжить создание** button. **Добавить лимит** on a saved bot's card asks
for seconds to add. **Все боты** lists saved bots and invitations. Parameters
and managed bot tokens are stored in
`bot_factories/admin_bot/.cache/admin.sqlite3`.
After activation, a personal bot spends its limit by the duration (in whole
seconds) of each video sent to it. A video is accepted only when its full
duration fits in the remaining limit; retried Telegram webhook deliveries do
not spend the limit twice.

## Running the Cloud Gateway

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
restart separately. The current gateway template exposes only `/webhook`;
managed-bot activation also needs `/webhook/managed/{bot_id}` support in the
gateway and Lambda before that flow can work. This deployment does not add it.

```bash
# On EC2 through Session Manager:
cd /opt/admin-bot
sudo docker compose logs -f
sudo docker compose restart
```

The former `ec2-stack.yaml` gateway template is replaced by step 5. Removing
that file does not delete any existing AWS stack or old server.

## Running the Worker

Run your local worker that contains the **aiogram bot handlers** and executes heavy processing:

``` bash
./bot_factories/echo_bot/start_worker.sh
```
The echo launcher loads its selected env file, opens an SSH tunnel to the
server's Redis, and starts the Celery worker. Stop it with Ctrl+C. The cloud
instance receives webhooks and publishes updates to the shared queue.

For Redis, leave `CELERY_BROKER=redis` and start the worker as above. For SQS,
put the same SQS settings in the gateway `.env` and the worker's bot-specific
environment file, set `CELERY_BROKER=sqs`, then run the same worker command:

```bash
./bot_factories/echo_bot/start_worker.sh
# or
./bot_factories/faceswap_bot/start_worker.sh
```

The SSH tunnel is needed only in Redis-broker mode. No SQS resource is created
by these commands.

## Setting the Telegram Webhook

After the cloud gateway is online, point your bot to it:

``` bash
curl -X POST "https://api.telegram.org/bot<token>/setWebhook" \
  -d "url=https://your_domain/webhook" \
  -d "secret_token=<WEBHOOK_SECRET_TOKEN>"
```

Webhook endpoint:
```
https://your-domain.com/webhook
```

## Custom Bots

To create a custom bot:

1. Add a package inside `bot_factories/`.
2. Keep its routes, service configuration, launch scripts, and specific tests in that package.
3. Create a Celery app using `CeleryFactory.create_app(router=your_router)`.
4. Give this bot its own gateway deployment and Redis broker.

The shared gateway and worker modules contain no service-specific processing code.

The FaceSwap integration test is opt-in because it requires a running local
FaceFusion HTTP service and ignored media fixtures under
`bot_factories/faceswap_bot/tests/data/`:

``` bash
RUN_FACESWAP_INTEGRATION=1 .venv/bin/pytest bot_factories/faceswap_bot/tests/test_integration.py
```

## License

MIT
