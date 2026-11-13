# AWS serverless migration: plan and handoff

Last updated: 2026-11-13. Read this file before continuing migration work.

## Goal and agreed decisions

- Learn AWS serverless and replace maintained gateway infrastructure with managed services; minimize total custom code and configuration.
- Target: Telegram → HTTP API Gateway → small Lambda → SQS → Celery on a new EC2 → admin/managed bot handlers and SQLite.
- Move both admin and managed bot webhooks. Keep management, handlers and SQLite on EC2. Keep Celery.
- Use CloudFormation, eu-central-1, and the standard API Gateway HTTPS domain. No custom domain, Nginx or Redis required for this deployment.
- Use the current Telegram admin bot. Start with an empty database; recreate/reconfigure managed bots. No old-data migration or backwards compatibility requirement.
- Use Secrets Manager for the admin token and webhook root secret. User will manually populate real values later; use REPLACE_ME_WEBHOOK_SECRET / REPLACE_ME_ADMIN_BOT_TOKEN placeholders meanwhile. Managed bot tokens remain in SQLite.
- Preserve SSH key access restricted to operator CIDR. Do not introduce Session Manager.
- A short cutover outage is acceptable. Do not run old and new workers simultaneously.
- No automated database backups. Do not delete the old server or data implicitly.
- Everything needed to recreate the deployment must be scripted or declared; secret values stay outside Git and stack outputs.

## Workflow constraints

- Read /Users/valerii_zimichev/.codex/AGENTS.md and current user instructions.
- Work in small verifiable increments; stop at meaningful checkpoints for feedback.
- Ask before new dependencies or architecture changes. Do not refactor unrelated bots.
- Python: high-level functions before helpers; preserve definition-time model dependencies; __main__ last.
- “Можно” is a question, not execution authorization.
- Commit only on explicit user request. Previous commit permission does not cover future commits.
- Never imply passing unit tests means deployed integration is verified.

## Current gateway stack boundaries (2026-11-13)

Lambda uses the manually created `tgbot-queue/webhook` via a full-ARN parameter;
no generated webhook secret or admin-bot policy remains in its stack.
`2-lambda-stack.yaml` contains Lambda, role, logs and alarm;
`3-gateway-stack.yaml` contains API Gateway and invocation permission.
Build/SQS remain separate. Deploy Lambda from newly built packaged-template.json,
then API with its WebhookFunctionArn output. No build or deployment was run for
these changes. Historical progress below describes earlier iterations.

## Progress

1. [x] Create codex/serverless-migration from codex/aws-gateway-migration.
2. [x] Implement Lambda handler for both webhook paths with Pydantic API Gateway models and aiogram Update validation; strict integer update_id.
   - Existing task contracts: telegram.process_update(update), managed_bot.updates(bot_id, update).
   - Preserve original JSON when publishing with Celery; validate secrets/HMAC, fail closed, return 503 on secret/publication failure.
   - Secrets Manager lookup by WEBHOOK_SECRET_ARN, cached per warm runtime; local configured-secret fallback.
   - 17 unittest tests passed (Lambda tests + shared Celery factory tests).
3. [ ] Infrastructure and packaging — partial, not ready for full deployment.
   - [x] Add serverless-stack.json: HTTP API routes, Lambda, SQS/DLQ, generated webhook secret, IAM, 14-day logs, error/DLQ alarms.
   - [x] Prepare direct Python ZIP packaging in CodeBuild, without SAM, Dockerfile or root Makefile; see lambda_build/README.md. This revised workflow has not been run in AWS.
   - Previous SAM workflow only: locked hash-checked Linux x86_64 wheels for Python 3.13 installed successfully in CodeBuild; 12 Lambda tests passed there.
   - [x] AWS validate-template accepted the ingress template (2026-11-12); this does not validate deployment/runtime behavior. Service resource semantics still need review.
   - Previous SAM workflow only: built ZIP in CodeBuild, run Linux unit/import checks and verify ELF architecture, size, hash and excluded files. Actual Lambda invocation still pending.
   - [ ] Add new EC2 worker infrastructure and bootstrap, persistent encrypted SQLite storage, IAM queue/secret access, admin token secret integration.
   - [ ] Provision versioned artifact storage and reproducible worker deployment artifacts.
4. [ ] Reproducible deployment/configuration tooling.
   - Immutable image/base-image digests and versioned Lambda artifacts; no mutable branch checkout as a release identity.
   - Safe initial admin-token provisioning; no secret values in command output, user-data or CloudFormation outputs.
   - Obtain queue/webhook settings from stack outputs; new worker runs concurrency=1, pool=solo (admin dialogue state is in memory).
   - Script admin setWebhook and getWebhookInfo verification. Include message, managed_bot and callback_query updates. Managed webhook registration remains automatic during activation.
