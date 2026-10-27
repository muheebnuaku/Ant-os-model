"""Platform operations: config versions, ingest, decisions, replay, escalations.

Each operation that changes state writes an audit entry in the same
transaction, as the last statement before commit (the audit trigger holds a
lock until the transaction ends).
"""

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

import yaml
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from antos_api import audit, notify
from antos_api.auth import Principal, Rbac
from antos_api.gateway import ModelGateway
from antos_api.tables import ConfigVersion, DecisionRow, EscalationRow, SignalRow
from antos_core import AuditRecord, DecisionRequest, Profile, run
from antos_core import replay as replay_decision
from antos_core.config import build_profile
from antos_core.contracts import (
    EcologyInput,
    EscalationPriority,
    HaeInput,
    InclusionInput,
    LocalFitInput,
    Signal,
    SignalInput,
)
from antos_core.engines.escalation import EscalationItem, EscalationReason
from antos_core.engines.signals import assess_signal, normalize_signal
from antos_core.hashing import canonical_json, short_id
from antos_core.loop import ENGINE_VERSION

# Tolerated clock skew for a source's observed_at in the future.
MAX_FUTURE_SKEW = timedelta(minutes=5)


class Forbidden(Exception):
    pass


class NotFound(Exception):
    pass


class Conflict(Exception):
    pass


# ── Config versions ──────────────────────────────────────────


class ConfigStore:
    """Profiles by content hash. Versions are immutable, so caching is safe."""

    def __init__(self) -> None:
        self._cache: dict[str, Profile] = {}

    async def get(self, session: AsyncSession, config_hash: str) -> Profile:
        if config_hash in self._cache:
            return self._cache[config_hash]
        row = await session.get(ConfigVersion, config_hash)
        if row is None:
            raise NotFound(f"config version {config_hash} not found")
        profile = Profile.model_validate(json.loads(row.profile_canonical))
        if profile.config_hash != config_hash:
            raise ValueError(f"stored config {config_hash} does not match its hash")
        self._cache[config_hash] = profile
        return profile

    async def active(self, session: AsyncSession) -> tuple[str, Profile]:
        config_hash = await session.scalar(
            select(ConfigVersion.config_hash).where(ConfigVersion.active)
        )
        if config_hash is None:
            raise NotFound("no active configuration; run bootstrap")
        return config_hash, await self.get(session, config_hash)

    async def activate(self, session: AsyncSession, *, manifest_doc: dict[str, Any],
                       packs_doc: dict[str, Any], rationale: str, actor: str) -> str:
        if not rationale.strip():
            raise ValueError("a recalibration rationale is required")
        profile = build_profile(manifest_doc, packs_doc)  # validates before anything is stored
        config_hash = profile.config_hash
        await session.execute(update(ConfigVersion).where(ConfigVersion.active)
                              .values(active=False))
        await session.execute(
            pg_insert(ConfigVersion)
            .values(config_hash=config_hash, profile=json.loads(canonical_json(profile)),
                    profile_canonical=canonical_json(profile),
                    source_docs={"manifest": manifest_doc, "sector_packs": packs_doc},
                    rationale=rationale, created_by=actor, active=True)
            .on_conflict_do_update(index_elements=[ConfigVersion.config_hash],
                                   set_={"active": True})
        )
        await audit.append(session, "config.activated", config_hash, actor,
                           {"config_hash": config_hash, "rationale": rationale,
                            "manifest_version": profile.manifest.version})
        self._cache[config_hash] = profile
        return config_hash


async def bootstrap(session: AsyncSession, store: ConfigStore, profile_dir: Path) -> str:
    """Activate the profile on disk if the database has no active config yet."""
    current = await session.scalar(select(ConfigVersion.config_hash).where(ConfigVersion.active))
    if current is not None:
        return current
    docs = {name: yaml.safe_load((profile_dir / f"{name}.yaml").read_text(encoding="utf-8"))
            for name in ("manifest", "sector_packs")}
    return await store.activate(session, manifest_doc=docs["manifest"],
                                packs_doc=docs["sector_packs"],
                                rationale="Bootstrap from profile directory", actor="system")


# ── Runtime ──────────────────────────────────────────────────


