from __future__ import annotations

import json
from typing import Any, Callable

import httpx
import typer
from rich.console import Console
from rich.table import Table

from .client import LocanApiError, LocanClient, make_client

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Local SEO tools for Google Business Profiles, powered by the Locan API.",
)

_state = {"pretty": False}
_console = Console()
_errors = Console(stderr=True)


@app.callback()
def root(
    pretty: bool = typer.Option(
        False,
        "--pretty",
        help="Render a compact human-readable table instead of JSON.",
    ),
) -> None:
    _state["pretty"] = pretty


@app.command("find-business", help="Look up a business on Google and print matching place ids.")
def find_business(
    query: str = typer.Argument(..., help="Business name, optionally with a city."),
    lang: str = typer.Option(None, "--lang", help="Language code for the suggestions, for example lt."),
    region: str = typer.Option(None, "--region", help="Two-letter region code to bias the search, for example LT."),
) -> None:
    _run(lambda client: client.find_business(query, lang=lang, region=region))


@app.command("gbp-audit", help="Score a public Google Business Profile and get AI improvement suggestions.")
def gbp_audit(
    place_id: str = typer.Option(None, "--place-id", help="Google place id, from find-business."),
    business_name: str = typer.Option(None, "--business-name", help="Business name, used with --city."),
    city: str = typer.Option(None, "--city", help="City the business operates in."),
    gbp_url: str = typer.Option(None, "--gbp-url", help="Google Maps or Business Profile URL."),
) -> None:
    _run(
        lambda client: client.gbp_audit(
            place_id=place_id, business_name=business_name, city=city, gbp_url=gbp_url
        )
    )


@app.command("gbp-categories", help="Compare your Google categories with the competitors ranking for your keywords.")
def gbp_categories(
    keyword: list[str] = typer.Option(
        None, "--keyword", help="Keyword to analyse; repeat the option for up to 10 keywords."
    ),
    place_id: str = typer.Option(None, "--place-id", help="Google place id, from find-business."),
    business_name: str = typer.Option(None, "--business-name", help="Business name, used with --city."),
    city: str = typer.Option(None, "--city", help="City the business operates in."),
    region_code: str = typer.Option(None, "--region-code", help="Two-letter region code, for example LT."),
    language_code: str = typer.Option(None, "--language-code", help="Language code for the search, for example lt."),
    services_text: str = typer.Option(None, "--services-text", help="Services or products the business offers."),
) -> None:
    _run(
        lambda client: client.gbp_categories(
            keywords=list(keyword or []),
            place_id=place_id,
            business_name=business_name,
            city=city,
            region_code=region_code,
            language_code=language_code,
            services_text=services_text,
        )
    )


@app.command("rank-grid", help="Check Google Maps rankings for one keyword across a grid of nearby locations.")
def rank_grid(
    place_id: str = typer.Option(..., "--place-id", help="Google place id, from find-business."),
    keyword: str = typer.Option(..., "--keyword", help="Search keyword to rank for."),
    grid_size: int = typer.Option(None, "--grid-size", help="Grid width: 3 or 5."),
    spacing_km: float = typer.Option(None, "--spacing-km", help="Distance between grid points in km: 0.5, 1 or 2."),
    language_code: str = typer.Option(None, "--language-code", help="Language code for the search, for example lt."),
    region_code: str = typer.Option(None, "--region-code", help="Two-letter region code, for example LT."),
) -> None:
    _run(
        lambda client: client.rank_grid(
            place_id=place_id,
            keyword=keyword,
            grid_size=grid_size,
            spacing_km=spacing_km,
            language_code=language_code,
            region_code=region_code,
        )
    )


@app.command("ai-visibility", help="Measure how often AI assistants name a business for local buyer queries.")
def ai_visibility(
    business_name: str = typer.Option(..., "--business-name", help="Business name as customers know it."),
    city: str = typer.Option(..., "--city", help="City the business operates in."),
    category: str = typer.Option(None, "--category", help="Business category; detected automatically when omitted."),
) -> None:
    _run(lambda client: client.ai_visibility(business_name=business_name, city=city, category=category))


@app.command("review-reply", help="Draft three public replies to a Google review in the owner's voice.")
def review_reply(
    business_name: str = typer.Option(..., "--business-name", help="Business name as it appears on Google."),
    review_text: str = typer.Option(..., "--review-text", help="The review to reply to."),
    rating: int = typer.Option(..., "--rating", help="Star rating of the review, 1 to 5."),
    reviewer_name: str = typer.Option(None, "--reviewer-name", help="Reviewer's first name."),
    tone: str = typer.Option(None, "--tone", help="professional, friendly, empathetic or concise."),
    language: str = typer.Option(None, "--language", help="Reply language; auto matches the review's language."),
    sign_off: str = typer.Option(None, "--sign-off", help="Sign-off appended to every reply."),
    business_type: str = typer.Option(None, "--business-type", help="Business type, for example dentist."),
) -> None:
    _run(
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


@app.command("review-link", help="Build the direct Google review link for a place id. No API call.")
def review_link(place_id: str = typer.Argument(..., help="Google place id, from find-business.")) -> None:
    _run(lambda client: client.review_link(place_id))


@app.command("schema-jsonld", help="Build LocalBusiness JSON-LD from a business's Google profile.")
def schema_jsonld(place_id: str = typer.Argument(..., help="Google place id, from find-business.")) -> None:
    _run(lambda client: client.schema_jsonld(client.place_details(place_id)))


def _run(call: Callable[[LocanClient], Any]) -> None:
    client = make_client()
    try:
        data = call(client)
    except LocanApiError as exc:
        _errors.print(f"error: {exc.message} ({exc.code})", highlight=False, soft_wrap=True)
        raise typer.Exit(1)
    except httpx.HTTPError:
        _errors.print(f"error: could not reach {client.base_url}", highlight=False, soft_wrap=True)
        raise typer.Exit(1)
    finally:
        client.close()
    _emit(data)


def _emit(data: Any) -> None:
    if _state["pretty"]:
        _render(data)
    else:
        typer.echo(json.dumps(data, indent=2, ensure_ascii=False))


def _render(data: Any) -> None:
    if isinstance(data, list) and data and all(isinstance(row, dict) for row in data):
        columns = list(dict.fromkeys(key for row in data for key in row))
        table = Table(show_header=True, header_style="bold")
        for column in columns:
            table.add_column(column)
        for row in data:
            table.add_row(*(_cell(row.get(column)) for column in columns))
        _console.print(table)
    elif isinstance(data, dict):
        table = Table(show_header=False, box=None)
        table.add_column("field", style="bold")
        table.add_column("value")
        for key, value in data.items():
            table.add_row(key, _cell(value))
        _console.print(table)
    else:
        _console.print(_cell(data))


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def main() -> None:
    app()
