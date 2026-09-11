# locan-tools

`locan` (CLI) and `locan-mcp` (MCP server) — local SEO tools for Google Business Profiles, on top of the [Locan](https://locan.ai) API.

Both are thin HTTP clients: no Google Places or LLM keys live on your machine. Point them at the hosted API or at your own self-hosted Locan instance.

## Install

```bash
uvx --from locan-tools locan find-business "Kauno klinikos"   # run without installing
pipx install locan-tools                                     # isolated install
pip install locan-tools                                      # into the current environment
```

Requires Python 3.11 or newer.

## Commands

```bash
locan find-business "Smile Dental Kaunas"
locan gbp-audit --business-name "Smile Dental" --city Kaunas
locan gbp-categories --place-id PLACE_ID --keyword "dentist kaunas" --keyword "teeth whitening"
locan rank-grid --place-id PLACE_ID --keyword "dentist" --grid-size 5 --spacing-km 1
locan ai-visibility --business-name "Smile Dental" --city Kaunas --category dentist
locan review-reply --business-name "Smile Dental" --review-text "Friendly staff, no waiting." --rating 5
locan review-link PLACE_ID
locan schema-jsonld PLACE_ID
```

| Command | What it does |
|---|---|
| `find-business` | Looks a business up on Google by its name (add the city to disambiguate) and prints candidate `placeId`s — start here. Category searches such as "dentist kaunas" return nothing; use `gbp-categories` or `rank-grid` for keyword research. |
| `gbp-audit` | Scores a public Google Business Profile and adds AI suggestions. Identify the business with `--place-id`, `--business-name` + `--city`, or `--gbp-url`. |
| `gbp-categories` | Compares your categories with the competitors ranking for your keywords. Repeat `--keyword` for up to 10 keywords. |
| `rank-grid` | Google Maps rankings for one keyword across a grid of nearby locations. `--grid-size` 3 or 5, `--spacing-km` 0.5, 1 or 2. |
| `ai-visibility` | How often AI assistants name the business for local buyer queries. |
| `review-reply` | Three public replies to a Google review, plus handling tips. `--rating` 1 to 5. |
| `review-link` | The direct Google review link for a place id. Runs locally, no API call. |
| `schema-jsonld` | LocalBusiness JSON-LD built from the business's Google profile. |

Every command prints JSON to stdout. Add `--pretty` before the command name for a compact table instead:

```bash
locan --pretty find-business "Smile Dental Kaunas"
```

API errors are printed to stderr as `error: <message> (<code>)` and exit with status 1.

## Self-hosting

`LOCAN_API_URL` selects the API. It defaults to `https://api.locan.ai/api`; point it at your own instance to skip the hosted limits:

```bash
export LOCAN_API_URL=http://localhost:8080/api
locan find-business "Smile Dental Kaunas"
```

## MCP server

`locan-mcp` exposes the same eight tools (`find_business`, `gbp_audit`, `gbp_categories`, `rank_grid`, `ai_visibility`, `review_reply`, `review_link`, `schema_jsonld`) to MCP clients over stdio.

Claude Code:

```bash
claude mcp add locan -- uvx --from locan-tools locan-mcp
```

Claude Desktop / Cursor:

```json
{
  "mcpServers": {
    "locan": {
      "command": "uvx",
      "args": ["--from", "locan-tools", "locan-mcp"],
      "env": { "LOCAN_API_URL": "https://api.locan.ai/api" }
    }
  }
}
```

Streamable HTTP instead of stdio:

```bash
locan-mcp --http --port 8765
```

## Cost and limits

The tools call Google Places and AI models through the Locan API, so they are not free to run. `rank-grid` is the most expensive: one Places request per grid cell, 25 for a 5×5 grid. Daily limits apply on the hosted API; self-host for unlimited runs.

## License

AGPL-3.0-only. The full text is in `LICENSE` next to `pyproject.toml` (and at the repository root of the public repo).
