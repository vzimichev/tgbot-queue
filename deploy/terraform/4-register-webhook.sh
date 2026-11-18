#!/usr/bin/env bash
set -euo pipefail

# Read the webhook URL from the Terraform state beside this script.
terraform_dir=$(cd "$(dirname "$0")" && pwd)
webhook_url=$(terraform -chdir="$terraform_dir" output -raw webhook_url)

if [[ "$webhook_url" != https://* || "$webhook_url" == *[[:space:]]* || "$webhook_url" == *'['* || "$webhook_url" == *']'* ]]; then
  printf 'No valid HTTPS webhook URL found in Terraform state.\n' >&2
  exit 1
fi
printf 'Webhook URL: %s\n' "$webhook_url"

# Step 3: Use tokens from the environment or prompt for missing values.
admin_bot_token=${ADMIN_BOT_TOKEN:-}
if [[ -z "$admin_bot_token" ]]; then
  read -r -p 'Admin bot token: ' admin_bot_token
  printf '\n'
fi
webhook_secret_token=${WEBHOOK_SECRET_TOKEN:-}
if [[ -z "$webhook_secret_token" ]]; then
  read -r -p 'Webhook secret (plaintext value from Secrets Manager): ' webhook_secret_token
  printf '\n'
fi

# Step 4: Require both tokens before registering the webhook.
if [[ -z "$admin_bot_token" || -z "$webhook_secret_token" ]]; then
  printf 'Bot token and webhook secret must not be empty.\n' >&2
  exit 1
fi

# Step 5: Register the webhook with Telegram and print its response.
curl --silent --show-error --fail-with-body \
  "https://api.telegram.org/bot${admin_bot_token}/setWebhook" \
  --data-urlencode "url=${webhook_url}" \
  --data-urlencode "secret_token=${webhook_secret_token}" \
  --data-urlencode 'allowed_updates=["message","callback_query","managed_bot"]'
printf '\n'
