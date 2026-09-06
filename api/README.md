# Locan API (`api.locan.ai`)

FastAPI app that powers every free tool on locan.ai. Runs on AWS Lambda (Python 3.12, arm64)
behind a Lambda Function URL fronted by CloudFront. Upstreams: Google Places API (New), OpenAI.
State: one DynamoDB table (`locan-api`) for daily quotas and subscribers; SES for owner alerts.

## Local development

```bash
cd api
/opt/homebrew/opt/python@3.13/bin/python3.13 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
cp .env.example .env          # fill REPLICATE_API_TOKEN and GOOGLE_PLACES_API_KEY
set -a; source .env; set +a
.venv/bin/uvicorn app.main:app --port 8000 --reload
# → http://localhost:8000/api/health   (Swagger: /api/docs in dev)
```

Tests (no network, Places/OpenAI mocked):

```bash
.venv/bin/pytest -q
```

## Layout

```
app/main.py            create_app(): CORS, X-Origin-Verify check, routers under /api
app/config.py          Settings.from_env()
app/errors.py          ApiError → {"error","code"} JSON; QuotaExceeded → 429 quota_exceeded
app/quota.py           daily counters (Memory / DynamoDB), enforce()
app/deps.py            client_ip(), enforce_tool_quota(request, scope, units)
app/services/places.py PlacesClient (autocomplete, details, search_text) + normalize_details()
app/services/llm.py    chat_text() / chat_json() — the only LLM entry points; Replicate (default) or OpenAI provider (monkeypatched in tests)
app/services/geo.py    offset(), haversine_km()
app/routers/*.py       health, places, subscribe, and one module per tool (mounted at /api/tools/*)
lambda_handler.py      Mangum adapter
template.yaml          SAM stack (us-west-2): Lambda + Function URL + DynamoDB + SES identity
edge-template.yaml     CloudFormation (us-east-1): ACM cert + CloudFront + Route 53 for api.locan.ai
deploy.sh              builds and deploys both stacks; scripts/smoke.sh checks a deployed base URL
```

## Adding a tool router

Create `app/routers/<name>.py` exporting `router = APIRouter()` with routes relative to `/api/tools`,
add the module name to `_include_tool_routers` in `app/main.py`, call
`await enforce_tool_quota(request, "tool_<name>")` first, use `llm.chat_json(...)` via the module
(`from ..services import llm`) so tests can fake it, and add `tests/test_<name>.py`.

## Endpoints

See `docs/superpowers/specs/2026-09-05-locan-relaunch-design.md` §6 for request/response contracts.