@dataclass
class Runtime:
    sessions: async_sessionmaker[AsyncSession]
    rbac: Rbac
    gateway: ModelGateway
    configs: ConfigStore = field(default_factory=ConfigStore)
    clock: Callable[[], datetime] = field(default=lambda: datetime.now(UTC))
    node_id: str = "gh-pilot-1"
    anchor_signer: Ed25519PrivateKey | None = None
    # Public keys trusted to have signed anchors, by key id.
    anchor_keys: dict[str, Ed25519PublicKey] = field(default_factory=dict)


def check_nation(principal: Principal, nation_id: str) -> None:
    if principal.nation_id is not None and principal.nation_id != nation_id:
        raise Forbidden(f"caller is bound to nation {principal.nation_id}, not {nation_id}")


# ── Signals ──────────────────────────────────────────────────


class IngestResult(BaseModel):
    signal_ref: str
    accepted: bool
    duplicate: bool
    freshness_at_ingest: float | None = None
    error: str | None = None


async def ingest(rt: Runtime, principal: Principal, signals: list[SignalInput],
                 *, nation_id: str, sector: str | None) -> list[IngestResult]:
    check_nation(principal, nation_id)
    now = rt.clock()
    results: list[IngestResult] = []
    async with rt.sessions.begin() as session:
        _, profile = await rt.configs.active(session)
        stored: list[str] = []
        for raw in signals:
            # IDs and receipt times are assigned here, never taken from the caller.
            raw = raw.model_copy(update={"signal_id": None, "received_at": None})
            resolved = raw.sector or sector
            ref = raw.signal_type
            if resolved is None or resolved not in profile.packs:
                results.append(IngestResult(signal_ref=ref, accepted=False, duplicate=False,
                                            error=f"unknown or missing sector {resolved!r}"))
                continue
            if raw.observed_at is not None and raw.observed_at > now + MAX_FUTURE_SKEW:
                results.append(IngestResult(signal_ref=ref, accepted=False, duplicate=False,
                                            error="observed_at is in the future"))
                continue
            sig = normalize_signal(raw, sector=resolved, nation_id=nation_id, now=now)
            inserted = await _store_signal(session, sig, principal.subject)
            if inserted:
                stored.append(sig.signal_id)
            results.append(IngestResult(
                signal_ref=sig.signal_id, accepted=True, duplicate=not inserted,
                freshness_at_ingest=assess_signal(sig, profile, now).freshness,
            ))
        if stored:
            await audit.append(session, "signals.ingested", short_id("ING", stored),
                               principal.subject, {"nation_id": nation_id, "signal_ids": stored})
    return results


async def _store_signal(session: AsyncSession, sig: Signal, actor: str) -> bool:
    """Insert unless already stored (IDs come from content). True if inserted."""
    inserted = await session.scalar(
        pg_insert(SignalRow)
        .values(signal_id=sig.signal_id, nation_id=sig.nation_id, sector=sig.sector,
                signal_type=sig.signal_type, source_id=sig.source_id,
                source_type=sig.source_type.value, payload=sig.payload,
                observed_at=sig.observed_at, received_at=sig.received_at,
                raw_hash=sig.raw_hash, ingested_by=actor)
        .on_conflict_do_nothing(index_elements=[SignalRow.signal_id])
        .returning(SignalRow.signal_id)
    )
    return inserted is not None


def _as_input(s: Signal | SignalRow) -> SignalInput:
    return SignalInput(signal_id=s.signal_id, signal_type=s.signal_type, source_id=s.source_id,
                       source_type=s.source_type, payload=s.payload, sector=s.sector,
                       observed_at=s.observed_at, received_at=s.received_at,
                       raw_hash=s.raw_hash)


async def load_signals(session: AsyncSession, ids: list[str], nation_id: str) -> list[SignalInput]:
    rows = {r.signal_id: r for r in (await session.scalars(
        select(SignalRow).where(SignalRow.signal_id.in_(ids)))).all()}
    missing = [i for i in ids if i not in rows or rows[i].nation_id != nation_id]
    if missing:
        raise NotFound(f"signals not found for nation {nation_id}: {missing}")
    return [_as_input(rows[i]) for i in ids]


