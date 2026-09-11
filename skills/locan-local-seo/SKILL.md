---
name: locan-local-seo
description: Use when auditing a local business's Google visibility (Business Profile, map rankings, AI answers) with the Locan MCP tools, and producing a prioritised, human-applied fix list.
---

# Locan local SEO audit

A repeatable procedure for auditing a local business's visibility in Google Search, Google Maps and AI
answers using the `locan` MCP tools, and turning the results into a prioritised fix list.

## Requirements

- The Locan MCP server (`locan-mcp`) connected, backed by the hosted API (`https://api.locan.ai/api`,
  daily per-visitor limits apply) or a self-hosted instance (`LOCAN_API_URL` pointed at it, e.g.
  `http://localhost:8080/api`, no limits).

## Procedure

1. **Resolve the business.** Call `find_business` with the business name (add the city if the name is
   common). Pick the matching place id from the results; ask the user to confirm if more than one
   candidate looks plausible.
2. **Audit the profile.** Call `gbp_audit` with that id as `place_id`. Note the score, grade, failing checks and
   the AI-suggested description, post ideas, FAQs and review reply templates.
3. **Check categories.** Call `gbp_categories` with the same `place_id` and 3–5 keywords that describe what the
   business does and what customers search for. Note which competitor categories it is missing.
4. **Check map rankings.** Call `rank_grid` once, for the single most important keyword (the head term),
   with `grid_size: 3` unless the user explicitly asks for a wider 5×5 grid. This is the most expensive
   call: one Google Places request per grid cell (9 for 3×3, 25 for 5×5).
5. **Check AI visibility.** Call `ai_visibility` with the business name, city and category. Note whether
   the business is named, which competitors are named instead, and any missing topics.
6. **Write the fix list**, in this priority order:
   1. Profile fields (website, phone, hours, photos, description) — the failing checks from `gbp_audit`.
   2. Categories — additions or changes to consider, from `gbp_categories`.
   3. Reviews — reply gaps and volume/recency issues surfaced by `gbp_audit` and `ai_visibility`.
   4. Pages/content — anything `ai_visibility` shows is missing from the business's own site.
7. **Offer review replies.** If the user pastes one or more reviews, call `review_reply` for each (with
   the review text and star rating) and offer the drafted replies.

## Output format for the fix list

For each item: what to change, why (which check/result it comes from), and its priority tier
(profile / categories / reviews / pages). Keep it short and specific — no invented statistics or scores
beyond what the tools returned.

## Boundaries

- This skill never changes a Google Business Profile, and no tool call does either — every tool is
  read-only against Google. Every recommendation is applied by the user, in their own Google Business
  Profile or website.
- Do not fabricate numbers (rankings, scores, review counts) beyond what a tool call returned.
