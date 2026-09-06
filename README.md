# Locan — free local SEO tools (open source)

Source code of the tools behind **[locan.ai](https://locan.ai)**: a hub of free local SEO tools for small
businesses — no account, no card, free forever. If a tool you need doesn't exist, you ask for it on the
homepage and we build it, free, usually within 3 days.

| Tool | What it does |
|---|---|
| Google Business Profile Optimizer | Scores the public profile (website, hours, phone, photos, reviews, category) and drafts descriptions, posts, FAQs and review replies with an LLM |
| GBP Category Optimizer | Compares your categories with the competitors ranking for your keywords and scores what to add |
| Local Rank Checker | 3×3 / 5×5 grid of Google Maps positions around your business (Places text search with location bias) |
| AI Visibility Checker | Simulates buyer questions across assistant personas and reports whether your business is named |
| LocalBusiness Schema Generator | JSON-LD builder, prefilled from your Google Business Profile — runs in the browser |
| Google Review Link & QR Poster | Review link, QR code and printable poster — runs in the browser |
| AI Review Response Generator | Three reply variants in the review's language, with handling tips |

## How it is built

```
site/   Astro 7 static site (Tailwind v4). Tool pages = one .astro page + one TypeScript module each.
api/    FastAPI on AWS Lambda (arm64) behind a Lambda Function URL + CloudFront. One router per tool.
infra/  S3 website config (redirects) and the CloudFront redirect function.
```

Upstreams: **Google Places API (New)** for all business data, an LLM through **Replicate**
(`openai/gpt-5-nano` by default; OpenAI direct is supported). DynamoDB holds daily per-visitor quotas and
the subscriber list (double opt-in, one-click unsubscribe). SES sends transactional e-mails and owner
notifications. Tool inputs are never stored.

Why it can stay free: static hosting, one Lambda, Places free tiers, a nano model and daily quotas.
The rank grid is the expensive tool (one Places text search per cell), which is why it has the tightest quota.

## Run it locally

```bash
# API
cd api
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
cp .env.example .env                 # GOOGLE_PLACES_API_KEY, REPLICATE_API_TOKEN (or OPENAI_API_KEY + LLM_PROVIDER=openai)
set -a; source .env; set +a
.venv/bin/uvicorn app.main:app --port 8000 --reload
.venv/bin/pytest -q                  # no network needed

# Site
cd site
npm install
npm run dev                          # http://localhost:4321 → talks to http://localhost:8000/api (site/.env)
npm run check                        # production build + internal link checker
```

Google Cloud: enable **Places API (New)** and create a server key restricted to it. Replicate: any token
with a few dollars of credit (below $5 Replicate throttles to 6 predictions/minute).

## Deploy your own

`api/deploy.sh` (AWS SAM; Lambda + DynamoDB + SES in one region, ACM + CloudFront + Route 53 for the API
domain in us-east-1) and `scripts/deploy-site.sh` (S3 + CloudFront). Replace the domain, bucket,
distribution and hosted-zone identifiers in `api/template.yaml`, `api/edge-template.yaml`,
`api/deploy.sh`, `scripts/deploy-site.sh`, `site/.env.production` and `site/src/data/site.ts`
(analytics IDs live there too).

## Adding a tool

1. `api/app/routers/<name>.py` — `router = APIRouter()`, call `await enforce_tool_quota(request, "tool_<name>")`
   first, use `llm.chat_json()` / `PlacesClient`, and `await notify_tool_run(...)` on success. Add the module
   name to `_include_tool_routers` in `api/app/main.py`. Tests in `api/tests/`.
2. `site/src/data/tools.ts` — one entry (copy, pillar, FAQ, related tools).
3. `site/src/pages/tools/<slug>.astro` (form + results markup inside `ToolShell`) and
   `site/src/scripts/tools/<slug>.ts` (calls `apiFetch`, renders results, dispatches `locan:tool-run`).

See `CONTRIBUTING.md`. The best way to propose a tool is still to request it on locan.ai — that is how
every tool here was chosen.

## What is not in this repository

The long-form guides published on locan.ai are editorial content and are **not** open source. The site
builds without them (guide sections and links simply don't render). The Locan name and logo are
trademarks of their owner and are not covered by the code license.

## License

Code: [GNU AGPL-3.0](LICENSE). You can run, study, modify and redistribute it; if you offer a modified
version as a service, you must publish your changes under the same license.
