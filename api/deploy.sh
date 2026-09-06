#!/usr/bin/env bash
# Deploys the Locan API: (1) Lambda + DynamoDB + SES stack in us-west-2, (2) CloudFront + cert + DNS in us-east-1.
#
# Usage:  AWS_PROFILE=podsite-aws-profile ./deploy.sh
# Secrets are read from api/.env (git-ignored): OPENAI_API_KEY, GOOGLE_PLACES_API_KEY, ORIGIN_VERIFY_SECRET.
# ORIGIN_VERIFY_SECRET is generated and persisted to .env on first run. ALLOWED_ORIGINS in .env is for local dev;
# production CORS comes from PROD_ALLOWED_ORIGINS (default https://locan.ai,https://www.locan.ai).
set -euo pipefail
cd "$(dirname "$0")"

export AWS_PROFILE="${AWS_PROFILE:-podsite-aws-profile}"
APP_REGION="us-west-2"
EDGE_REGION="us-east-1"
APP_STACK="locan-api-v2"
EDGE_STACK="locan-api-edge"

if [ -f .env ]; then
  set -a; # shellcheck disable=SC1091
  source .env; set +a
fi

LLM_PROVIDER="${LLM_PROVIDER:-replicate}"
LLM_MODEL="${LLM_MODEL:-openai/gpt-5-nano}"

if [ "${ALLOW_EMPTY_KEYS:-0}" = "1" ]; then
  # Infrastructure-first deploy: 'disabled' makes the API answer 503 (not configured) until real keys are set.
  OPENAI_API_KEY="${OPENAI_API_KEY:-disabled}"
  REPLICATE_API_TOKEN="${REPLICATE_API_TOKEN:-disabled}"
  GOOGLE_PLACES_API_KEY="${GOOGLE_PLACES_API_KEY:-disabled}"
  echo "WARNING: deploying with upstream keys disabled (ALLOW_EMPTY_KEYS=1)"
else
  : "${GOOGLE_PLACES_API_KEY:?Set GOOGLE_PLACES_API_KEY in api/.env (or ALLOW_EMPTY_KEYS=1 to deploy infrastructure first)}"
  if [ "$LLM_PROVIDER" = "replicate" ]; then
    : "${REPLICATE_API_TOKEN:?Set REPLICATE_API_TOKEN in api/.env (LLM_PROVIDER=replicate)}"
    OPENAI_API_KEY="${OPENAI_API_KEY:-disabled}"
  else
    : "${OPENAI_API_KEY:?Set OPENAI_API_KEY in api/.env (LLM_PROVIDER=openai)}"
    REPLICATE_API_TOKEN="${REPLICATE_API_TOKEN:-disabled}"
  fi
fi

if [ -z "${ORIGIN_VERIFY_SECRET:-}" ]; then
  ORIGIN_VERIFY_SECRET="$(openssl rand -hex 24)"
  printf '\nORIGIN_VERIFY_SECRET=%s\n' "$ORIGIN_VERIFY_SECRET" >> .env
  echo "Generated ORIGIN_VERIFY_SECRET and saved it to api/.env"
fi

echo "=== 1/3 sam build (arm64 python3.12 in container) ==="
sam build --use-container --build-image public.ecr.aws/sam/build-python3.12:latest-arm64

echo "=== 2/3 deploy ${APP_STACK} (${APP_REGION}) ==="
sam deploy \
  --stack-name "$APP_STACK" \
  --region "$APP_REGION" \
  --resolve-s3 \
  --capabilities CAPABILITY_IAM \
  --no-confirm-changeset \
  --no-fail-on-empty-changeset \
  --parameter-overrides \
    "OpenAiApiKey=${OPENAI_API_KEY}" \
    "ReplicateApiToken=${REPLICATE_API_TOKEN}" \
    "LlmProvider=${LLM_PROVIDER}" \
    "LlmModel=${LLM_MODEL}" \
    "GooglePlacesApiKey=${GOOGLE_PLACES_API_KEY}" \
    "OriginVerifySecret=${ORIGIN_VERIFY_SECRET}" \
    "AllowedOrigins=${PROD_ALLOWED_ORIGINS:-https://locan.ai,https://www.locan.ai}" \
    "AlertEmail=${ALERT_EMAIL:-gintaras@locan.ai}" \
    "AlertFrom=${ALERT_FROM:-alerts@locan.ai}" \
    "NotifyEvents=${NOTIFY_EVENTS:-tool_run,error,quota,subscribe,confirm,unsubscribe,tool_request}"

ORIGIN_HOST="$(aws cloudformation describe-stacks --stack-name "$APP_STACK" --region "$APP_REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='FunctionUrlHost'].OutputValue" --output text)"
echo "Function URL host: $ORIGIN_HOST"

echo "=== 3/3 deploy ${EDGE_STACK} (${EDGE_REGION}) ==="
aws cloudformation deploy \
  --stack-name "$EDGE_STACK" \
  --region "$EDGE_REGION" \
  --template-file edge-template.yaml \
  --no-fail-on-empty-changeset \
  --parameter-overrides \
    "OriginHost=${ORIGIN_HOST}" \
    "OriginVerifySecret=${ORIGIN_VERIFY_SECRET}"

echo
echo "Done. API base: https://api.locan.ai/api   (health: https://api.locan.ai/api/health)"
echo "Smoke test:     ./scripts/smoke.sh https://api.locan.ai/api"
