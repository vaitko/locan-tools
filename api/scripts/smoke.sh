#!/usr/bin/env bash
# Smoke-test a deployed (or local) Locan API. Usage: ./scripts/smoke.sh https://api.locan.ai/api
set -uo pipefail
BASE="${1:-http://localhost:8000/api}"
ORIGIN="${ORIGIN:-https://locan.ai}"
fail=0

check() {
  local name="$1" expected="$2"; shift 2
  local out code
  out="$(curl -sS -o /tmp/smoke_body -w '%{http_code}' -H "Origin: $ORIGIN" "$@")"
  code="$out"
  if [ "$code" = "$expected" ]; then
    printf '✔ %-28s %s  %s\n' "$name" "$code" "$(head -c 160 /tmp/smoke_body | tr '\n' ' ')"
  else
    printf '✘ %-28s %s (expected %s)  %s\n' "$name" "$code" "$expected" "$(head -c 300 /tmp/smoke_body | tr '\n' ' ')"
    fail=1
  fi
}

check "health"        200 "$BASE/health"
check "autocomplete"  200 "$BASE/places/autocomplete?q=starbucks%20seattle&session=smoke-$(date +%s)"
check "review-response" 200 -X POST -H 'Content-Type: application/json' "$BASE/tools/review-response" \
  -d '{"businessName":"Smoke Test Bakery","reviewText":"Lovely croissants and friendly staff, will be back!","rating":5,"tone":"friendly"}'
check "validation 422" 422 -X POST -H 'Content-Type: application/json' "$BASE/tools/gbp-optimizer" -d '{}'

exit $fail
