# Telegram Processing Gateway

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

- **Queue** (Redis) — decouples your cloud and local machines.

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

    Telegram → FastAPI → Celery Task → Redis → Worker → Aiogram Bot → Telegram API

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

# Select the task and queue belonging to the worker this gateway serves.
```

All variables are loaded via `shared/config.py`.

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

### AWS migration (EC2 + CloudFormation)

The AWS stack in `deploy/aws/gateway-stack.yaml` provisions an isolated VPC,
public subnet, security group, Ubuntu 26.04 x86_64 `t3.micro` Docker host, 1
GB swap, a 24 GB encrypted root volume, and a stable Elastic IP in
`eu-central-1`. It opens HTTP/HTTPS to the internet and SSH only from
`AllowedSshCidr`. Redis is not exposed publicly. It does not accept, generate,
or store application secrets.

Before creating the stack, create an EC2 key pair in `eu-central-1` and learn
the public IPv4 address of the computer that will administer and run the local
workers. Use its `/32` CIDR (for example, `203.0.113.10/32`) for SSH access.
Validate and create the stack from a machine authenticated to your AWS account:

```bash
aws cloudformation validate-template \
  --region eu-central-1 \
  --template-body file://deploy/aws/gateway-stack.yaml

aws cloudformation create-stack \
  --region eu-central-1 \
  --stack-name tgbot-queue-gateway \
  --template-body file://deploy/aws/gateway-stack.yaml \
  --parameters \
    ParameterKey=KeyName,ParameterValue=your-existing-key-pair \
    ParameterKey=AllowedSshCidr,ParameterValue=203.0.113.10/32 \
    ParameterKey=GatewayDomain,ParameterValue=your-domain.duckdns.org

aws cloudformation wait stack-create-complete \
  --region eu-central-1 \
  --stack-name tgbot-queue-gateway

aws cloudformation describe-stacks \
  --region eu-central-1 \
  --stack-name tgbot-queue-gateway \
  --query 'Stacks[0].Outputs' \
  --output table
```

The outputs contain the Elastic IP and SSH command. Wait for cloud-init to
finish, then connect using the `ubuntu` user. The stack's first-boot setup
installs basic tools, enables a 1 GB swap file, disables password and keyboard
interactive SSH, and enables UFW for ports 22, 80, and 443.

The existing DigitalOcean server runs the Docker gateway and a separate
`admin-bot-worker`; its `admin-bot_admin_data` volume contains the admin
SQLite database and must be migrated. Redis data is only the Celery queue and
is intentionally not migrated in this fast-cutover procedure.

Before cutover, retain these items until the migration has been verified:

- `/opt/tgbot-queue/.env` for rollback; create a new root `.env` on EC2 and
  record its new webhook/Redis secrets securely.
- `bot_factories/admin_bot/.env`, including `ADMIN_BOT_TOKEN` and
  `ADMIN_BOT_OWNER_ID`.
- The `admin-bot_admin_data` volume; it contains managed-bot tokens, limits,
  activation links, and the transaction ledger.
- The private key or SSH configuration required by each local worker. The new
  EC2 host accepts the EC2 key-pair user as `ubuntu`, not the old `root` login.

Do not transfer the old host SSH keys, Docker images, Redis queue volume, or
Let's Encrypt certificate. The Docker installer rebuilds images and recreates
the certificate renewal timer and Nginx renewal hook on EC2.

Before DNS cutover, pause the old admin worker long enough to create a
consistent backup, then start it again. Run this on the current server:

```bash
cd /opt/tgbot-queue
docker compose -f bot_factories/admin_bot/docker-compose.yml stop worker
docker run --rm \
  -v admin-bot_admin_data:/source:ro \
  -v /root:/backup \
  alpine tar czf /backup/admin-bot-data.tgz -C /source .
docker compose -f bot_factories/admin_bot/docker-compose.yml start worker
```

On the new EC2 instance, clone the repository and create its private gateway
environment file. This uses the Docker deployment so it matches the current
server topology:

```bash
sudo git clone --branch main https://github.com/vzimichev/tgbot-queue.git /opt/tgbot-queue
sudo install -m 600 /dev/null /opt/tgbot-queue/.env
sudoedit /opt/tgbot-queue/.env
```

Use this file format, with new values:

```env
WEBHOOK_SECRET_TOKEN=replace-with-a-new-random-secret
REDIS_HOST=127.0.0.1
REDIS_PORT=6379
REDIS_PASSWORD=replace-with-a-new-random-password
```

Copy the admin configuration and volume archive through the administrator
machine without keeping a local plaintext copy. Replace both placeholders with
the real hosts or IP addresses:

```bash
scp -3 root@OLD_SERVER:/root/admin-bot-data.tgz ubuntu@NEW_SERVER:/tmp/
scp -3 root@OLD_SERVER:/opt/tgbot-queue/bot_factories/admin_bot/.env \
  ubuntu@NEW_SERVER:/tmp/admin-bot.env
