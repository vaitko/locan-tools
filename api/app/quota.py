"""Daily quota counters. Keys: QUOTA#<scope>#<ip|global>#<YYYY-MM-DD>."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Protocol

from .errors import QuotaExceeded


def today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


class QuotaRepo(Protocol):
    async def incr(self, key: str, ttl_days: int = 2) -> int: ...


class MemoryQuotaRepo:
    def __init__(self) -> None:
        self._counts: dict[str, int] = {}

    async def incr(self, key: str, ttl_days: int = 2) -> int:
        self._counts[key] = self._counts.get(key, 0) + 1
        return self._counts[key]


class NoQuotaRepo:
    async def incr(self, key: str, ttl_days: int = 2) -> int:
        return 0


class DynamoQuotaRepo:
    """Atomic ADD counter on a single-table DynamoDB (PK string, ttl number)."""

    def __init__(self, table_name: str, region: str) -> None:
        import boto3  # local import keeps tests free of boto3 session creation

        self._table = boto3.resource("dynamodb", region_name=region).Table(table_name)

    async def incr(self, key: str, ttl_days: int = 2) -> int:
        ttl = int(time.time()) + ttl_days * 86400

        def _update() -> int:
            resp = self._table.update_item(
                Key={"PK": key},
                UpdateExpression="ADD #c :one SET #t = if_not_exists(#t, :ttl)",
                ExpressionAttributeNames={"#c": "count", "#t": "ttl"},
                ExpressionAttributeValues={":one": 1, ":ttl": ttl},
                ReturnValues="UPDATED_NEW",
            )
            return int(resp["Attributes"]["count"])

        return await asyncio.to_thread(_update)


async def enforce(
    repo: QuotaRepo,
    scope: str,
    ip: str,
    limit_ip: int,
    limit_global: int | None = None,
    units: int = 1,
) -> None:
    """Consume `units` from the per-IP (and optional global) daily budget; raise 429 when exceeded."""
    day = today_utc()
    for _ in range(units):
        count = await repo.incr(f"QUOTA#{scope}#{ip}#{day}")
        if count > limit_ip:
            raise QuotaExceeded(scope)
        if limit_global is not None:
            gcount = await repo.incr(f"QUOTA#{scope}#global#{day}")
            if gcount > limit_global:
                raise QuotaExceeded(scope)
