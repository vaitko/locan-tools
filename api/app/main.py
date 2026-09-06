"""Application factory. Routers register themselves here; tool routers are added by later tasks."""

from __future__ import annotations

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import Settings
from .errors import install_error_handlers
from .quota import DynamoQuotaRepo, MemoryQuotaRepo
from .routers import health, places, subscribe
from .routers.subscribe import DynamoSubscriberStore, NullStore
from .services import llm
from .services.notify import Notifier, NullMailer, SesMailer
from .services.places import PlacesClient

API_PREFIX = "/api"


def create_app(cfg: Settings | None = None) -> FastAPI:
    cfg = cfg or Settings.from_env()
    app = FastAPI(title="Locan API", version=health.VERSION, docs_url=None if cfg.is_prod else "/api/docs", redoc_url=None)
    app.state.settings = cfg

    http = httpx.AsyncClient(timeout=httpx.Timeout(cfg.upstream_timeout_s))
    app.state.http = http
    app.state.places = PlacesClient(cfg.google_places_api_key, http)
    llm.configure(cfg, http)

    if cfg.quota_table:
        app.state.quota = DynamoQuotaRepo(cfg.quota_table, cfg.aws_region)
        app.state.subscribers = DynamoSubscriberStore(cfg.quota_table, cfg.aws_region)
        mailer = SesMailer(cfg.aws_region, cfg.alert_from) if cfg.alert_from else NullMailer()
    else:
        app.state.quota = MemoryQuotaRepo()
        app.state.subscribers = NullStore()
        mailer = NullMailer()
    app.state.notifier = Notifier(mailer, cfg.alert_email, cfg.site_url, set(cfg.notify_events))

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.allowed_origins,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
        max_age=600,
    )

    # Only enforced in prod so a local .env that also holds the secret (deploy.sh writes it) doesn't block dev.
    if cfg.origin_verify_secret and cfg.is_prod:
        secret = cfg.origin_verify_secret

        @app.middleware("http")
        async def _origin_verify(request: Request, call_next):
            if request.url.path != f"{API_PREFIX}/health" and request.headers.get("x-origin-verify") != secret:
                return JSONResponse(status_code=403, content={"error": "Forbidden", "code": "forbidden"})
            return await call_next(request)

    install_error_handlers(app)

    app.include_router(health.router, prefix=API_PREFIX)
    app.include_router(places.router, prefix=API_PREFIX)
    app.include_router(subscribe.router, prefix=API_PREFIX)
    _include_tool_routers(app)

    @app.on_event("shutdown")
    async def _close_http() -> None:  # pragma: no cover
        await http.aclose()

    return app


def _include_tool_routers(app: FastAPI) -> None:
    """Tool routers are optional modules so the foundation can be tested before they exist."""
    import importlib

    for name in ("gbp_optimizer", "category_optimizer", "ai_visibility", "rank_checker", "review_response"):
        try:
            module = importlib.import_module(f"app.routers.{name}")
        except ModuleNotFoundError as exc:
            if exc.name and exc.name.endswith(name):
                continue
            raise
        app.include_router(module.router, prefix=f"{API_PREFIX}/tools")


app = create_app()