```

On the new host, install the admin configuration, change its
`REDIS_PASSWORD`, `WEBHOOK_SECRET_TOKEN`, and `ADMIN_BOT_CHILD_WEBHOOK_URL` to
the new values, then restore the volume before starting the admin worker:

```bash
sudo install -m 600 /tmp/admin-bot.env /opt/tgbot-queue/bot_factories/admin_bot/.env
sudoedit /opt/tgbot-queue/bot_factories/admin_bot/.env
sudo docker volume create admin-bot_admin_data
sudo docker run --rm \
  -v admin-bot_admin_data:/target \
  -v /tmp:/backup:ro \
  alpine tar xzf /backup/admin-bot-data.tgz -C /target
rm /tmp/admin-bot.env /tmp/admin-bot-data.tgz
```

At cutover, point DuckDNS at the Elastic IP. Once it resolves to the new host,
start the gateway and obtain its certificate:

```bash
cd /opt/tgbot-queue
sudo bash deploy/docker/install.sh your-domain.duckdns.org
sudo docker compose -f bot_factories/admin_bot/docker-compose.yml up -d worker
```

Verify `https://your-domain.duckdns.org/openapi.json`, update the Telegram
webhook with the new secret, and replace `SSH_HOST` in every local
bot-specific `.env` with `ubuntu@your-domain.duckdns.org`. Copy the new
`REDIS_PASSWORD` to each bot-specific `.env`; then restart every local worker
so its SSH tunnel uses the new host. Re-register the webhook of the admin bot
and every existing managed bot: managed-bot webhook secrets are derived from
`WEBHOOK_SECRET_TOKEN`, so rotating it invalidates their previous webhook
credentials. Run the managed-bot command first in dry-run mode, then for real;
it logs only managed-bot IDs, never their tokens:

```bash
sudo docker compose -f bot_factories/admin_bot/docker-compose.yml exec -T worker \
  python -m bot_factories.admin_bot.register_webhooks --dry-run
sudo docker compose -f bot_factories/admin_bot/docker-compose.yml exec -T worker \
  python -m bot_factories.admin_bot.register_webhooks
```

The fast cutover allows tasks still queued in the old Redis volume to be lost.
Keep the old server until test updates succeed through the gateway and every
active worker; only then delete the Droplet.

### Without Docker (Debian 13 or Ubuntu)

On a fresh Ubuntu 26.04 or Debian 13 server, point your domain at the server
and allow inbound TCP ports 80 and 443. Create a private `/root/gateway.env`:

```env
WEBHOOK_SECRET_TOKEN=replace-with-a-random-secret
REDIS_HOST=127.0.0.1
REDIS_PORT=6379
REDIS_PASSWORD=replace-with-a-random-password
```

Use a password made of letters, digits and common punctuation without spaces.
Download and run the bootstrap script, passing your real domain and env file:

```sh
curl -fsSLo bootstrap.sh https://raw.githubusercontent.com/vzimichev/tgbot-queue/codex/cloud-gateway-deploy/deploy/cloud/bootstrap.sh
sudo bash bootstrap.sh tgbot-queue.duckdns.org /root/gateway.env
```

The bootstrap adds swap on small machines, installs packages, checks out this
branch in `/opt/tgbot-queue`, configures local-only Redis, runs
`deploy/cloud/install.sh`, and configures Nginx and a Let's Encrypt certificate.
It can be rerun to update the checkout. Pass an email address as a third
argument if you want certificate expiry notices. The bot token stays on the
worker machine; configure the Telegram webhook separately after bootstrap.
No Celery worker is started on the cloud host.

The script uses Python 3.14 on Ubuntu 26.04 and Python 3.13 on Debian 13.
The lock file includes wheels for both. Ubuntu 24.04 has Python 3.12 by default.

### With Docker

On a fresh Ubuntu server, copy the project to `/opt/tgbot-queue` and create a
private `.env` there with `WEBHOOK_SECRET_TOKEN`, `REDIS_PASSWORD`,
`REDIS_HOST=redis`, and `REDIS_PORT=6379`. Point the domain at the server, then run:

```bash
sudo bash deploy/docker/install.sh your-domain.example
```

The installer adds swap on small VMs, installs Docker and Certbot, starts the
FastAPI gateway, Redis, and Nginx, and obtains a Let's Encrypt certificate.
Certificate renewal reloads Nginx automatically. Redis is exposed only on the
server's loopback interface for the local worker's SSH tunnel. The gateway uses
Celery to publish tasks to Redis; the bot worker runs on your own machine.

View logs:

``` bash
docker compose logs -f
```

Stop containers without deleting Redis data:

``` bash
docker compose down
```

## Running the Worker

Run your local worker that contains the **aiogram bot handlers** and executes heavy processing:

``` bash
./bot_factories/echo_bot/start_worker.sh
```
The echo launcher loads its selected env file, opens an SSH tunnel to the
server's Redis, and starts the Celery worker. Stop it with Ctrl+C. The cloud
instance receives webhooks and publishes updates to the shared queue.

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
