"""Signed audit anchors (Ed25519).

An anchor signs ``{node_id, up_to_seq, head_hash, entries, anchored_at}``. Each
new anchor is also queued as a notification, so copies leave this database.
Verification trusts only the public keys this node is configured with, never a
key read from the database.

Generate a key pair with ``python -m antos_api.cli generate-anchor-key DIR``.
Keep the private key off the database host where possible.
"""

import base64
import hashlib
import json
from datetime import datetime
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from antos_api import audit, notify
from antos_api.tables import AnchorRow, AuditEntry
from antos_core.hashing import canonical_json


class ChainBroken(RuntimeError):
    pass


class AnchorStatement(BaseModel):
    node_id: str
    up_to_seq: int
    head_hash: str
    entries: int
    anchored_at: datetime


class AnchorReport(BaseModel):
    ok: bool
    anchors_checked: int
    latest_seq: int | None = None
    problems: list[str] = []


def key_id(public_key: Ed25519PublicKey) -> str:
    raw = public_key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return hashlib.sha256(raw).hexdigest()[:16]


def load_private_key(path: Path) -> Ed25519PrivateKey:
    return load_private_key_pem(path.read_bytes(), str(path))


def load_private_key_pem(pem: bytes, source: str = "key") -> Ed25519PrivateKey:
    key = serialization.load_pem_private_key(pem, password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError(f"{source} is not an Ed25519 private key")
    return key


def load_public_key(path: Path) -> Ed25519PublicKey:
    key = serialization.load_pem_public_key(path.read_bytes())
    if not isinstance(key, Ed25519PublicKey):
        raise ValueError(f"{path} is not an Ed25519 public key")
    return key


def generate_key_pair(directory: Path) -> tuple[Path, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    private = Ed25519PrivateKey.generate()
    priv_path, pub_path = directory / "anchor_ed25519.pem", directory / "anchor_ed25519.pub.pem"
    priv_path.write_bytes(private.private_bytes(serialization.Encoding.PEM,
                                                serialization.PrivateFormat.PKCS8,
                                                serialization.NoEncryption()))
    pub_path.write_bytes(private.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    return priv_path, pub_path


async def create_anchor(session: AsyncSession, signer: Ed25519PrivateKey, node_id: str,
                        now: datetime) -> AnchorRow | None:
    """Anchor the current head of the chain. Refuses to sign a broken chain.
    Returns None when nothing was appended since the last anchor."""
    report = await audit.verify_chain(session)
    if not report.ok:
        raise ChainBroken(f"refusing to anchor a broken chain: {report.problem} "
                          f"(seq {report.first_bad_seq})")
    head = await session.scalar(select(AuditEntry).order_by(AuditEntry.seq.desc()).limit(1))
    if head is None:
        return None
    last = await session.scalar(select(AnchorRow.up_to_seq).order_by(AnchorRow.up_to_seq.desc())
                                .limit(1))
    if last is not None:
        # The previous anchor's own "audit.anchored" entry is not news.
        news = await session.scalar(
            select(func.count()).select_from(AuditEntry)
            .where(AuditEntry.seq > last, AuditEntry.event_type != "audit.anchored"))
        if not news:
            return None

    statement = AnchorStatement(node_id=node_id, up_to_seq=head.seq, head_hash=head.entry_hash,
                                entries=report.entries_checked, anchored_at=now)
    text = canonical_json(statement)
    row = AnchorRow(
        anchor_id=f"ANC-{head.entry_hash[:12].upper()}", node_id=node_id, up_to_seq=head.seq,
        head_hash=head.entry_hash, entries=report.entries_checked, anchored_at=now,
        key_id=key_id(signer.public_key()), statement=text,
        signature=base64.b64encode(signer.sign(text.encode("utf-8"))).decode("ascii"),
    )
    session.add(row)
    await session.flush()
    published = {"anchor_id": row.anchor_id, "statement": text, "signature": row.signature,
                 "key_id": row.key_id}
    await audit.append(session, "audit.anchored", row.anchor_id, "system:anchor", published)
    notify.enqueue(session, "audit.anchored", row.anchor_id, published, now)
    return row


async def verify_anchors(session: AsyncSession,
                         trusted: dict[str, Ed25519PublicKey]) -> AnchorReport:
    problems: list[str] = []
    rows = (await session.scalars(select(AnchorRow).order_by(AnchorRow.up_to_seq))).all()
    for row in rows:
        key = trusted.get(row.key_id)
        if key is None:
            problems.append(f"{row.anchor_id}: signed by untrusted key {row.key_id}")
            continue
        try:
            key.verify(base64.b64decode(row.signature), row.statement.encode("utf-8"))
        except (InvalidSignature, ValueError):
            problems.append(f"{row.anchor_id}: signature is invalid")
            continue
        signed = AnchorStatement.model_validate(json.loads(row.statement))
        if (signed.up_to_seq, signed.head_hash) != (row.up_to_seq, row.head_hash):
            problems.append(f"{row.anchor_id}: row does not match its signed statement")
            continue
        entry = await session.get(AuditEntry, signed.up_to_seq)
        if entry is None:
            problems.append(f"{row.anchor_id}: anchored entry {signed.up_to_seq} is missing")
        elif entry.entry_hash != signed.head_hash:
            problems.append(f"{row.anchor_id}: entry {signed.up_to_seq} no longer has the "
                            "anchored hash (history was rewritten)")
    return AnchorReport(ok=not problems, anchors_checked=len(rows),
                        latest_seq=rows[-1].up_to_seq if rows else None, problems=problems)
