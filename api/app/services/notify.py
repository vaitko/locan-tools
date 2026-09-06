"""Owner notifications + transactional e-mail (SES). Every platform event ends up in the owner's inbox.

Event kinds: tool_run, error, quota, subscribe, unsubscribe, tool_request. Filter with NOTIFY_EVENTS (csv).
Sending never raises into request handlers — failures are logged.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import time
from typing import Any, Protocol

from fastapi import Request

log = logging.getLogger("locan.notify")

ALL_EVENTS = ("tool_run", "error", "quota", "subscribe", "confirm", "unsubscribe", "tool_request")


class Mailer(Protocol):
    async def send(self, to: str, subject: str, text: str, html: str | None = None) -> None: ...


class NullMailer:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    async def send(self, to: str, subject: str, text: str, html: str | None = None) -> None:
        self.sent.append({"to": to, "subject": subject, "text": text, "html": html})
        log.info("mail (dev, not sent) to=%s subject=%s", to, subject)


class SesMailer:
    def __init__(self, region: str, sender: str) -> None:
        import boto3

        self._ses = boto3.client("sesv2", region_name=region)
        self._sender = sender

    async def send(self, to: str, subject: str, text: str, html: str | None = None) -> None:
        body: dict[str, Any] = {"Text": {"Data": text}}
        if html:
            body["Html"] = {"Data": html}

        def _send() -> None:
            self._ses.send_email(
                FromEmailAddress=self._sender,
                Destination={"ToAddresses": [to]},
                Content={"Simple": {"Subject": {"Data": subject}, "Body": body}},
            )

        await asyncio.to_thread(_send)


class Notifier:
    def __init__(self, mailer: Mailer, owner_email: str, site_url: str, events: set[str] | None = None) -> None:
        self.mailer = mailer
        self.owner_email = owner_email
        self.site_url = site_url.rstrip("/")
        self.events = events if events is not None else set(ALL_EVENTS)

    @staticmethod
    def request_meta(request: Request | None) -> dict[str, str]:
        if request is None:
            return {}
        from ..deps import client_ip

        return {
            "path": request.url.path,
            "ip": client_ip(request),
            "country": request.headers.get("cloudfront-viewer-country", "") or "",
            "user_agent": (request.headers.get("user-agent") or "")[:160],
            "referer": request.headers.get("referer", "") or "",
        }

    async def event(self, kind: str, title: str, fields: dict[str, Any] | None = None, request: Request | None = None) -> None:
        """E-mail the owner about one platform event. Never raises."""
        if kind not in self.events or not self.owner_email:
            return
        lines = [f"{k}: {v}" for k, v in (fields or {}).items() if v not in (None, "", [], {})]
        meta = self.request_meta(request)
        lines += [f"{k}: {v}" for k, v in meta.items() if v]
        lines.append(f"time: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}")
        subject = f"[locan] {kind}: {title}"[:200]
        try:
            await self.mailer.send(self.owner_email, subject, "\n".join(lines))
        except Exception as exc:  # noqa: BLE001 — notifications must never break a request
            log.warning("owner notification failed (%s): %s", kind, exc)

    async def send_user(self, to: str, subject: str, text: str, html: str | None = None) -> None:
        try:
            await self.mailer.send(to, subject, text, html)
        except Exception as exc:  # noqa: BLE001
            log.warning("user e-mail failed to=%s: %s", to, exc)


# ── signed e-mail links (one-click unsubscribe, double opt-in confirm) ────────────


def _token(secret: str, purpose: str, email: str) -> str:
    return hmac.new(secret.encode(), f"{purpose}:{email.strip().lower()}".encode(), hashlib.sha256).hexdigest()[:32]


def unsubscribe_token(secret: str, email: str) -> str:
    return _token(secret, "unsubscribe", email)


def confirm_token(secret: str, email: str) -> str:
    return _token(secret, "confirm", email)


def verify_unsubscribe_token(secret: str, email: str, token: str) -> bool:
    return hmac.compare_digest(unsubscribe_token(secret, email), (token or "").strip())


def verify_confirm_token(secret: str, email: str, token: str) -> bool:
    return hmac.compare_digest(confirm_token(secret, email), (token or "").strip())


def _signed_url(api_base: str, path: str, secret: str, email: str, token: str) -> str:
    from urllib.parse import urlencode

    return f"{api_base.rstrip('/')}/{path}?" + urlencode({"email": email.strip().lower(), "token": token})


def unsubscribe_url(api_base: str, secret: str, email: str) -> str:
    return _signed_url(api_base, "unsubscribe", secret, email, unsubscribe_token(secret, email))


def confirm_url(api_base: str, secret: str, email: str) -> str:
    return _signed_url(api_base, "confirm", secret, email, confirm_token(secret, email))


# ── transactional templates (plain text first; HTML mirrors it) ───────────────


def confirm_email(site_url: str, confirm: str, unsub: str) -> tuple[str, str, str]:
    subject = "Confirm your email — Locan free tool updates"
    text = (
        "One click to confirm you want updates from Locan:\n"
        f"{confirm}\n\n"
        "What you'll get: one short email when a new free local SEO tool ships, when a tool you used improves, "
        "or when a guide gets a major update. Nothing to buy, ever.\n\n"
        f"Browse the current tools: {site_url}/tools/\n"
        f"Ask for a tool that doesn't exist yet (built for free, usually within 3 days): {site_url}/request-a-tool/\n\n"
        "If you didn't request this, ignore this email — nothing will be sent without confirmation.\n"
        f"Unsubscribe with one click: {unsub}\n"
    )
    return subject, text, _html(text)


def tool_request_email(site_url: str, request_text: str, confirm: str, unsub: str) -> tuple[str, str, str]:
    subject = "We got your tool request — expect an email within 3 days"
    text = (
        "Thanks — your request reached a human.\n\n"
        f"What you asked for:\n> {request_text.strip()}\n\n"
        "What happens next: we build it for free, test it, and email you the link when it is live — usually within "
        "3 days. If we need a detail, we'll reply to this email.\n\n"
        f"Want to hear about every new free tool, not just yours? Confirm with one click: {confirm}\n\n"
        f"Current tools while you wait: {site_url}/tools/\n\n"
        f"Unsubscribe with one click: {unsub}\n"
    )
    return subject, text, _html(text)


def _html(text: str) -> str:
    import html as _h
    import re

    escaped = _h.escape(text)
    escaped = re.sub(r"(https?://[^\s]+)", r'<a href="\1" style="color:#141413">\1</a>', escaped)
    paragraphs = "".join(f"<p style='margin:0 0 14px'>{p.replace(chr(10), '<br>')}</p>" for p in escaped.split("\n\n"))
    return (
        "<div style='font-family:Inter,Helvetica,Arial,sans-serif;font-size:15px;line-height:1.6;color:#141413;"
        "background:#f5f3ec;padding:28px'><div style='max-width:560px;margin:0 auto;background:#fff;border:1px solid #e3dfd3;"
        f"border-radius:16px;padding:28px'>{paragraphs}"
        "<p style='margin:18px 0 0;font-size:12px;color:#5f5e5a'>Locan — free local SEO tools. No account, no card, free forever.</p>"
        "</div></div>"
    )
