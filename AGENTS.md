# AGENTS.md

## Scope

These instructions apply to the entire repository.

This file is a living project guide. Add new project-specific rules here when
they become important for future changes.

## Collaboration rules

- Preserve unrelated user changes in the working tree.
- Make the smallest change that solves the requested task.
- Do not commit changes unless the user explicitly asks for a commit.
- Do not push, create pull requests, or modify remote branches unless the user
  explicitly asks for it.
- When a commit is explicitly requested, use the commit naming convention
  defined below.
- Do not use destructive commands such as resetting the repository, deleting
  volumes, or deleting databases unless the user explicitly requests it.
- Before changing behavior, inspect the relevant code and existing tests.
- Do not claim that tests or checks passed unless they actually completed.
- If validation is blocked by a missing dependency, service, fixture, or
  credential, report that limitation clearly.

## Commit naming

Use a short English imperative summary without a type or scope prefix:

```text
Add managed bot activation flow
Fix video debit idempotency (#25)
```

Use an English imperative, start with a capital letter, avoid a trailing
period, and add `(#number)` for an issue or pull request.

Do not create a commit merely because the work is complete. Create one only
after the user explicitly asks for it.

## Branch strategy

Never work directly on `main`. Start every task from the current `main` in a
focused branch named `codex/<short-topic>`.

Flow: branch → implement → validate → review diff → commit/PR only on request.
Keep one task per branch and do not mix unrelated changes.

## Project purpose

This project is a Telegram processing gateway.

The cloud gateway receives Telegram webhooks and publishes updates to
Redis/Celery. Local workers run Aiogram handlers and CPU/GPU-heavy processing.

The intended architecture is:

```text
Telegram
  -> FastAPI webhook gateway
  -> Redis broker
  -> Celery worker
  -> Aiogram handler or heavy-processing service
  -> Telegram API
```

The cloud gateway should remain lightweight. Heavy processing belongs in local
workers.

## Repository structure

- `api/` — FastAPI application and Telegram webhook endpoints.
- `worker/` — shared Celery configuration and task registration.
- `shared/` — shared settings, clients, logging, and webhook helpers.
- `bot_factories/` — isolated bot implementations.
- `deploy/` — Docker, Nginx, systemd, and cloud bootstrap scripts.
- `tests/` directories — unit and integration tests for each component.
- `README.md` — user-facing setup and deployment documentation.

Service-specific processing should stay inside its own
`bot_factories/<bot_name>/` package whenever possible.

## Architectural direction: clean core and replaceable specifics

The project is intentionally designed as a reusable core with replaceable bot
factories. The common gateway, Celery wiring, configuration primitives, and
shared clients form the stable skeleton. A concrete bot factory adds or patches
the behavior needed by one bot without copying or contaminating the common
core.

When implementing a feature, first decide whether it is genuinely common to
all bots. Keep it in shared code only when multiple bot factories need the
same behavior and the abstraction is stable. Otherwise keep it inside the
specific bot factory.

Prefer explicit extension points over conditionals such as:

```python
if bot_type == "echo":
    ...
elif bot_type == "faceswap":
    ...
```

The common core must not know private details of a concrete bot. A bot factory
may depend on the common core; the common core must not import a concrete bot
factory merely to support it.

### Layer responsibilities inside a bot factory

Keep the following boundaries explicit:

```text
Telegram/Aiogram routes
        -> application/service logic
        -> repositories
        -> database CRUD/data access
        -> SQLite or another persistence mechanism
```

#### Telegram routes

Routes adapt Telegram updates and callback events to application operations.
They may validate input, extract Telegram identifiers, call services or
repositories, and format Telegram responses.

Routes must not contain substantial business rules, SQL, transaction
management, or direct persistence details.

#### Repositories and business logic

Repositories and application services own business behavior and invariants:

- authorization and ownership checks;
- state transitions;
- balance and limit rules;
- idempotency decisions;
- orchestration of Telegram API calls and persistence;
- conversion of low-level failures into domain-level outcomes.

Do not move business rules into handlers just because the rule is currently
used by one route. Keep reusable behavior testable without constructing an
Aiogram update or Telegram transport.

#### Database CRUD

Database modules own persistence mechanics:

- SQL statements;
- row-to-model and model-to-row conversion;
- connection and transaction primitives;
- schema initialization and additive migrations;
- database constraints and indexes.

Database CRUD code must not know about Telegram messages, callback buttons,
webhook payloads, or user-facing text. It should return data or persistence
errors to the repository/application layer.

Repositories should not duplicate SQL that belongs in the database CRUD layer.
Routes should not bypass repositories to call database CRUD directly unless a
read-only operation is explicitly documented as an exception.

### Dependency direction

Dependencies should point toward stable abstractions and the common core:

```text
concrete bot factory -> shared core
Telegram route       -> application/repository
repository           -> database CRUD
database CRUD        -> database driver
```

Avoid reverse dependencies from shared modules into bot-specific routes,
repositories, or database tables. Avoid making the database schema dictate
Telegram-facing models.

When a new feature crosses layers, keep the data transformation at the
boundary. Do not pass raw Telegram update dictionaries deep into database
code, and do not return database rows directly to Telegram handlers when a
domain/application result is more appropriate.

## Core architecture invariants

### Celery

The shared Telegram task and queue are:

- task: `telegram.process_update`
- queue: `telegram_updates`
- broker: Redis DB 1
- result backend: Redis DB 2

`CeleryFactory.create_app()` without a router is used by the gateway. It must
not construct a Telegram `Bot` or `Dispatcher`.

`CeleryFactory.create_app(router=...)` is used by concrete bot workers. Only
worker applications should create Aiogram runtime objects.