5. [ ] Verify delivery and end-to-end behavior.
   - Bad secrets/body never enqueue; both routes dispatch correct task names/arguments; dependency failures return retryable HTTP errors.
   - Explicitly verify Celery failure acknowledgement/retry behavior and DLQ delivery. acks_late alone does NOT ensure retry on handler exceptions.
   - Verify duplicate update handling for activation, limit top-up and video debit. Do not claim exactly-once delivery.
   - Test worker crash/restart, SQLite persistence, queue visibility expiry, malformed messages and secret lookup failure.
   - Create managed bot → activate → query balance → top up → send video → verify single debit on repeated update.
   - Recreate infrastructure from declared inputs and immutable artifacts.
6. [ ] Cutover after checks and explicit execution authorization.
   - Stop old worker, start new worker with fresh database, register current admin webhook, recreate/reconfigure managed bots.
   - Explicitly handle old managed webhook registrations; their records are not migrated.
   - Verify current admin and newly configured managed bots. Keep old resources until separately authorized for removal.

## Current checkpoint and next action

Latest successful build (supersedes failure notes below):
- CodeBuild 25854273-79e5-4df3-95c5-0eeb9cd1fc65, build number 4: SUCCEEDED end-to-end.
- Verified and downloaded ZIP (33,592,626 bytes), report.json and SAM packaged-template.json to .cloud-build/lambda/. SHA-256 b364502c3fa7b13086c3eb3d90e8374b014963b73db54e43fe17e20845d96fcb.
- S3 ZIP key packages/4/2e3922c407ff57421b9fa6e2ec536ca4, version 9_z3DrfwfZDckRLWFocfwvdpoh5NEQ4L, bucket tgbot-queue-serverless-build-artifacts-acnbtsijzwka.
- Packaged template results/4/template.json, version f.USq9qfSpTQVtHYhdxBHA_BU3BcoOo7. Generated by SAM and pinned by the publishing step, not reconstructed locally.
- No Lambda deployment, webhook switch, commit or push performed. Next is actual Lambda runtime verification; EC2 worker remains unfinished.

Earlier checkpoints/history:

- Branch codex/serverless-migration. Last pushed commit 2a82dae; SAM/CodeBuild changes and this plan remain uncommitted.
- Created stack tgbot-queue-serverless-build: retained versioned S3 bucket, restricted CodeBuild role, project and 14-day logs. No ingress or EC2 deployment performed.
- SAM templates, helpers, tests and README now live under deploy/aws/sam/. Root Makefile remains the SAM entry point. Removed the separate build shell script; its commands now live in buildspec.json. Removed custom Docker/ZIP packaging.
- Both templates passed sam validate --lint. 20 local tests pass.
- Exactly one paid CodeBuild launched: BuildProject-zZtYz1iyTKpK:f8b161f2-f5d3-4aa0-8412-d006eff01cc3. It FAILED in archive verification after successful SAM build, 12 Linux Lambda tests and ZIP upload (~36.9 MB).
- Failure: tests generated __pycache__ in artifact; fixed locally with PYTHONDONTWRITEBYTECODE=1. Also allowlisted certifi/cacert.pem (public HTTPS CA bundle) while keeping other PEM files forbidden. Fixes not yet run in CodeBuild.
- Build details saved in .cloud-build/lambda/build.json. No verified final report or downloaded final ZIP yet.
- User requested secret stubs: ingress template now provisions REPLACE_ME_WEBHOOK_SECRET; manually replace before registering webhooks. Future admin token placeholder REPLACE_ME_ADMIN_BOT_TOKEN. No real secrets fetched or migrated. Authentication still enabled.
- Redeployed tgbot-queue-serverless-build with the new deploy/aws/sam/buildspec.json path.
- User authorized retry. Build 8206741b-9a97-424a-aa78-1a9c9ab52277 (AWS build number 3) built/uploaded ZIP, but final verifier failed on botocore/cacert.pem (public CA bundle). Fixed allowlist locally, added coverage. No further paid build launched.
- Downloaded that existing ZIP and verified it locally: .cloud-build/lambda/lambda-webhook.zip, 33,592,626 compressed bytes / 76,551,963 unpacked bytes; native ELF x86_64 libraries, no forbidden entries/cache. SHA-256 b364502c3fa7b13086c3eb3d90e8374b014963b73db54e43fe17e20845d96fcb.
- Artifact: s3://tgbot-queue-serverless-build-artifacts-acnbtsijzwka/packages/3/2e3922c407ff57421b9fa6e2ec536ca4 version oiy0mP8owYKALyB_gJOqjqriiz0tOHgg.
- Saved report.json and reconstructed packaged-template.json locally from matching source with version-pinned CodeUri. The CodeBuild status remains FAILED; local post-verification succeeded. This is not a successful end-to-end CodeBuild result.
- Next: actual Lambda runtime smoke test before deployment/cutover. Future builds include corrected verifier; no extra build authorized implicitly.
- Runtime import verification in actual Lambda remains separate. EC2 worker, admin-token integration and cutover tooling remain incomplete.

## Useful checks