# ── Decisions ────────────────────────────────────────────────


class ResolveBody(BaseModel):
    """A decision request whose signals may be inline, stored (by ref), or both."""

    model_config = ConfigDict(extra="forbid")

    objective: str = Field(min_length=1)
    sector: str
    nation_id: str = "GH"
    signals: list[SignalInput] = Field(default_factory=list)
    signal_refs: list[str] = Field(default_factory=list)
    high_consequence: bool = False
    ecology: EcologyInput | None = None
    inclusion: InclusionInput | None = None
    hae: HaeInput | None = None
    local_fit: LocalFitInput | None = None

    @model_validator(mode="after")
    def _has_signals(self) -> "ResolveBody":
        if not self.signals and not self.signal_refs:
            raise ValueError("give at least one signal or signal_ref")
        return self


class StoredDecision(BaseModel):
    audit_ref: str
    decision_id: str
    audit_seq: int
    config_hash: str
    decision: dict[str, Any]
    escalation: dict[str, Any] | None
    # Read from the sealed audit record, so the explanation is what was recorded.
    evaluated_at: str | None = None
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    conflicts: list[dict[str, Any]] = Field(default_factory=list)
    confidence_breakdown: dict[str, Any] | None = None


def _explain(audit_record: dict[str, Any]) -> dict[str, Any]:
    """Evidence, disagreements and the confidence breakdown, from the recorded trail."""
    trace = {t["step"]: t.get("detail", {}) for t in audit_record.get("trace", [])}
    assessed = {a["signal_id"]: a for a in trace.get(5, {}).get("assessments", [])}
    ids = trace.get(3, {}).get("signal_ids", [])
    evidence = []
    for raw, signal_id in zip(audit_record["request"]["signals"], ids, strict=False):
        a = assessed.get(signal_id, {})
        evidence.append({
            "signal_id": signal_id, "signal_type": raw["signal_type"],
            "source_id": raw["source_id"], "source_type": raw["source_type"],
            "payload": raw.get("payload", {}), "observed_at": raw.get("observed_at"),
            "freshness": a.get("freshness"), "source_reliability": a.get("source_reliability"),
            "evidence_strength": a.get("evidence_strength"),
            "timestamp_basis": a.get("timestamp_basis"),
        })
    return {"evaluated_at": audit_record.get("evaluated_at"), "evidence": evidence,
            "conflicts": trace.get(7, {}).get("conflicts", []),
            "confidence_breakdown": trace.get(8) or None}


async def resolve(rt: Runtime, principal: Principal, body: ResolveBody) -> StoredDecision:
    check_nation(principal, body.nation_id)
    now = rt.clock()

    # Read phase. Closed before step 14 so no transaction stays open during a model call.
    async with rt.sessions() as session:
        config_hash, profile = await rt.configs.active(session)
        stored = (await load_signals(session, body.signal_refs, body.nation_id)
                  if body.signal_refs else [])
    pack = profile.pack(body.sector)
    # Inline signals are normalised here, exactly as ingest would, and stored with
    # the decision: every signal a decision relied on is in the signal store.
    inline: list[Signal] = []
    for raw in body.signals:
        raw = raw.model_copy(update={"signal_id": None, "received_at": None})
        sector = raw.sector or body.sector
        profile.pack(sector)
        if raw.observed_at is not None and raw.observed_at > now + MAX_FUTURE_SKEW:
            raise ValueError(
                f"{raw.signal_type} from {raw.source_id}: observed_at is in the future")
        inline.append(normalize_signal(raw, sector=sector, nation_id=body.nation_id, now=now))
    request = DecisionRequest(
        **{k: getattr(body, k) for k in DecisionRequest.model_fields if k != "signals"},
        signals=[*stored, *(_as_input(s) for s in inline)],
    )

    recommender = rt.gateway.recommender_for(pack)
    result = await run(request, profile, now, recommender)
    exchange = recommender.exchange if recommender else None

    # Write phase.
    async with rt.sessions.begin() as session:
        existing = await session.get(DecisionRow, result.audit.audit_ref)
        if existing is not None:
            return await _stored(session, existing)
        for sig in inline:
            await _store_signal(session, sig, principal.subject)
        entry = await audit.append(session, "decision.recorded", result.audit.audit_ref,
                                   principal.subject,
                                   {"audit": result.audit, "decision": result.decision,
                                    "escalation": result.escalation, "model_exchange": exchange})
        d = result.decision
        session.add(DecisionRow(
            audit_ref=d.audit_ref, decision_id=d.decision_id, audit_seq=entry.seq,
            nation_id=d.nation_id, sector=d.sector, validation_state=d.validation_state.value,
            action=d.recommended_action.action.value, allowed_for_action=d.allowed_for_action,
            human_escalation_required=d.human_escalation_required, config_hash=config_hash,
            decision=json.loads(canonical_json(d)), created_by=principal.subject,
            created_at=now,
        ))
        if result.escalation is not None:
            await _open_escalation(session, result.escalation, d.audit_ref, principal.subject,
                                   now)
        await session.flush()
        return StoredDecision(
            audit_ref=d.audit_ref, decision_id=d.decision_id, audit_seq=entry.seq,
            config_hash=config_hash, decision=json.loads(canonical_json(d)),
            escalation=json.loads(canonical_json(result.escalation))
            if result.escalation else None,
            **_explain(json.loads(canonical_json(result.audit))),
        )


