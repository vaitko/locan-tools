"""Email capture, one-click unsubscribe and free tool requests.

Storage is a single DynamoDB table (PK): SUB#<email> for subscribers, REQ#<id> for tool requests.
Both the store and the mailer are pluggable (Null* in dev/tests).
"""

from __future__ import annotations

import asyncio
import secrets
import time
from typing import Any, Protocol

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr, Field

from ..config import Settings
from ..deps import client_ip, quota_repo, settings
from ..errors import ApiError
from ..quota import QuotaRepo, enforce
from ..services.notify import (
    Notifier,
    confirm_email,
    confirm_url,
    tool_request_email,
    unsubscribe_url,
    verify_confirm_token,
    verify_unsubscribe_token,
)

router = APIRouter()


# ── models ────────────────────────────────────────────────────────────────────


class SubscribeRequest(BaseModel):
    email: EmailStr
    source: str = Field(default="site", max_length=60)


class ToolRequest(BaseModel):
    email: EmailStr
    request: str = Field(min_length=10, max_length=2000)
    business: str | None = Field(default=None, max_length=200)
    website: str | None = Field(default=None, max_length=300)
    source: str = Field(default="home", max_length=60)


# ── storage ports ─────────────────────────────────────────────────────────────


class SubscriberStore(Protocol):
    async def put(self, email: str, source: str, ip: str) -> str: ...
    async def confirm(self, email: str) -> bool: ...
    async def unsubscribe(self, email: str) -> bool: ...
    async def put_request(self, item: dict[str, Any]) -> None: ...


class NullStore:
    def __init__(self) -> None:
        self.subscribers: dict[str, dict[str, Any]] = {}
        self.requests: list[dict[str, Any]] = []

    async def put(self, email: str, source: str, ip: str) -> str:
        """Upsert as pending unless already active; returns the previous status ('' when new)."""
        key = email.lower()
        prev = self.subscribers.get(key, {}).get("status", "")
        status = "active" if prev == "active" else "pending"
        self.subscribers[key] = {"email": email, "source": source, "ip": ip, "status": status}
        return prev

    async def confirm(self, email: str) -> bool:
        item = self.subscribers.get(email.lower())
        if not item:
            return False
        item["status"] = "active"
        item["confirmedAt"] = int(time.time())
        return True

    async def unsubscribe(self, email: str) -> bool:
        item = self.subscribers.get(email.lower())
        if not item:
            return False
        item["status"] = "unsubscribed"
        return True

    async def put_request(self, item: dict[str, Any]) -> None:
        self.requests.append(item)


class DynamoSubscriberStore:
    def __init__(self, table_name: str, region: str) -> None:
        import boto3

        self._table = boto3.resource("dynamodb", region_name=region).Table(table_name)

    async def put(self, email: str, source: str, ip: str) -> str:
        """Upsert as pending unless already active; returns the previous status ('' when new)."""
        key = f"SUB#{email.lower()}"
        now = int(time.time())

        def _put() -> str:
            existing = self._table.get_item(Key={"PK": key}).get("Item") or {}
            prev = existing.get("status", "")
            item = {
                **existing,
                "PK": key,
                "type": "subscriber",
                "email": email,
                "source": source,
                "ip": ip,
                "status": "active" if prev == "active" else "pending",
                "createdAt": existing.get("createdAt", now),
                "updatedAt": now,
            }
            self._table.put_item(Item=item)
            return prev

        return await asyncio.to_thread(_put)

    async def _set_status(self, email: str, status: str, extra: dict[str, Any] | None = None) -> bool:
        key = f"SUB#{email.lower()}"

        def _update() -> bool:
            if not self._table.get_item(Key={"PK": key}).get("Item"):
                return False
            names = {"#s": "status"}
            values: dict[str, Any] = {":s": status, ":t": int(time.time())}
            expr = "SET #s = :s, updatedAt = :t"
            for i, (k, v) in enumerate((extra or {}).items()):
                names[f"#e{i}"] = k
                values[f":e{i}"] = v
                expr += f", #e{i} = :e{i}"
            self._table.update_item(
                Key={"PK": key}, UpdateExpression=expr, ExpressionAttributeNames=names, ExpressionAttributeValues=values
            )
            return True

        return await asyncio.to_thread(_update)

    async def confirm(self, email: str) -> bool:
        return await self._set_status(email, "active", {"confirmedAt": int(time.time())})

    async def unsubscribe(self, email: str) -> bool:
        return await self._set_status(email, "unsubscribed")

    async def put_request(self, item: dict[str, Any]) -> None:
        await asyncio.to_thread(self._table.put_item, Item=item)


def store(request: Request) -> SubscriberStore:
    return request.app.state.subscribers


def notifier(request: Request) -> Notifier:
    return request.app.state.notifier


