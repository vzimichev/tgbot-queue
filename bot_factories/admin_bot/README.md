# Admin bot

The root `docker-compose.yml` continues to run the webhook API and Redis. The
admin bot has a separate Docker Compose project containing:

- `worker` runs `admin_router` and manages created bots;
- `admin_data` persists the SQLite database with drafts, bot records, limits,
  and managed bot tokens.

The worker joins the root Compose network and connects to its `redis` service.

## Start

Create the environment file:

```bash
cp bot_factories/admin_bot/.env.example bot_factories/admin_bot/.env
```

Set `ADMIN_BOT_TOKEN`, `ADMIN_BOT_OWNER_ID`, and `REDIS_PASSWORD`. Start the
root stack first so its Redis service and network exist:

```bash
docker compose up -d
```

Then start the admin worker from the repository root:

```bash
docker compose \
  --env-file bot_factories/admin_bot/.env \
  -f bot_factories/admin_bot/docker-compose.yml \
  up -d --build
```

Configure the admin bot webhook on the existing gateway as:

```text
https://your-domain.example/webhook
```

Telegram must send the `message` and `managed_bot` update types. Use the root
gateway's `WEBHOOK_SECRET_TOKEN` when registering the webhook.

The default external Docker network is `tgbot-queue_default`. If the root
Compose project uses another project name, set `GATEWAY_NETWORK` accordingly.

## Operations

```bash
# Follow logs
docker compose --env-file bot_factories/admin_bot/.env \
  -f bot_factories/admin_bot/docker-compose.yml logs -f

# Stop the stack without deleting data
docker compose --env-file bot_factories/admin_bot/.env \
  -f bot_factories/admin_bot/docker-compose.yml down
```

Do not use `down -v` unless the saved bot records and tokens may be deleted.