async def _stored(session: AsyncSession, row: DecisionRow) -> StoredDecision:
    esc = await session.scalar(
        select(EscalationRow).where(EscalationRow.audit_ref == row.audit_ref))
    _, payload = await audit.load_payload(session, row.audit_seq)
    return StoredDecision(audit_ref=row.audit_ref, decision_id=row.decision_id,
                          audit_seq=row.audit_seq, config_hash=row.config_hash,
                          decision=row.decision, escalation=escalation_view(esc) if esc else None,
                          **_explain(payload["audit"]))


async def get_decision(rt: Runtime, principal: Principal, ref: str) -> StoredDecision:
    """``ref`` is an audit ref or a decision id (latest record wins)."""
    async with rt.sessions() as session:
        row = await session.get(DecisionRow, ref) or await session.scalar(
            select(DecisionRow).where(DecisionRow.decision_id == ref)
            .order_by(DecisionRow.audit_seq.desc()).limit(1))
        if row is None:
            raise NotFound(f"decision {ref} not found")
        check_nation(principal, row.nation_id)
        return await _stored(session, row)


class ReplayReport(BaseModel):
    audit_ref: str
    decision_id: str
    match: bool
    recorded_decision_hash: str
    replayed_decision_hash: str
    config_hash: str
    recorded_engine_version: str
    current_engine_version: str
    projection_matches_audit: bool
    produced_by: str
    guardrail_events: list[str]
    reasoning_summary: str


async def replay(rt: Runtime, principal: Principal, audit_ref: str) -> ReplayReport:
    """Re-execute a recorded decision from the hash-checked audit entry and the
    exact config version it ran under. Step 14 is taken as recorded."""
    async with rt.sessions() as session:
        row = await session.get(DecisionRow, audit_ref)
        if row is None:
            raise NotFound(f"decision {audit_ref} not found")
        check_nation(principal, row.nation_id)
        return await _replay_row(rt, session, row)


async def _replay_row(rt: Runtime, session: AsyncSession, row: DecisionRow) -> ReplayReport:
    _, payload = await audit.load_payload(session, row.audit_seq)
    record = AuditRecord.model_validate(payload["audit"])
    profile = await rt.configs.get(session, record.config_hash)
    replayed = replay_decision(record, profile)
    d = replayed.decision
    return ReplayReport(
        audit_ref=row.audit_ref,
        decision_id=record.decision_id,
        match=replayed.audit.decision_hash == record.decision_hash,
        recorded_decision_hash=record.decision_hash,
        replayed_decision_hash=replayed.audit.decision_hash,
        config_hash=record.config_hash,
        recorded_engine_version=record.engine_version,
        current_engine_version=ENGINE_VERSION,
        projection_matches_audit=(
            canonical_json(row.decision) == canonical_json(payload["decision"])),
        produced_by=record.recommendation_as_produced.produced_by,
        guardrail_events=d.guardrail_events,
        reasoning_summary=(
            f"{d.validation_state.value} at confidence {d.confidence:.2f}; "
            f"action {d.recommended_action.action.value}; "
            f"{'human escalation required' if d.human_escalation_required else 'no escalation'}."
        ),
    )


