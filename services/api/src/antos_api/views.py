"""Read-only views for dashboards: situation room, decision list, audit browser.

The situation room summarises *stored, real* signals and decisions. A sector
with nothing in the window reports ``no_data``; it never shows a default score.
"""

import json
from datetime import datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import distinct_on

from antos_api.auth import Principal
from antos_api.service import NotFound, Runtime, check_nation, escalation_view
from antos_api.tables import AnchorRow, AuditEntry, DecisionRow, EscalationRow, SignalRow
from antos_core.engines.signals import freshness
from antos_core.loop import ENGINE_VERSION

SectorStatus = Literal["no_data", "stable", "attention", "critical"]


class SignalTypeSummary(BaseModel):
    signal_type: str
    latest_signal_id: str
    source_id: str
    timestamp: datetime
    timestamp_basis: Literal["observed", "received"]
    freshness: float


class Bucket(BaseModel):
    start: datetime
    signals: int
    decisions: int
    worst_state: str | None  # most severe validation state among the bucket's decisions


class Pulse(BaseModel):
    decisions_in_window: int
    decisions_previous_window: int
    signals_in_window: int
    allowed_for_action: int
    open_escalations: dict[str, int]
    at_risk_escalations: int  # open, not yet breached, due within AT_RISK
    breached_escalations: int
    mean_freshness: float | None


class SectorSummary(BaseModel):
    sector: str
    sector_name: str
    priority_24hae: str
    status: SectorStatus
    signals_in_window: int
    signal_types: list[SignalTypeSummary]
    mean_freshness: float | None
    decisions_in_window: int
    validation_states: dict[str, int]
    actions: dict[str, int]
    hae_alignment_mean: float | None
    open_escalations: dict[str, int]
    breached_escalations: int
    latest_decision: dict[str, Any] | None
    timeline: list[Bucket]


class SituationRoom(BaseModel):
    nation_id: str
    generated_at: datetime
    time_window_hours: int
    bucket_minutes: int
    config_hash: str
    pulse: Pulse
    sectors: list[SectorSummary]
    active_escalations: list[dict[str, Any]]


BUCKETS = 24
AT_RISK = timedelta(minutes=30)
STATE_SEVERITY = {"trusted": 0, "provisional": 1, "decayed": 2, "conflicted": 3, "blocked": 4}


def _status(s: SectorSummary) -> SectorStatus:
    if s.signals_in_window == 0 and s.decisions_in_window == 0 and not s.open_escalations:
        return "no_data"
    if s.open_escalations.get("critical") or s.breached_escalations:
        return "critical"
    if (s.open_escalations or s.validation_states.get("blocked")
            or s.validation_states.get("conflicted")
            or any(s.actions.get(a) for a in ("investigate", "escalate", "block"))):
        return "attention"
    return "stable"


