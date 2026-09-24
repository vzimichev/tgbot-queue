# Admin bot

The root `docker-compose.yml` continues to run the webhook API and Redis. The
admin bot has a separate Docker Compose project containing:

- `worker` runs `admin_router` and manages created bots;
- `admin_data` persists the SQLite database with bot records, limits,
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

Telegram must send the `message`, `managed_bot`, and `callback_query` update types. Use the root
gateway's `WEBHOOK_SECRET_TOKEN` when registering the webhook.

The default external Docker network is `tgbot-queue_default`. If the root
Compose project uses another project name, set `GATEWAY_NETWORK` accordingly.

## Menu

The main menu has **Выбрать пользователя** and **Все боты**. The first button
opens Telegram's user picker directly, without an intermediate prompt. Selecting
a user opens their card with the current status and available actions:

- No bot: **Создать бота** asks for the initial budget, then opens Telegram's
  creation confirmation.
- Pending creation: **Продолжить создание** reuses the saved creation request.
- Awaiting activation: uses the existing one-time link in the sharing button, shows the current limit,
  **Отправить пользователю**, and **Добавить лимит**. For recipients without a
  username, **Поделиться ссылкой** opens Telegram's chat picker instead. The link
  is included only in the sharing button, not in the card text. Each saved bot
  is shown as one message with inline sharing, budget, and back buttons.
- Activated: uses the ordinary bot link in the sharing button, shows remaining budget, **Отправить пользователю**,
  and **Добавить лимит**.

**Назад** returns from budget input to the card without changing the budget;
from the card or recipient picker it returns to the main menu. Selecting a user
again never changes their limit or creates a duplicate bot.

## Dialogue state

Menu buttons, recipient selection, and budget input use separate aiogram handlers
and `FSMContext`, following the FaceSwap bot structure. The dialogue uses the
worker's default in-memory FSM storage: restarting the worker resets unfinished
input, so start again with **Выбрать пользователя**. Saved bots, pending creations, limits, and
activation tokens remain in SQLite. Legacy SQLite `draft` records are ignored;
no database migration is required.

## Why one-time activation links

Granting access directly to the selected Telegram user caused problems during
development. One-time activation links are an intentional workaround. The exact
cause of the Telegram access-setting failures has not been established; this is
an observed integration issue, not a documented universal Telegram restriction.

The initially selected user is used for bookkeeping and sending the invitation.
The final recipient is identified by the actual Telegram user ID in the message
sent when they open the personal bot's link and press Start.

Before activation, the bot has unrestricted Telegram access, but its worker only
handles activation messages; it does not run user tasks. A valid link binds the
bot to the account activating it. The worker restricts access to that recipient
(the owner retains access), reads back the access settings, and consumes the
activation token only after confirming that the restriction was applied.

Possession of the link allows its holder to claim the bot. The claimant's ID is
intentionally not compared with the initially selected user's ID. Send the link
only to its intended recipient; this behavior is part of the workaround.

If access setup fails or cannot be confirmed, the token remains valid and the
worker continues polling for another activation attempt. Repeated registration
events and bot API token updates preserve the recipient, activation state, and
existing access restrictions; they must not reopen an activated bot.

Do not replace this flow with direct access assignment or require the claimant
to match the initial selection without first reproducing and resolving the
original access-setting problem against the real Telegram API.

Existing webhook registrations must include `callback_query` for the inline
budget and back buttons to work.

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