```sh
.venv/bin/python -m unittest bot_factories.admin_bot.tests.test_lambda_adapter worker.tests.test_celery_factory -q
python3 -m json.tool deploy/aws/sam/serverless-stack.json > /dev/null
aws cloudformation validate-template --region eu-central-1 --template-body file://deploy/aws/sam/serverless-stack.json
git diff --check
```

For future context reduction, preserve the latest user instruction plus this file path, current git status, active increment and any new verification results. Update this file at meaningful checkpoints; do not restart completed work.


## Lambda deployment — 2026-11-13

- Created `tgbot-queue-serverless-build` and completed CodeBuild build `BuildProject-2LcoqZJXqoxz:0e9865de-64e7-406a-8bb2-eb1abef6c316`. Linux adapter tests and archive verification passed.
- Build publication now uses `.lambda-build` on `PYTHONPATH` to access locked runtime dependencies.
- Removed reserved concurrency with user approval: this account has a regional concurrency quota of 10. The function uses the unreserved pool.
- Deployed `tgbot-queue-lambda`: `CREATE_COMPLETE`; function `tgbot-queue-lambda-WebhookFunction-SvFEQ2huO6Os` is Active. Its CodeSha256 matches the verified build report.
- The build started before the concurrency change. `.cloud-build/lambda/deployment-template.json` matches the current source and built S3 ZIP version; it differs from the downloaded packaged template only by removing `ReservedConcurrentExecutions`.
- Invoked `GET /webhook`: HTTP 405, no Lambda FunctionError. Initialization and webhook-secret access succeeded; no SQS message was sent.
- Gateway deployment, SQS publication smoke test, worker deployment and Telegram webhook cutover remain pending. Secret values were not printed.


## Gateway deployment — 2026-11-13

- Deployed `tgbot-queue-gateway`: `CREATE_COMPLETE`, connected to the existing Lambda.
- Added an explicit API name (`${AWS::StackName}-http-api`) after AWS rejected the initial unnamed API; the failed stack rolled back and was recreated.
- Admin webhook URL: `https://ugltwyd3zf.execute-api.eu-central-1.amazonaws.com/webhook`.
- Managed webhook base URL: `https://ugltwyd3zf.execute-api.eu-central-1.amazonaws.com/webhook/managed`.
- Both POST routes returned HTTP 403 without the secret header, confirming API Gateway → Lambda integration. No SQS messages were sent.
- Telegram webhook registration and successful publication to SQS remain pending.

## Worker infrastructure deployment — 2026-11-13

- Deployed `tgbot-queue-admin-worker` in `eu-central-1`; CloudFormation completed successfully.
- Instance: `i-086cc9f762f17a4b8`; retained data volume: `vol-068095c5fdd6ad3a1`.
- No inbound security group rules. Session Manager agent is Online on Ubuntu 26.04.
- SSM Run Command succeeded (`id`, cloud-init status done, SSM service active), confirming AWS CLI administration without opening SSH. An interactive browser session was not tested.
- Step 6 now temporarily authorizes SSH from the deploying machine's public IPv4 /32 and revokes its rule on exit. Seven local orchestration tests passed, including failure cleanup. No live application deployment was performed.
- Application deployment (step 6) and Telegram end-to-end verification remain pending.

## Worker deployment transport update — 2026-11-13

- Step 6 now takes only the numeric admin Telegram owner ID and uses AWS CLI SSM Run Command for source transfer and execution. SSH, public IP lookup and security group changes were removed.
- No infrastructure update or live application deployment was performed for this change. Existing closed inbound rules remain the intended configuration.
- Six local mocked orchestration tests passed, covering multi-chunk archive integrity, excluded secrets/databases, invalid input, offline SSM and command failure. Bash syntax and diff whitespace checks passed.
- A local interruption can leave a remote SSM command running or staging files behind; inspect the printed command ID before retrying. This supersedes the earlier temporary SSH deployment procedure.

## Admin secret format correction — 2026-11-13

- Confirmed the existing admin bot secret is JSON with ADMIN_BOT_TOKEN and ADMIN_BOT_OWNER_ID; values were not printed.
- Step 6 no longer prompts for or accepts an owner ID. Container startup and preflight use the same JSON parsing and validation. The webhook secret remains plaintext.
- Nine local tests passed, including malformed/missing fields, invalid owner IDs, startup environment and preflight without worker execution. No live application deployment was performed.


## Admin JSON consumer — 2026-11-13

- Agreed direction: bot management consumes JSON directly; Celery remains for execution tasks.
- Added sequential SQS → aiogram consumer for raw admin Telegram updates; acknowledgement follows successful dispatch. Errors leave messages for SQS retry/DLQ. No visibility extension or exactly-once guarantee.
- Docker default and step-6 startup/readiness now target the JSON consumer. Existing Celery modules and execution tasks remain unchanged.
- 14 local tests passed (JSON consumer and deployment script); shell syntax and whitespace checks passed. Real aiogram/AWS end-to-end validation is pending.
- No commit, push or deployment performed. Step 6 deploys a published Git branch, so these local changes are not yet deployable through it.
- Managed webhook routing/consumer support remains a separate increment; current Lambda/API exposes only the admin path.