async def situation_room(rt: Runtime, principal: Principal, *, nation_id: str,
                         sectors: list[str] | None, time_window_hours: int) -> SituationRoom:
    check_nation(principal, nation_id)
    now = rt.clock()
    since = now - timedelta(hours=time_window_hours)
    async with rt.sessions() as session:
        config_hash, profile = await rt.configs.active(session)
        wanted = sectors or list(profile.packs)
        for s in wanted:
            profile.pack(s)  # unknown sectors are rejected

        seen_at = func.coalesce(SignalRow.observed_at, SignalRow.received_at)
        latest = (await session.scalars(
            select(SignalRow)
            .where(SignalRow.nation_id == nation_id, SignalRow.sector.in_(wanted),
                   seen_at >= since)
            .ext(distinct_on(SignalRow.sector, SignalRow.signal_type))
            .order_by(SignalRow.sector, SignalRow.signal_type, seen_at.desc())
        )).all()
        bucket = timedelta(hours=time_window_hours) / BUCKETS
        # Signal counts per sector and bucket, aggregated in the database.
        signal_buckets = (await session.execute(
            select(SignalRow.sector,
                   func.floor(func.extract("epoch", seen_at - since)
                              / bucket.total_seconds()).label("i"),
                   func.count())
            .where(SignalRow.nation_id == nation_id, SignalRow.sector.in_(wanted),
                   seen_at >= since, seen_at <= now)
            .group_by(SignalRow.sector, "i"))).all()
        previous = await session.scalar(
            select(func.count()).select_from(DecisionRow)
            .where(DecisionRow.nation_id == nation_id, DecisionRow.sector.in_(wanted),
                   DecisionRow.created_at >= since - timedelta(hours=time_window_hours),
                   DecisionRow.created_at < since))
        decisions = (await session.scalars(
            select(DecisionRow)
            .where(DecisionRow.nation_id == nation_id, DecisionRow.sector.in_(wanted),
                   DecisionRow.created_at >= since)
            .order_by(DecisionRow.created_at.desc()))).all()
        open_escalations = (await session.scalars(
            select(EscalationRow)
            .where(EscalationRow.nation_id == nation_id, EscalationRow.sector.in_(wanted),
                   EscalationRow.status != "resolved")
            .order_by(EscalationRow.due_at))).all()

    def index(t: datetime) -> int:
        return min(int((t - since) / bucket), BUCKETS - 1)

    signals_per: dict[str, list[int]] = {s: [0] * BUCKETS for s in wanted}
    for sector, i, count in signal_buckets:
        signals_per[sector][min(int(i), BUCKETS - 1)] += count
    signal_counts = {s: sum(v) for s, v in signals_per.items()}

    summaries = []
    for sector in wanted:
        pack = profile.pack(sector)
        types = []
        for row in (r for r in latest if r.sector == sector):
            stamp = row.observed_at or row.received_at
            age_h = max((now - stamp).total_seconds() / 3600, 0.0)
            types.append(SignalTypeSummary(
                signal_type=row.signal_type, latest_signal_id=row.signal_id,
                source_id=row.source_id, timestamp=stamp,
                timestamp_basis="observed" if row.observed_at else "received",
                freshness=round(freshness(age_h, pack.half_life_hours), 6)))
        mine = [d for d in decisions if d.sector == sector]
        states: dict[str, int] = {}
        actions: dict[str, int] = {}
        hae = [d.decision["hae_alignment_score"] for d in mine
               if d.decision.get("hae_alignment_score") is not None]
        for d in mine:
            states[d.validation_state] = states.get(d.validation_state, 0) + 1
            actions[d.action] = actions.get(d.action, 0) + 1
        esc = [e for e in open_escalations if e.sector == sector]
        by_priority: dict[str, int] = {}
        for e in esc:
            by_priority[e.priority] = by_priority.get(e.priority, 0) + 1
        decided = [0] * BUCKETS
        worst: list[str | None] = [None] * BUCKETS
        for d in mine:
            i = index(d.created_at)
            decided[i] += 1
            current = worst[i]
            if current is None or (STATE_SEVERITY.get(d.validation_state, 0)
                                   > STATE_SEVERITY.get(current, 0)):
                worst[i] = d.validation_state
        timeline = [Bucket(start=since + bucket * i, signals=signals_per[sector][i],
                           decisions=decided[i], worst_state=worst[i]) for i in range(BUCKETS)]
        summary = SectorSummary(
            sector=sector, sector_name=pack.sector_name, priority_24hae=pack.priority_24hae,
            status="no_data", signals_in_window=signal_counts.get(sector, 0),
            signal_types=types,
            mean_freshness=round(sum(t.freshness for t in types) / len(types), 6)
            if types else None,
            decisions_in_window=len(mine), validation_states=states, actions=actions,
            hae_alignment_mean=round(sum(hae) / len(hae), 6) if hae else None,
            open_escalations=by_priority,
            breached_escalations=sum(e.breached_at is not None for e in esc),
            latest_decision=_decision_summary(mine[0]) if mine else None,
            timeline=timeline,
        )
        summary.status = _status(summary)
        summaries.append(summary)

    by_priority_all: dict[str, int] = {}
    for e in open_escalations:
        by_priority_all[e.priority] = by_priority_all.get(e.priority, 0) + 1
    all_fresh = [t.freshness for s in summaries for t in s.signal_types]
    pulse = Pulse(
        decisions_in_window=len(decisions),
        decisions_previous_window=previous or 0,
        signals_in_window=sum(signal_counts.values()),
        allowed_for_action=sum(d.allowed_for_action for d in decisions),
        open_escalations=by_priority_all,
        at_risk_escalations=sum(e.breached_at is None and now <= e.due_at <= now + AT_RISK
                                for e in open_escalations),
        breached_escalations=sum(e.breached_at is not None for e in open_escalations),
        mean_freshness=round(sum(all_fresh) / len(all_fresh), 6) if all_fresh else None,
    )
    return SituationRoom(nation_id=nation_id, generated_at=now,
                         time_window_hours=time_window_hours,
                         bucket_minutes=round(bucket.total_seconds() / 60),
                         config_hash=config_hash, pulse=pulse, sectors=summaries,
                         active_escalations=[escalation_view(e) for e in open_escalations[:50]])


