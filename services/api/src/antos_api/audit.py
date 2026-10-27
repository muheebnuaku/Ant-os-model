"""Hash-chained audit log.

The database trigger (migration 0001) assigns ``seq`` and computes every hash.
This module appends entries and *independently* recomputes the chain, so a
verifier does not have to trust the code that wrote it.
"""

import hashlib
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import BaseModel
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from antos_api.tables import AuditEntry
from antos_core.hashing import canonical_json

GENESIS = "0" * 64
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


class Appended(BaseModel):
    seq: int
    entry_hash: str


class ChainReport(BaseModel):
    ok: bool
    entries_checked: int
    head_hash: str
    first_bad_seq: int | None = None
    problem: str | None = None


async def append(
    session: AsyncSession, event_type: str, ref: str, actor: str, payload: Any
) -> Appended:
    """Append one entry inside the caller's transaction. The advisory lock the
    trigger takes is held until that transaction ends, so append last."""
    row = (await session.execute(
        insert(AuditEntry)
        .values(event_type=event_type, ref=ref, actor=actor, payload=canonical_json(payload),
                # placeholders; the trigger overwrites all four
                seq=0, payload_hash="", prev_hash="", entry_hash="")
        .returning(AuditEntry.seq, AuditEntry.entry_hash)
    )).one()
    return Appended(seq=row.seq, entry_hash=row.entry_hash)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def expected_entry_hash(entry: AuditEntry, prev_hash: str) -> str:
    created_us = (entry.created_at - _EPOCH) // timedelta(microseconds=1)
    return _sha256("|".join([prev_hash, str(entry.seq), str(created_us), entry.event_type,
                             entry.ref, entry.actor, entry.payload_hash]))


async def _entries(session: AsyncSession, batch: int = 1000) -> AsyncIterator[AuditEntry]:
    last = -1
    while True:
        rows = (await session.scalars(
            select(AuditEntry).where(AuditEntry.seq > last).order_by(AuditEntry.seq).limit(batch)
        )).all()
        if not rows:
            return
        for row in rows:
            yield row
        last = rows[-1].seq


async def verify_chain(session: AsyncSession) -> ChainReport:
    prev, checked = GENESIS, 0
    async for entry in _entries(session):
        problem = None
        if entry.prev_hash != prev:
            problem = "prev_hash does not match the previous entry (entry removed or reordered)"
        elif _sha256(entry.payload) != entry.payload_hash:
            problem = "payload does not match payload_hash (payload altered)"
        elif expected_entry_hash(entry, prev) != entry.entry_hash:
            problem = "entry_hash does not match its contents (metadata altered)"
        if problem:
            return ChainReport(ok=False, entries_checked=checked, head_hash=prev,
                               first_bad_seq=entry.seq, problem=problem)
        prev, checked = entry.entry_hash, checked + 1
    return ChainReport(ok=True, entries_checked=checked, head_hash=prev)


async def load_payload(session: AsyncSession, seq: int) -> tuple[AuditEntry, Any]:
    """Load one entry and check its payload hash before anyone relies on it."""
    entry = await session.get(AuditEntry, seq)
    if entry is None:
        raise LookupError(f"audit entry {seq} not found")
    if _sha256(entry.payload) != entry.payload_hash:
        raise ValueError(f"audit entry {seq} payload does not match its hash")
    return entry, json.loads(entry.payload)