The default Celery configuration uses late acknowledgements and
`worker_prefetch_multiplier = 1`. Do not change retry or delivery semantics
without tests for duplicate and failed processing.

### Bot isolation

Every bot must use its own gateway deployment and Redis broker. Several bots
intentionally use the same task and queue names, so sharing a broker can make
one worker consume another bot's updates.

When adding or changing a bot, check all of these together:

- Telegram token;
- gateway environment file;
- Redis host, port, and password;
- SSH tunnel port, if applicable;
- webhook URL and secret;
- Celery app import path;
- worker launch command;
- focused tests.

### Webhooks

The normal endpoint is `/webhook`.

Managed child bots use `/webhook/managed/{bot_id}` and a derived secret.

Do not weaken webhook authentication or change task names, queue names, or
Redis isolation without checking both the gateway and every corresponding
worker.

Webhook payloads may contain user data. Do not add logs containing tokens,
passwords, activation links, or unnecessary full Telegram payloads.

## Configuration and secrets

The root `.env` is for the gateway. Bot credentials belong in separate ignored
files:

- `bot_factories/echo_bot/.env`
- `bot_factories/faceswap_bot/.env`
- `bot_factories/admin_bot/.env`

Launch scripts may set `APP_ENV_FILE` so that the selected environment file is
loaded.

Never commit:

- `.env` files;
- Telegram bot tokens;
- Redis passwords;
- SSH credentials or private keys;
- SQLite databases;
- generated media;
- FaceSwap test fixtures;
- local deployment files.

When adding a setting:

1. Add it to the correct settings class.
2. Add a safe placeholder to the relevant `.env.example`.
3. Document where the setting is used.
4. Add or update configuration tests.
5. Do not put real credentials in examples.

Do not source a production gateway environment file into a root shell. The
cloud installer intentionally parses it as data.

## Adding a new bot factory

A new bot belongs in `bot_factories/<name>/` and should normally contain:

- an Aiogram router;
- a Celery app created through `CeleryFactory.create_app(router=...)`;
- bot-specific configuration;
- a launcher or deployment definition;
- focused tests;
- an `.env.example` file.

Keep shared modules usable by all bot factories. Give the bot its own Redis
broker and gateway deployment unless the isolation model is intentionally
changed and documented.

## Admin bot rules

The admin bot stores state in `bot_factories/admin_bot/.cache/`.

Database initialization and additive migrations belong in
`bot_factories/admin_bot/db/db_init.py`.

When changing the schema:

- use an additive migration;
- keep existing databases usable;
- preserve existing unique constraints;
- update database tests;
- test both a fresh database and an existing database;
- never delete or rewrite user data automatically.

Managed bot video charging must remain:

- authorized by the persisted recipient Telegram ID;
- limited by the current balance;
- atomic with the balance check;
- idempotent for repeated Telegram `update_id` values;
- represented in the transaction ledger.

Never charge a duplicate webhook twice. Do not expose managed bot tokens,
claim tokens, or activation URLs in logs or error messages.

## FaceSwap rules

The FaceSwap worker depends on an external local FaceFusion HTTP service.

The integration test is opt-in and may take a long time.

Follow the command and prerequisites documented in `README.md`. Do not run
this test during ordinary validation unless the local service and ignored
media fixtures are available.

The FaceSwap launcher manages an SSH Redis tunnel, the FaceFusion API process,
and the Celery worker. If one exits, the launcher should stop the stack.

Keep the launcher compatible with macOS Bash 3.2 unless that requirement is
explicitly removed.

## Validation and documentation intent

`README.md` is the source of truth for concrete commands: dependency setup,
local worker startup, deployment, Docker operations, webhook configuration,
and test invocation.

Keep this file at the level of intent:

- validate the smallest relevant scope first;
- run focused tests for changed behavior and broader tests when practical;
- use static analysis and syntax validation appropriate to the changed files;
- keep external-service and media-dependent tests opt-in;
- report missing tooling, services, fixtures, or credentials instead of
  claiming successful validation;
- update `README.md` when a user-facing command or operational procedure
  changes;
- do not duplicate operational command blocks from `README.md` here.

For Docker and deployment changes, inspect the resulting configuration and
scripts before applying them to real infrastructure. Do not run deployment
against a real server unless the target host, domain, and environment are
explicitly confirmed.

## Testing expectations

For a behavior change:

- add a focused regression test;
- test error paths and duplicate/retry behavior when relevant;
- use mocks for Telegram and external HTTP services in unit tests;
- keep external integration tests opt-in;
- run the narrowest useful test first;
- run the full suite when practical.

Do not claim tests passed unless the command actually completed successfully.

## Code style

Follow the existing style:

- Python 3.13–3.14;
- type annotations for new public functions;
- small focused functions;
- explicit error handling;
- async code for Telegram and HTTP operations;
- no blocking network calls inside async functions;
- no secrets in exceptions or logs.

Do not replace existing Celery/Aiogram patterns with a different architecture
without a specific reason and corresponding tests.

## Deployment safety

Deployment files affect real infrastructure. Before modifying them:

- read the complete script;
- verify paths and service names;
- preserve secret-file permissions;
- avoid exposing Redis publicly;
- keep Nginx and certificate behavior intact;
- test shell syntax;
- update `README.md` if operator behavior changes.

Never delete deployment data, Redis volumes, or SQLite databases unless the
user explicitly requests it.

## Completion checklist

Before handing off a change:

- relevant tests were run;
- static checks were run or their limitation was reported;
- no secrets or generated files were added;
- documentation and `.env.example` files were updated if needed;
- Celery task names, queue names, Redis isolation, and webhook behavior were
  checked;
- no commit was created unless the user explicitly requested one;
- the final response lists changed files, validation performed, and any
  remaining limitation.