# ── Node status (top bar) ────────────────────────────────────


class NodeStatus(BaseModel):
    node_id: str
    engine_version: str
    config_hash: str
    manifest_version: str
    audit_head_seq: int | None
    audit_head_hash: str | None
    last_anchor_seq: int | None
    last_anchor_at: datetime | None
    entries_since_anchor: int
    model_gateway: dict[str, Any]
    anchor_signing: bool


async def node_status(rt: Runtime) -> NodeStatus:
    async with rt.sessions() as session:
        config_hash, profile = await rt.configs.active(session)
        head = (await session.execute(
            select(AuditEntry.seq, AuditEntry.entry_hash)
            .order_by(AuditEntry.seq.desc()).limit(1))).first()
        anchor = (await session.execute(
            select(AnchorRow.up_to_seq, AnchorRow.anchored_at)
            .order_by(AnchorRow.up_to_seq.desc()).limit(1))).first()
        since_anchor = await session.scalar(
            select(func.count()).select_from(AuditEntry)
            .where(AuditEntry.seq > (anchor[0] if anchor else -1)))
    return NodeStatus(
        node_id=rt.node_id, engine_version=ENGINE_VERSION, config_hash=config_hash,
        manifest_version=profile.manifest.version,
        audit_head_seq=head[0] if head else None, audit_head_hash=head[1] if head else None,
        last_anchor_seq=anchor[0] if anchor else None,
        last_anchor_at=anchor[1] if anchor else None,
        entries_since_anchor=since_anchor or 0, model_gateway=rt.gateway.describe(),
        anchor_signing=rt.anchor_signer is not None)


# ── Decision list ────────────────────────────────────────────


def _decision_summary(row: DecisionRow) -> dict[str, Any]:
    d = row.decision
    return {"audit_ref": row.audit_ref, "decision_id": row.decision_id,
            "audit_seq": row.audit_seq, "sector": row.sector, "nation_id": row.nation_id,
            "objective": d.get("objective"), "validation_state": row.validation_state,
            "confidence": d.get("confidence"), "action": row.action,
            "allowed_for_action": row.allowed_for_action,
            "human_escalation_required": row.human_escalation_required,
            "produced_by": d.get("recommended_action", {}).get("produced_by"),
            "created_at": row.created_at, "created_by": row.created_by}


async def list_decisions(rt: Runtime, principal: Principal, *, sector: str | None,
                         limit: int, before_seq: int | None,
                         since: datetime | None = None, until: datetime | None = None
                         ) -> list[dict[str, Any]]:
    async with rt.sessions() as session:
        query = select(DecisionRow).order_by(DecisionRow.audit_seq.desc()).limit(limit)
        if sector:
            query = query.where(DecisionRow.sector == sector)
        if since is not None:
            query = query.where(DecisionRow.created_at >= since)
        if until is not None:
            query = query.where(DecisionRow.created_at < until)
        if principal.nation_id:
            query = query.where(DecisionRow.nation_id == principal.nation_id)
        if before_seq is not None:
            query = query.where(DecisionRow.audit_seq < before_seq)
        return [_decision_summary(r) for r in (await session.scalars(query)).all()]