class ReplayAllReport(BaseModel):
    total: int
    matched: int
    mismatched: list[str]
    errors: dict[str, str]

    @property
    def ok(self) -> bool:
        return self.total == self.matched


async def replay_all(rt: Runtime, batch: int = 200, *, recorded_by: str | None = None
                     ) -> ReplayAllReport:
    """Replay every recorded decision (Phase 2 exit criterion: 100% must match).
    With ``recorded_by``, the result is written to the audit log."""
    report = await _replay_all(rt, batch)
    if recorded_by:
        async with rt.sessions.begin() as session:
            await audit.append(session, "audit.replay_checked", short_id("RPL", rt.clock()),
                               recorded_by, {**report.model_dump(), "ok": report.ok,
                                             "at": rt.clock()})
    return report


async def _replay_all(rt: Runtime, batch: int) -> ReplayAllReport:
    total, matched, mismatched, errors = 0, 0, [], {}
    last = -1
    while True:
        async with rt.sessions() as session:
            rows = (await session.scalars(
                select(DecisionRow).where(DecisionRow.audit_seq > last)
                .order_by(DecisionRow.audit_seq).limit(batch))).all()
            if not rows:
                break
            for row in rows:
                total += 1
                try:
                    report = await _replay_row(rt, session, row)
                except Exception as exc:  # a tampered or unreadable record is a finding
                    errors[row.audit_ref] = f"{type(exc).__name__}: {exc}"
                    continue
                if report.match and report.projection_matches_audit:
                    matched += 1
                else:
                    mismatched.append(row.audit_ref)
            last = rows[-1].audit_seq
    return ReplayAllReport(total=total, matched=matched, mismatched=mismatched, errors=errors)


# ── Escalations ──────────────────────────────────────────────


def escalation_view(row: EscalationRow) -> dict[str, Any]:
    return {c: getattr(row, c) if not isinstance(getattr(row, c), datetime)
            else getattr(row, c).isoformat()
            for c in ("escalation_id", "decision_id", "audit_ref", "nation_id", "sector",
                      "objective", "priority", "assigned_role", "sla_minutes", "due_at",
                      "reasons", "status", "breached_at", "acknowledged_by", "acknowledged_at",
                      "resolved_by", "resolved_at", "resolution", "created_by", "created_at")}


def _notice(row: EscalationRow | EscalationItem) -> dict[str, Any]:
    """What a notification carries: enough to route and act, no signal data."""
    reasons = row.reasons if isinstance(row, EscalationRow) else [
        r.model_dump(mode="json") for r in row.reasons]
    priority = row.priority if isinstance(row, EscalationRow) else row.priority.value
    return {"escalation_id": row.escalation_id, "priority": priority,
            "assigned_role": row.assigned_role, "sector": row.sector,
            "nation_id": row.nation_id, "objective": row.objective,
            "due_at": row.due_at, "reasons": [r["message"] for r in reasons]}


async def _open_escalation(session: AsyncSession, item: EscalationItem, audit_ref: str | None,
                           actor: str, now: datetime) -> None:
    session.add(EscalationRow(
        escalation_id=item.escalation_id, decision_id=item.decision_id, audit_ref=audit_ref,
        nation_id=item.nation_id, sector=item.sector, objective=item.objective,
        priority=item.priority.value, assigned_role=item.assigned_role,
        sla_minutes=item.sla_minutes, due_at=item.due_at,
        reasons=[r.model_dump(mode="json") for r in item.reasons], status="open",
        created_by=actor, created_at=now,
    ))
    await session.flush()
    notify.enqueue(session, "escalation.opened", item.escalation_id, _notice(item), now)
    await audit.append(session, "escalation.opened", item.escalation_id, actor, item)


