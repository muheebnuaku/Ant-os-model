"""Database tables. The schema itself is created by the Alembic migrations in
``services/api/migrations``, which also install the audit triggers."""

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def _now() -> Any:
    return mapped_column(DateTime(timezone=True), server_default=text("now()"), nullable=False)


class ConfigVersion(Base):
    """Every profile ever activated, keyed by its content hash. Decisions record
    the hash they ran under, so replay can load the exact configuration."""

    __tablename__ = "config_versions"

    config_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    profile: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    profile_canonical: Mapped[str] = mapped_column(Text, nullable=False)
    source_docs: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = _now()
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __table_args__ = (
        Index("one_active_config", "active", unique=True, postgresql_where=text("active")),
    )


class SignalRow(Base):
    __tablename__ = "signals"

    signal_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    nation_id: Mapped[str] = mapped_column(String(8), nullable=False)
    sector: Mapped[str] = mapped_column(Text, nullable=False)
    signal_type: Mapped[str] = mapped_column(Text, nullable=False)
    source_id: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    raw_hash: Mapped[str | None] = mapped_column(Text)
    ingested_by: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        Index("signals_lookup", "nation_id", "sector", "signal_type", "observed_at"),
    )


class DecisionRow(Base):
    """Query projection of recorded decisions. The audit log is authoritative."""

    __tablename__ = "decisions"

    audit_ref: Mapped[str] = mapped_column(String(32), primary_key=True)
    decision_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    audit_seq: Mapped[int] = mapped_column(BigInteger, nullable=False)
    nation_id: Mapped[str] = mapped_column(String(8), nullable=False)
    sector: Mapped[str] = mapped_column(Text, nullable=False)
    validation_state: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    allowed_for_action: Mapped[bool] = mapped_column(Boolean, nullable=False)
    human_escalation_required: Mapped[bool] = mapped_column(Boolean, nullable=False)
    config_hash: Mapped[str] = mapped_column(
        String(64), ForeignKey("config_versions.config_hash"), nullable=False
    )
    decision: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_by: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = _now()


class EscalationRow(Base):
    __tablename__ = "escalations"

    escalation_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    decision_id: Mapped[str | None] = mapped_column(String(32))
    audit_ref: Mapped[str | None] = mapped_column(String(32))
    nation_id: Mapped[str] = mapped_column(String(8), nullable=False)
    sector: Mapped[str] = mapped_column(Text, nullable=False)
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[str] = mapped_column(Text, nullable=False)
    assigned_role: Mapped[str] = mapped_column(Text, nullable=False)
    sla_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reasons: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="open")
    breached_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acknowledged_by: Mapped[str | None] = mapped_column(Text)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by: Mapped[str | None] = mapped_column(Text)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = _now()

    __table_args__ = (
        Index("escalations_queue", "status", "assigned_role", "due_at"),
    )


class AuditEntry(Base):
    """Append-only, hash-chained. ``seq``, ``payload_hash``, ``prev_hash`` and
    ``entry_hash`` are set by the database trigger, never by the application."""

    __tablename__ = "audit_log"

    seq: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    ref: Mapped[str] = mapped_column(Text, nullable=False)
    actor: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False)  # canonical JSON text
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    prev_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    entry_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_at: Mapped[datetime] = _now()

    __table_args__ = (Index("audit_log_ref", "ref"),)


class ApiKey(Base):
    __tablename__ = "api_keys"

    key_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    secret_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    roles: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    nation_id: Mapped[str | None] = mapped_column(String(8))
    created_by: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = _now()
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OutboxRow(Base):
    __tablename__ = "notification_outbox"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event: Mapped[str] = mapped_column(Text, nullable=False)
    ref: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime] = _now()
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _now()
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AnchorRow(Base):
    """Signed checkpoints of the audit chain. Append-only."""

    __tablename__ = "audit_anchors"

    anchor_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    node_id: Mapped[str] = mapped_column(Text, nullable=False)
    up_to_seq: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    head_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    entries: Mapped[int] = mapped_column(BigInteger, nullable=False)
    anchored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    key_id: Mapped[str] = mapped_column(String(32), nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False)  # the exact signed text
    signature: Mapped[str] = mapped_column(Text, nullable=False)  # base64 Ed25519