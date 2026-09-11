from __future__ import annotations

import argparse
from typing import Any, Callable

import httpx
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from . import __version__
from .client import LocanApiError, LocanClient, make_client

LIMITS = "daily limits apply on the hosted API; self-host for unlimited runs"

INSTRUCTIONS = (
    "Local SEO tools for Google Business Profiles, backed by the Locan API. "
    "Start with find_business to turn a business name into a Google place id, then pass that id to the other tools. "
    f"Results come from Google Places and AI models, so they cost money to produce: {LIMITS}. "
    "Set LOCAN_API_URL to point the server at a self-hosted Locan API instead of https://api.locan.ai/api."
)

server = MCPServer("locan", instructions=INSTRUCTIONS, version=__version__)


def _call(operation: Callable[[LocanClient], Any]) -> Any:
    client = make_client()
    try:
        return operation(client)
    except LocanApiError as exc:
        raise ToolError(f"{exc.message} ({exc.code})") from exc
    except httpx.HTTPError as exc:
        raise ToolError(f"could not reach {client.base_url} ({exc.__class__.__name__})") from exc
    finally:
        client.close()


@server.tool(
    name="find_business",
    description=(
        "Find a business on Google Maps and return candidate matches, each with a Google place id, a name "
        "and an address. Use this first whenever you only know a business by name: every other tool works "
        "best with a place_id. "
        f"Costs one Google Places request per call; {LIMITS}."
    ),
)
def find_business(query: str, lang: str | None = None, region: str | None = None) -> list[dict[str, Any]]:
    return _call(lambda client: client.find_business(query, lang=lang, region=region))


@server.tool(
    name="gbp_audit",
    description=(
        "Audit a public Google Business Profile. Returns a 0-100 score, a letter grade, per-factor checks "
        "(website, phone, hours, photos, reviews), prioritised recommendations and AI suggestions: an optimised "
        "description, long-tail keywords, Google Post ideas, local FAQs, review reply templates and citation ideas. "
        "Use it when the user asks how their listing is doing or how to improve it. "
        "Identify the business with place_id, or business_name plus city, or a Google Maps gbp_url. "
        f"Costs Google Places lookups and one AI call; {LIMITS}."
    ),
)
def gbp_audit(
    place_id: str | None = None,
    business_name: str | None = None,
    city: str | None = None,
    gbp_url: str | None = None,
) -> dict[str, Any]:
    return _call(
        lambda client: client.gbp_audit(
            place_id=place_id, business_name=business_name, city=city, gbp_url=gbp_url
        )
    )


@server.tool(
    name="gbp_categories",
    description=(
        "Compare a business's Google categories with the categories the competitors ranking for its keywords use. "
        "Returns the client's current categories, aggregated competitor categories, scored add/keep/review "
        "recommendations and an opportunity summary. Use it when choosing a primary or additional category. "
        "Pass 1 to 10 keywords, and identify the business with place_id or business_name plus city. "
        f"Costs several Google Places searches per keyword; {LIMITS}."
    ),
)
def gbp_categories(
    keywords: list[str],
    place_id: str | None = None,
    business_name: str | None = None,
    city: str | None = None,
    region_code: str | None = None,
    language_code: str | None = None,
    services_text: str | None = None,
) -> dict[str, Any]:
    return _call(
        lambda client: client.gbp_categories(
            keywords=keywords,
            place_id=place_id,
            business_name=business_name,
            city=city,
            region_code=region_code,
            language_code=language_code,
            services_text=services_text,
        )
    )


@server.tool(
    name="rank_grid",
    description=(
        "Check where a business ranks on Google Maps for one keyword across a grid of nearby search locations. "
        "Returns the business, every grid point with its rank (null when it is not in the top 20), a summary "
        "(average, best and worst rank, visible share, top-3 share) and the competitors that outrank it. "
        "Use it to see how far the business's map visibility reaches. grid_size is 3 or 5, spacing_km is 0.5, 1 or 2. "
        f"This is the most expensive tool: one Places request per cell; 25 for a 5×5. Also, {LIMITS}."
    ),
)
def rank_grid(
    place_id: str,
    keyword: str,
    grid_size: int | None = None,
    spacing_km: float | None = None,
    language_code: str | None = None,
    region_code: str | None = None,
) -> dict[str, Any]:
    return _call(
        lambda client: client.rank_grid(
            place_id=place_id,
            keyword=keyword,
            grid_size=grid_size,
            spacing_km=spacing_km,
            language_code=language_code,
            region_code=region_code,
        )
    )


@server.tool(
    name="ai_visibility",
    description=(
        "Measure how often AI assistants name a business when asked local buyer questions. Returns a 0-100 score, "
        "per-engine mention counts, the queries that were run, the competitors named instead, missing topics and "
        "recommended actions. Use it when the user asks whether AI search knows about their business. "
        f"Costs a batch of AI calls and takes a while; {LIMITS}."
    ),
)
def ai_visibility(business_name: str, city: str, category: str | None = None) -> dict[str, Any]:
    return _call(lambda client: client.ai_visibility(business_name=business_name, city=city, category=category))


@server.tool(
    name="review_reply",
    description=(
        "Draft three public replies to a Google review in the owner's voice, plus tips for handling that review. "
        "Use it when the user pastes a review they need to answer. rating is 1 to 5; tone is professional, friendly, "
        "empathetic or concise; language auto matches the review's language. The replies never invent facts or offers. "
        f"Costs one AI call; {LIMITS}."
    ),
)
def review_reply(
    business_name: str,
    review_text: str,
    rating: int,
    reviewer_name: str | None = None,
    tone: str | None = None,
    language: str | None = None,
    sign_off: str | None = None,
    business_type: str | None = None,
) -> dict[str, Any]:
    return _call(
        lambda client: client.review_reply(
            business_name=business_name,
            review_text=review_text,
            rating=rating,
            reviewer_name=reviewer_name,
            tone=tone,
            language=language,
            sign_off=sign_off,
            business_type=business_type,
        )
    )


@server.tool(
    name="review_link",
    description=(
        "Build the direct Google review link for a place id, the URL that opens the review box straight away. "
        "Use it when the user wants a link to ask customers for reviews. Runs locally and costs nothing."
    ),
)
def review_link(place_id: str) -> dict[str, str]:
    return _call(lambda client: client.review_link(place_id))


@server.tool(
    name="schema_jsonld",
    description=(
        "Build LocalBusiness JSON-LD structured data for a business from its Google profile: schema type, name, url, "
        "telephone, PostalAddress, geo coordinates, opening hours and hasMap. Returns the JSON-LD object to paste "
        "into a script type=\"application/ld+json\" tag. Use it when the user wants schema markup for their website. "
        "Review the output before publishing: it only contains what Google knows about the business. "
        f"Costs one Google Places details request; {LIMITS}."
    ),
)
def schema_jsonld(place_id: str) -> dict[str, Any]:
    return _call(lambda client: client.schema_jsonld(client.place_details(place_id)))


def main() -> None:
    parser = argparse.ArgumentParser(prog="locan-mcp", description="MCP server exposing the Locan local SEO tools.")
    parser.add_argument("--http", action="store_true", help="Serve over streamable HTTP instead of stdio.")
    parser.add_argument("--port", type=int, default=8765, help="Port for --http (default 8765).")
    args = parser.parse_args()
    if args.http:
        server.run("streamable-http", port=args.port)
    else:
        server.run()
