"""FastAPI dependencies shared by routers."""

from __future__ import annotations

from fastapi import Request

from .config import Settings
from .quota import QuotaRepo, enforce
from .services.places import PlacesClient


def client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def settings(request: Request) -> Settings:
    return request.app.state.settings


def places(request: Request) -> PlacesClient:
    return request.app.state.places


def quota_repo(request: Request) -> QuotaRepo:
    return request.app.state.quota


async def enforce_tool_quota(request: Request, scope: str, units: int = 1) -> None:
    """Per-IP tool limit plus the shared global tools budget."""
    cfg: Settings = request.app.state.settings
    await enforce(
        request.app.state.quota,
        scope,
        client_ip(request),
        limit_ip=cfg.quota_limits["tool_ip"],
        limit_global=None,
        units=units,
    )
    await enforce(
        request.app.state.quota,
        "tools",
        "global",
        limit_ip=cfg.quota_limits["tools_global"],
        limit_global=None,
        units=units,
    )


async def notify_tool_run(request: Request, tool: str, summary: str, fields: dict | None = None) -> None:
    """Tell the owner a tool was used (never raises)."""
    notifier = getattr(request.app.state, "notifier", None)
    if notifier is not None:
        await notifier.event("tool_run", f"{tool} — {summary}"[:180], {"tool": tool, **(fields or {})}, request)