# ── Signals (evidence) ───────────────────────────────────────


async def list_signals(rt: Runtime, principal: Principal, *, sector: str | None,
                       signal_type: str | None, source: str | None, hours: int,
                       limit: int) -> dict[str, Any]:
    now = rt.clock()
    since = now - timedelta(hours=hours)
    async with rt.sessions() as session:
        _, profile = await rt.configs.active(session)
        seen_at = func.coalesce(SignalRow.observed_at, SignalRow.received_at)
        query = select(SignalRow).where(seen_at >= since)
        if principal.nation_id:
            query = query.where(SignalRow.nation_id == principal.nation_id)
        if sector:
            query = query.where(SignalRow.sector == sector)
        if signal_type:
            query = query.where(SignalRow.signal_type == signal_type)
        if source:
            query = query.where(SignalRow.source_id == source)
        rows = (await session.scalars(query.order_by(seen_at.desc()).limit(limit + 1))).all()

    truncated = len(rows) > limit
    out: list[dict[str, Any]] = []
    for r in rows[:limit]:
        pack = profile.packs.get(r.sector)
        stamp = r.observed_at or r.received_at
        age_h = max((now - stamp).total_seconds() / 3600, 0.0)
        fresh = freshness(age_h, pack.half_life_hours) if pack else None
        floor = pack.validation_thresholds.decay_freshness_floor if pack else 0.0
        compare = pack.signal_types.get(r.signal_type) if pack else None
        field = compare.compare_field if compare else None
        out.append({
            "signal_id": r.signal_id, "nation_id": r.nation_id, "sector": r.sector,
            "signal_type": r.signal_type, "source_id": r.source_id, "source_type": r.source_type,
            "reading_field": field,
            "reading": r.payload.get(field) if field else None,
            "payload": r.payload, "observed_at": r.observed_at, "received_at": r.received_at,
            "freshness": round(fresh, 6) if fresh is not None else None,
            "stale": fresh is not None and fresh < floor,
        })
    fresh_values = [float(s["freshness"]) for s in out if s["freshness"] is not None]
    return {
        "summary": {
            "received": len(out), "sources": len({s["source_id"] for s in out}),
            "mean_freshness": round(sum(fresh_values) / len(fresh_values), 6)
            if fresh_values else None,
            "stale": sum(1 for s in out if s["stale"]),
        },
        "signals": out, "truncated": truncated,
    }


# ── Audit browser ────────────────────────────────────────────


def _entry_summary(e: AuditEntry) -> dict[str, Any]:
    return {"seq": e.seq, "event_type": e.event_type, "ref": e.ref, "actor": e.actor,
            "created_at": e.created_at, "payload_hash": e.payload_hash,
            "prev_hash": e.prev_hash, "entry_hash": e.entry_hash,
            "payload_bytes": len(e.payload.encode("utf-8"))}


async def list_audit_entries(rt: Runtime, *, limit: int, before_seq: int | None,
                             event_type: str | None) -> list[dict[str, Any]]:
    """The log spans every nation on this node, so it is not filtered by nation.
    Access needs an audit permission; pilot nodes serve one nation each.
    Multi-nation nodes need per-tenant audit views (planned with multi-tenancy)."""
    async with rt.sessions() as session:
        query = select(AuditEntry).order_by(AuditEntry.seq.desc()).limit(limit)
        if before_seq is not None:
            query = query.where(AuditEntry.seq < before_seq)
        if event_type:
            query = query.where(AuditEntry.event_type == event_type)
        return [_entry_summary(e) for e in (await session.scalars(query)).all()]


async def get_audit_entry(rt: Runtime, seq: int) -> dict[str, Any]:
    async with rt.sessions() as session:
        entry = await session.get(AuditEntry, seq)
    if entry is None:
        raise NotFound(f"audit entry {seq} not found")
    return {**_entry_summary(entry), "payload": json.loads(entry.payload)}