def _api_base(cfg: Settings) -> str:
    return cfg.api_base_url


# ── routes ────────────────────────────────────────────────────────────────────


@router.post("/subscribe")
async def subscribe(
    request: Request,
    body: SubscribeRequest,
    cfg: Settings = Depends(settings),
    repo: QuotaRepo = Depends(quota_repo),
    subscribers: SubscriberStore = Depends(store),
    notify: Notifier = Depends(notifier),
) -> dict:
    """Double opt-in: store as pending and send a confirmation link; already-confirmed addresses get nothing new."""
    ip = client_ip(request)
    await enforce(repo, "subscribe", ip, limit_ip=8, limit_global=500)
    email = str(body.email)
    prev = await subscribers.put(email, body.source, ip)
    confirmed = prev == "active"
    if not confirmed:
        subject, text, html = confirm_email(
            cfg.site_url,
            confirm_url(_api_base(cfg), cfg.unsubscribe_secret, email),
            unsubscribe_url(_api_base(cfg), cfg.unsubscribe_secret, email),
        )
        await notify.send_user(email, subject, text, html)
    await notify.event(
        "subscribe",
        f"{email} ({body.source})",
        {"email": email, "source": body.source, "status": "active" if confirmed else "pending", "previous": prev or "new"},
        request,
    )
    return {"ok": True, "status": "confirmed" if confirmed else "pending"}


@router.get("/confirm")
async def confirm(
    request: Request,
    email: str = Query(min_length=3, max_length=254),
    token: str = Query(min_length=8, max_length=64),
    cfg: Settings = Depends(settings),
    subscribers: SubscriberStore = Depends(store),
    notify: Notifier = Depends(notifier),
) -> RedirectResponse:
    """Double opt-in link target. Redirects to the site's confirmation page."""
    ok = verify_confirm_token(cfg.unsubscribe_secret, email, token)
    found = await subscribers.confirm(email) if ok else False
    status = "ok" if ok and found else "invalid"
    if ok and found:
        await notify.event("confirm", email, {"email": email}, request)
    return RedirectResponse(url=f"{cfg.site_url}/confirmed/?status={status}", status_code=302)


@router.get("/unsubscribe")
async def unsubscribe(
    request: Request,
    email: str = Query(min_length=3, max_length=254),
    token: str = Query(min_length=8, max_length=64),
    cfg: Settings = Depends(settings),
    subscribers: SubscriberStore = Depends(store),
    notify: Notifier = Depends(notifier),
) -> RedirectResponse:
    """One-click unsubscribe link target. Always redirects to the site so the visitor lands on a page."""
    ok = verify_unsubscribe_token(cfg.unsubscribe_secret, email, token)
    found = await subscribers.unsubscribe(email) if ok else False
    status = "ok" if ok and found else "invalid"
    if ok and found:
        await notify.event("unsubscribe", email, {"email": email}, request)
    return RedirectResponse(url=f"{cfg.site_url}/unsubscribe/?status={status}", status_code=302)


@router.post("/tool-requests")
async def tool_requests(
    request: Request,
    body: ToolRequest,
    cfg: Settings = Depends(settings),
    repo: QuotaRepo = Depends(quota_repo),
    subscribers: SubscriberStore = Depends(store),
    notify: Notifier = Depends(notifier),
) -> dict:
    ip = client_ip(request)
    await enforce(repo, "tool_request", ip, limit_ip=5, limit_global=300)
    email = str(body.email)
    req_id = f"{time.strftime('%Y%m%d', time.gmtime())}-{secrets.token_hex(4)}"
    item = {
        "PK": f"REQ#{req_id}",
        "type": "tool_request",
        "id": req_id,
        "email": email,
        "request": body.request.strip(),
        "business": (body.business or "").strip(),
        "website": (body.website or "").strip(),
        "source": body.source,
        "ip": ip,
        "status": "new",
        "createdAt": int(time.time()),
    }
    await subscribers.put_request(item)
    prev = await subscribers.put(email, f"tool-request:{body.source}", ip)
    subject, text, html = tool_request_email(
        cfg.site_url,
        body.request,
        confirm_url(_api_base(cfg), cfg.unsubscribe_secret, email),
        unsubscribe_url(_api_base(cfg), cfg.unsubscribe_secret, email),
    )
    await notify.send_user(email, subject, text, html)
    await notify.event(
        "tool_request",
        f"{req_id} from {email}",
        {"id": req_id, "email": email, "business": item["business"], "website": item["website"], "request": item["request"], "subscriber": prev or "new (pending)"},
        request,
    )
    return {"ok": True, "id": req_id}


def not_found() -> ApiError:  # kept for symmetry with other routers' error helpers
    return ApiError(404, "not_found", "Not found")
