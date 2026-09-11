#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

PORT="${LOCAN_PORT:-8080}"
BASE="http://localhost:${PORT}"
CREATED_ENV=0

if [ ! -f .env ]; then
  cp .env.example .env
  CREATED_ENV=1
  echo "created a temporary .env from .env.example for this run"
fi

FAIL=0

cleanup() {
  docker compose down
  if [ "$CREATED_ENV" -eq 1 ]; then
    rm -f .env
    echo "removed the temporary .env"
  fi
}
trap cleanup EXIT

docker compose up -d --build

echo "waiting for ${BASE}/api/health ..."
ok=0
for _ in $(seq 1 30); do
  if body="$(curl -fsS "${BASE}/api/health" 2>/dev/null)" && echo "$body" | grep -q '"selfHosted": *true'; then
    ok=1
    break
  fi
  sleep 3
done
if [ "$ok" -eq 1 ]; then
  echo "PASS: /api/health selfHosted=true"
else
  echo "FAIL: /api/health did not report selfHosted=true within 90s"
  FAIL=1
fi

check_get() {
  local path="$1"
  local code
  if code="$(curl -s -o /dev/null -w '%{http_code}' "${BASE}${path}")"; then
    :
  else
    code="000"
  fi
  if [ "$code" = "200" ]; then
    echo "PASS: GET ${path} -> 200"
  else
    echo "FAIL: GET ${path} -> ${code}"
    FAIL=1
  fi
}

check_get "/"
check_get "/tools/"
check_get "/tools/local-rank-checker/"

if ! review_body="$(curl -s -X POST "${BASE}/api/tools/review-response" \
  -H 'Content-Type: application/json' \
  -d '{"businessName":"Test","reviewText":"Great service, thanks!","rating":5}')"; then
  review_body=""
fi
if [ -z "$review_body" ]; then
  echo "FAIL: POST /api/tools/review-response returned an empty body"
  FAIL=1
elif [ "${review_body:0:1}" = "<" ]; then
  echo "FAIL: POST /api/tools/review-response returned HTML"
  FAIL=1
elif [ "${review_body:0:1}" != "{" ]; then
  echo "FAIL: POST /api/tools/review-response returned a non-JSON body: ${review_body}"
  FAIL=1
elif echo "$review_body" | grep -q '"error"'; then
  echo "PASS: POST /api/tools/review-response returned a JSON error body (no working LLM configured)"
elif echo "$review_body" | grep -q '"responses"'; then
  echo "PASS: POST /api/tools/review-response returned a JSON success body with \"responses\""
else
  echo "FAIL: POST /api/tools/review-response returned unexpected JSON: ${review_body}"
  FAIL=1
fi

exit "$FAIL"
