"""Notifications through a transactional outbox.

``enqueue`` writes in the caller's transaction; the worker's ``deliver_pending``
sends with retries and exponential backoff. A webhook receiver (SMS gateway,
email bridge, chat) routes by ``assigned_role``. Payloads carry no signal data.
"""

import hashlib
import hmac
import json
import logging
from datetime import datetime, timedelta
from typing import Any, Protocol

import httpx
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from antos_api.tables import OutboxRow
from antos_core.hashing import canonical_json

log = logging.getLogger("antos.notify")

MAX_ATTEMPTS = 8
MAX_BACKOFF = timedelta(hours=1)


def enqueue(session: AsyncSession, event: str, ref: str, payload: Any, now: datetime) -> None:
    session.add(OutboxRow(event=event, ref=ref, payload=json.loads(canonical_json(payload)),
                          status="pending", attempts=0, next_attempt_at=now))


class Notifier(Protocol):
    async def send(self, event: str, ref: str, payload: dict[str, Any]) -> None: ...


class LogNotifier:
    """Default when no webhook is configured: the event is only logged."""

    async def send(self, event: str, ref: str, payload: dict[str, Any]) -> None:
        log.warning("notification %s %s %s", event, ref, canonical_json(payload))


class WebhookNotifier:
    def __init__(self, url: str, secret: str | None, *,
                 http: httpx.AsyncClient | None = None) -> None:
        self.url, self.secret = url, secret
        self.http = http or httpx.AsyncClient(timeout=10)

    def signature(self, body: bytes) -> str:
        assert self.secret
        return "sha256=" + hmac.new(self.secret.encode(), body, hashlib.sha256).hexdigest()

    async def send(self, event: str, ref: str, payload: dict[str, Any]) -> None:
        body = canonical_json({"event": event, "ref": ref, "payload": payload}).encode()
        headers = {"Content-Type": "application/json", "X-Antos-Event": event}
        if self.secret:
            headers["X-Antos-Signature"] = self.signature(body)
        response = await self.http.post(self.url, content=body, headers=headers)
        response.raise_for_status()


class DeliveryReport(BaseModel):
    delivered: int = 0
    retrying: int = 0
    failed: int = 0


async def deliver_pending(sessions: async_sessionmaker[AsyncSession], notifier: Notifier,
                          now: datetime, batch: int = 50) -> DeliveryReport:
    report = DeliveryReport()
    async with sessions.begin() as session:
        rows = (await session.scalars(
            select(OutboxRow)
            .where(OutboxRow.status == "pending", OutboxRow.next_attempt_at <= now)
            .order_by(OutboxRow.id).limit(batch).with_for_update(skip_locked=True)
        )).all()
        for row in rows:
            try:
                await notifier.send(row.event, row.ref, row.payload)
            except Exception as exc:
                row.attempts += 1
                row.last_error = f"{type(exc).__name__}: {exc}"[:500]
                if row.attempts >= MAX_ATTEMPTS:
                    row.status = "failed"
                    report.failed += 1
                else:
                    row.next_attempt_at = now + min(timedelta(minutes=2 ** row.attempts),
                                                    MAX_BACKOFF)
                    report.retrying += 1
            else:
                row.status, row.delivered_at = "delivered", now
                report.delivered += 1
    return report
