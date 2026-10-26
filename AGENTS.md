# Repository guidance

## Architecture

- Keep `api/` as the lightweight FastAPI webhook gateway, `worker/` as the
  reusable Celery foundation, `shared/` as common configuration and clients,
  and `bot_factories/` as isolated bot implementations.
- The gateway is a Celery producer only: it validates and queues JSON updates.
  Create Aiogram `Bot`, `Dispatcher`, and bot-specific handlers only in a
  concrete bot worker.
- A bot needs its own gateway deployment, Redis broker, webhook, and local
  environment file. Do not mix tokens, queues, or state between bots.

## Managed bots

- Authenticate managed-bot webhook requests with the per-bot HMAC secret and
  use constant-time comparison.
- Keep recipient authorization checks in every managed-bot entry point.
- Put durable business rules such as video-limit debits and duplicate-update
  protection in repositories or ledger services, not Telegram routes. Those
  operations must be idempotent by Telegram update ID.

## Configuration and secrets

- Never commit `.env` files, tokens, Redis passwords, SQLite caches, or media
  fixtures/results. Update the relevant `.env.example` when adding a required
  setting.
- Treat the root `README.md` as the source of truth for local launch,
  SSH-tunnel, and deployment instructions; do not duplicate runbooks here.

## Tests

- Keep bot-specific code and its tests under the matching
  `bot_factories/<bot>/` package.
- Run the affected test package before the full suite: `.venv/bin/pytest`.
- The FaceSwap integration test is opt-in and requires
  `RUN_FACESWAP_INTEGRATION=1` plus local media/API prerequisites.
