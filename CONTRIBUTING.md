# Contributing

Thanks for helping keep local SEO tools free. Two ground rules keep the hub honest:

1. **Every tool is read-only and works from public data.** Nothing may write to a user's Google Business
   Profile or store tool inputs.
2. **No invented numbers.** Copy, docs and tool output must not present made-up statistics or unverifiable
   claims ("boosts rankings by 30%").

## Ways to contribute

- **Request a tool** at https://locan.ai (or open an issue with the `tool-request` label). Real requests are
  how tools get prioritised.
- **Fix or improve a tool**: open a pull request against `main`. Keep API changes covered by tests
  (`cd api && .venv/bin/pytest -q`) and make sure the site builds (`cd site && npm run check`).
- **Report a bug**: include the tool, the input (a public business name is fine), what you expected and what
  you got. Never paste API keys or e-mail addresses of other people.

## Building a new tool

A tool is three files plus tests:

| Layer | File | Notes |
|---|---|---|
| API | `api/app/routers/<name>.py` | `router = APIRouter()`; first line `await enforce_tool_quota(request, "tool_<name>")`; register the module name in `_include_tool_routers` (`api/app/main.py`); pydantic v2 request/response models with size limits; call `notify_tool_run()` on success |
| Tests | `api/tests/test_<name>.py` | Use the `client`, `places_mock` (respx) and `fake_llm` fixtures — no network |
| Data | `site/src/data/tools.ts` | Copy, pillar, FAQ, related tools (this drives cards, nav, footer, schema) |
| Page | `site/src/pages/tools/<slug>.astro` | Form and results markup inside `ToolShell`; the shell adds the optional e-mail field, methodology and FAQ |
| Script | `site/src/scripts/tools/<slug>.ts` | `apiFetch()` the endpoint, render with `esc()`, `document.dispatchEvent(new CustomEvent('locan:tool-run'))` on success |

Cost matters: prefer Places field masks that stay in the Essentials/Pro SKUs, cap upstream calls per run, and
say on the page what the tool can and cannot see.

## Style

Python: type hints, pydantic v2, `ApiError(status, code, message)` for errors, 120-char lines.
TypeScript/Astro: strict TS, no frameworks in the browser, Tailwind utility classes with the tokens in
`site/src/styles/global.css`.

## License

By contributing you agree that your contribution is licensed under the AGPL-3.0 like the rest of the code.
