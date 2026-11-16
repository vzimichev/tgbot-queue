#!/usr/bin/env bash
set -euo pipefail

# Step 1: Select the AWS region and Gateway stack.
read -r -p 'AWS region [eu-central-1]: ' region
region=${region:-eu-central-1}
read -r -p 'Gateway stack [tgbot-queue-gateway]: ' gateway_stack
gateway_stack=${gateway_stack:-tgbot-queue-gateway}

# Step 2: Fetch and validate the deployed webhook URL from CloudFormation.
webhook_url=$(aws cloudformation describe-stacks \
  --region "$region" \
  --stack-name "$gateway_stack" \
  --query 'Stacks[0].Outputs[?OutputKey==`WebhookUrl`].OutputValue | [0]' \
  --output text)

if [[ "$webhook_url" != https://* || "$webhook_url" == *[[:space:]]* || "$webhook_url" == *'['* || "$webhook_url" == *']'* ]]; then
  printf 'No valid HTTPS WebhookUrl found in stack %s.\n' "$gateway_stack" >&2
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
