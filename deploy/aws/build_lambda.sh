#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
artifact_dir="${1:-${project_dir}/.cloud-build/lambda}"

if ! command -v docker >/dev/null 2>&1; then
  echo 'Docker with BuildKit is required to build the Lambda artifact.' >&2
  exit 1
fi

build_args=()
if [[ -n "${LAMBDA_BUILD_IMAGE:-}" ]]; then
  build_args+=(--build-arg "LAMBDA_BUILD_IMAGE=${LAMBDA_BUILD_IMAGE}")
fi

docker build --platform linux/amd64 \
  --file "${project_dir}/deploy/aws/lambda.Dockerfile" \
  --target artifact \
  "${build_args[@]}" \
  --output "type=local,dest=${artifact_dir}" \
  "${project_dir}"

echo "Lambda artifact: ${artifact_dir}/lambda-webhook.zip"