async def create_escalation(rt: Runtime, principal: Principal, *, objective: str, sector: str,
                            nation_id: str, priority: EscalationPriority, reason: str,
                            source_ref: str | None) -> dict[str, Any]:
    check_nation(principal, nation_id)
    now = rt.clock()
    async with rt.sessions.begin() as session:
        _, profile = await rt.configs.active(session)
        route = profile.pack(sector).escalation_routing[priority]
        item = EscalationItem(
            escalation_id=short_id("ESC", {"objective": objective, "sector": sector,
                                           "nation": nation_id, "at": now,
                                           "by": principal.subject}),
            decision_id=source_ref or "manual", sector=sector, nation_id=nation_id,
            objective=objective, priority=priority, assigned_role=route.role,
            sla_minutes=route.sla_minutes, due_at=now + timedelta(minutes=route.sla_minutes),
            reasons=[EscalationReason(code="manual", priority=priority, message=reason)],
        )
        await _open_escalation(session, item, None, principal.subject, now)
        row = await session.get(EscalationRow, item.escalation_id)
        assert row is not None
        return escalation_view(row)


def _may_handle(rbac: Rbac, principal: Principal, row: EscalationRow) -> bool:
    return row.assigned_role in principal.roles or rbac.allows(principal, "override_reviews")


async def list_escalations(rt: Runtime, principal: Principal,
                           status: str | None = None) -> list[dict[str, Any]]:
    async with rt.sessions() as session:
        query = select(EscalationRow).order_by(EscalationRow.due_at)
        if status:
            query = query.where(EscalationRow.status == status)
        if principal.nation_id:
            query = query.where(EscalationRow.nation_id == principal.nation_id)
        if not rt.rbac.allows(principal, "override_reviews", "audit_mode"):
            query = query.where(EscalationRow.assigned_role.in_(sorted(principal.roles)))
        return [escalation_view(r) for r in (await session.scalars(query)).all()]


async def transition(rt: Runtime, principal: Principal, escalation_id: str,
                     to: Literal["acknowledged", "resolved"], note: str | None) -> dict[str, Any]:
    now = rt.clock()
    async with rt.sessions.begin() as session:
        row = await session.get(EscalationRow, escalation_id, with_for_update=True)
        if row is None:
            raise NotFound(f"escalation {escalation_id} not found")
        check_nation(principal, row.nation_id)
        if not _may_handle(rt.rbac, principal, row):
            raise Forbidden(f"escalation is assigned to {row.assigned_role}")
        if to == "acknowledged":
            if row.status != "open":
                raise Conflict(f"cannot acknowledge an escalation that is {row.status}")
            row.status, row.acknowledged_by, row.acknowledged_at = to, principal.subject, now
        else:
            if row.status == "resolved":
                raise Conflict("escalation is already resolved")
            if not note or not note.strip():
                raise ValueError("a resolution note is required")
            row.status, row.resolved_by, row.resolved_at, row.resolution = (
                to, principal.subject, now, note)
        await session.flush()
        await audit.append(session, f"escalation.{to}", escalation_id, principal.subject,
                           {"escalation_id": escalation_id, "status": to, "note": note,
                            "at": now, "breached": row.breached_at is not None})
        return escalation_view(row)


async def sweep_sla(rt: Runtime) -> list[str]:
    """Mark unresolved escalations past their SLA as breached (once each).
    Safe to run from several workers: locked rows are skipped."""
    now = rt.clock()
    async with rt.sessions.begin() as session:
        rows = (await session.scalars(
            select(EscalationRow)
            .where(EscalationRow.status != "resolved", EscalationRow.breached_at.is_(None),
                   EscalationRow.due_at < now)
            .with_for_update(skip_locked=True)
        )).all()
        for row in rows:
            row.breached_at = now
            notify.enqueue(session, "escalation.sla_breached", row.escalation_id,
                           {**_notice(row), "status": row.status, "breached_at": now}, now)
        if rows:
            await session.flush()
            await audit.append(session, "escalation.sla_breached", short_id("SLA", now),
                               "system:sla_sweeper",
                               {"at": now, "breached": [
                                   {"escalation_id": r.escalation_id, "priority": r.priority,
                                    "assigned_role": r.assigned_role, "due_at": r.due_at}
                                   for r in rows]})
        return [r.escalation_id for r in rows]
