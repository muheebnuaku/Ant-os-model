"""The 19-step reasoning contract.

    prepare()   steps 1–13   pure, deterministic
    recommender step 14      the only place a model may take part (may do I/O)
    finalize()  steps 15–19  pure, deterministic

Because steps 1–13 and 15–19 are pure functions of (request, now, profile,
recommendation), an audit record holding those inputs can be re-executed and
must reproduce the same decision hash — that is what ``verify_replay`` checks.
"""

from datetime import datetime
from typing import Any

from pydantic import Field

from antos_core.config import Profile
from antos_core.contracts import (
    Action,
    Contract,
    ContradictionResult,
    ContradictionSeverity,
    EcologyInput,
    EcologyResult,
    EisState,
    EscalationPriority,
    HaeInput,
    HaeResult,
    InclusionInput,
    InclusionResult,
    InclusionState,
    LocalFitInput,
    LocalFitResult,
    Signal,
    SignalAssessment,
    SignalInput,
    ValidationState,
)
from antos_core.engines import confidence as confidence_engine
from antos_core.engines import contradiction as contradiction_engine
from antos_core.engines import policy
from antos_core.engines.escalation import EscalationItem, EscalationReason, route, rule_reasons
from antos_core.engines.signals import assess_signal, normalize_signal
from antos_core.engines.triggers import FactValue, fact_value
from antos_core.hashing import sha256_of, short_id
from antos_core.recommend import (
    Recommendation,
    RecommendationContext,
    Recommender,
    RuleBasedRecommender,
)

ENGINE_VERSION = "0.2.1"

STATE_ACTION_FLOOR = {
    ValidationState.TRUSTED: Action.PROCEED,
    ValidationState.PROVISIONAL: Action.PROCEED,
    ValidationState.DECAYED: Action.DEFER,
    ValidationState.CONFLICTED: Action.INVESTIGATE,
    ValidationState.BLOCKED: Action.BLOCK,
}


# ── Contracts ────────────────────────────────────────────────


class DecisionRequest(Contract):
    objective: str = Field(min_length=1)
    sector: str
    nation_id: str = "GH"
    signals: list[SignalInput] = Field(min_length=1)
    high_consequence: bool = False
    ecology: EcologyInput | None = None
    inclusion: InclusionInput | None = None
    hae: HaeInput | None = None
    local_fit: LocalFitInput | None = None


class StepTrace(Contract):
    step: int
    name: str
    detail: dict[str, Any] = Field(default_factory=dict)


class PreparedDecision(Contract):
    request: DecisionRequest
    evaluated_at: datetime
    input_hash: str
    decision_id: str
    trail_id: str
    signals: list[Signal]
    assessments: list[SignalAssessment]
    contradiction: ContradictionResult
    confidence: float
    mean_freshness: float
    validation_state: ValidationState
    inclusion: InclusionResult
    hae: HaeResult
    ecology: EcologyResult
    trace: list[StepTrace]

    def recommendation_context(self) -> RecommendationContext:
        return RecommendationContext(
            objective=self.request.objective,
            sector=self.request.sector,
            nation_id=self.request.nation_id,
            signals=self.signals,
            validation_state=self.validation_state,
            confidence=self.confidence,
            contradiction_severity=self.contradiction.severity_label,
            contradiction_count=self.contradiction.contradiction_count,
            inclusion=self.inclusion,
            hae=self.hae,
            ecology=self.ecology,
            high_consequence=self.request.high_consequence,
        )


class Decision(Contract):
    decision_id: str
    objective: str
    sector: str
    nation_id: str
    validation_state: ValidationState
    confidence: float
    contradiction_count: int
    contradiction_severity: ContradictionSeverity
    ecology_state: EisState
    ecology_score: float | None
    inclusion_state: InclusionState
    inclusion_score: float | None
    hae_alignment_score: float | None
    recommended_action: Recommendation
    human_escalation_required: bool
    allowed_for_action: bool
    local_fit_passed: bool | None
    local_fit_report: LocalFitResult
    guardrail_events: list[str]
    audit_ref: str


class AuditRecord(Contract):
    audit_ref: str
    decision_id: str
    engine_version: str
    config_hash: str
    input_hash: str
    decision_hash: str
    evaluated_at: datetime
    request: DecisionRequest
    recommendation_as_produced: Recommendation
    trace: list[StepTrace]


class LoopResult(Contract):
    decision: Decision
    escalation: EscalationItem | None
    audit: AuditRecord


# ── Steps 1–13 ───────────────────────────────────────────────


def prepare(request: DecisionRequest, profile: Profile, now: datetime) -> PreparedDecision:
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    pack = profile.pack(request.sector)
    trace: list[StepTrace] = []
    input_hash = sha256_of({"request": request, "evaluated_at": now})

    # 1–3 ingest, classify, provenance
    signals = [
        normalize_signal(raw, sector=request.sector, nation_id=request.nation_id, now=now)
        for raw in request.signals
    ]
    for s in signals:
        profile.pack(s.sector)  # step 2: every signal must map to a registered sector
    trace.append(StepTrace(step=1, name="ingest_signal", detail={"count": len(signals)}))
    trace.append(StepTrace(
        step=2, name="classify_signal_and_sector",
        detail={"sectors": sorted({s.sector for s in signals})},
    ))
    trace.append(StepTrace(
        step=3, name="attach_provenance_and_timestamp",
        detail={"signal_ids": [s.signal_id for s in signals]},
    ))

    # 4–5 freshness and source reliability
    assessments = [assess_signal(s, profile, now) for s in signals]
    by_id = {a.signal_id: a for a in assessments}
    mean_freshness = sum(a.freshness for a in assessments) / len(assessments)
    trace.append(StepTrace(
        step=4, name="evaluate_freshness_with_domain_lambda",
        detail={"mean_freshness": round(mean_freshness, 6),
                "missing_observed_at": [a.signal_id for a in assessments
                                        if a.timestamp_basis == "received"]},
    ))
    trace.append(StepTrace(step=5, name="evaluate_source_reliability",
                           detail={"assessments": [a.model_dump(mode="json")
                                                   for a in assessments]}))

    # 6 trail
    trail_id = short_id("TRL", {"objective": request.objective, "sector": request.sector,
                                "signals": sorted(by_id)})
    trace.append(StepTrace(step=6, name="attach_or_create_trail", detail={"trail_id": trail_id}))

    # 7 contradictions
    contradiction = contradiction_engine.evaluate(signals, by_id, profile)
    trace.append(StepTrace(
        step=7, name="detect_contradictions_and_assign_severity",
        detail={"count": contradiction.contradiction_count,
                "severity": contradiction.severity_label.value,
                "max_severity": contradiction.max_severity,
                "conflicts": [c.model_dump(mode="json") for c in contradiction.conflicts]},
    ))

    # 8–9 confidence and validation state
    conf = confidence_engine.score_signals(assessments, contradiction, pack, profile)
    state = confidence_engine.assign_state(
        conf.confidence, mean_freshness, contradiction.severity_label, pack
    )
    trace.append(StepTrace(step=8, name="compute_confidence_score",
                           detail=conf.model_dump(mode="json")))
    trace.append(StepTrace(step=9, name="assign_validation_state", detail={"state": state.value}))

    # 10–13 inclusion, 24HAE, ecology, intra-African trade
    inclusion = policy.inclusion(request.inclusion, profile)
    hae = policy.hae(request.hae, profile)
    ecology = policy.ecology(request.ecology, pack, profile)
    trace.append(StepTrace(step=10, name="run_inclusion_check",
                           detail={"state": inclusion.state.value}))
    trace.append(StepTrace(step=11, name="run_policy_precheck_24hae",
                           detail={"state": hae.state.value, "flags": hae.policy_flags}))
    trace.append(StepTrace(step=12, name="run_ecology_check_EIS",
                           detail={"state": ecology.state.value, "eis": ecology.eis_score}))
    trace.append(StepTrace(step=13, name="evaluate_intra_african_trade_alignment",
                           detail={"aligned": hae.intra_african_aligned}))

    return PreparedDecision(
        request=request,
        evaluated_at=now,
        input_hash=input_hash,
        decision_id=f"DEC-{input_hash[:12].upper()}",
        trail_id=trail_id,
        signals=signals,
        assessments=assessments,
        contradiction=contradiction,
        confidence=conf.confidence,
        mean_freshness=mean_freshness,
        validation_state=state,
        inclusion=inclusion,
        hae=hae,
        ecology=ecology,
        trace=trace,
    )


# ── Steps 15–19 ──────────────────────────────────────────────


def decision_facts(p: PreparedDecision, profile: Profile) -> dict[str, FactValue]:
    """Facts the pack's escalation rules can test. Signal payload fields come
    from the most recent signal of each type."""
    facts: dict[str, FactValue] = {
        "sector": p.request.sector,
        "nation_id": p.request.nation_id,
        "validation_state": p.validation_state.value,
        "confidence": p.confidence,
        "mean_freshness": p.mean_freshness,
        "contradiction_severity": p.contradiction.severity_label.value,
        "contradiction_count": float(p.contradiction.contradiction_count),
        "high_consequence": p.request.high_consequence,
    }
    for name, score in (("eis_score", p.ecology.eis_score),
                        ("inclusion_score", p.inclusion.inclusion_score),
                        ("hae_alignment_score", p.hae.hae_alignment_score)):
        if score is not None:
            facts[name] = score

    latest: dict[str, Signal] = {}
    for s in sorted(p.signals, key=lambda s: (s.observed_at or s.received_at, s.signal_id)):
        latest[s.signal_type] = s
    for signal_type, signal in latest.items():
        for field, raw in signal.payload.items():
            value = fact_value(raw)
            if value is not None:
                facts[f"{signal_type}.{field}"] = value

    worst: dict[str, float] = {}
    for c in p.contradiction.conflicts:
        worst[c.signal_type] = max(worst.get(c.signal_type, 0.0), c.severity)
    for signal_type in latest:
        label = contradiction_engine.classify(
            worst.get(signal_type, 0.0), signal_type in worst, profile
        )
        facts[f"contradiction.{signal_type}"] = label.value
    return facts


def _escalation_reasons(
    p: PreparedDecision, local_fit: LocalFitResult, rec: Recommendation
) -> list[EscalationReason]:
    crit, high, med = (EscalationPriority.CRITICAL, EscalationPriority.HIGH,
                       EscalationPriority.MEDIUM)
    checks: list[tuple[bool, str, EscalationPriority, str]] = [
        (p.validation_state is ValidationState.BLOCKED, "validation_blocked", crit,
         "Validation state is BLOCKED."),
        (p.contradiction.severity_label is ContradictionSeverity.SEVERE, "severe_contradiction",
         crit, f"{p.contradiction.contradiction_count} severe signal contradiction(s)."),
        (p.ecology.state is EisState.CRITICAL, "eis_critical", crit,
         f"Ecology Impact Score {p.ecology.eis_score} is at or above the critical threshold."),
        ("WORKER_DIGNITY_AT_RISK" in p.hae.policy_flags, "labour_dignity_guardrail", crit,
         "Worker dignity or safety is at risk."),
        ("SOVEREIGNTY_AT_RISK" in p.hae.policy_flags, "sovereignty_guardrail", crit,
         "Data or threshold sovereignty is at risk."),
        (p.request.high_consequence, "high_consequence", high,
         "Requester marked this decision high-consequence."),
        (local_fit.hard_fail_triggered, "local_fit_hard_fail", high,
         f"Local fit hard-fail: {', '.join(local_fit.dimensions_failed)}."),
        ("REDUCES_PRODUCTIVE_CAPACITY" in p.hae.policy_flags, "24hae_alignment_guardrail", high,
         "Decision reduces productive capacity."),
        (p.inclusion.state is InclusionState.CRITICAL_EXCLUSION, "inclusion_guardrail", high,
         "Decision critically excludes under-represented actors."),
        (p.validation_state is ValidationState.CONFLICTED, "validation_conflicted", med,
         "Validation state is CONFLICTED."),
        (local_fit.escalation_triggered and not local_fit.hard_fail_triggered, "local_fit_failed",
         med, f"Local fit failed: {', '.join(local_fit.dimensions_failed)}."),
        (rec.escalation_suggested, "recommender_suggested", med,
         "The reasoning step suggested human review."),
    ]
    return [EscalationReason(code=c, priority=pr, message=m) for ok, c, pr, m in checks if ok]


def postcheck(
    p: PreparedDecision, rec: Recommendation, events: list[str]
) -> Recommendation:
    """Step 16. The recommendation may only be *more* cautious than the evidence allows,
    and may only cite signals that exist in this trail."""
    known = {s.signal_id for s in p.signals}
    unknown = [sid for sid in rec.cited_signal_ids if sid not in known]
    updates: dict[str, Any] = {}
    if unknown:
        events.append(f"truth_guardrail: removed citations of unknown signals {unknown}")
        updates["cited_signal_ids"] = [sid for sid in rec.cited_signal_ids if sid in known]

    floor = STATE_ACTION_FLOOR[p.validation_state]
    if rec.action.caution < floor.caution:
        events.append(
            f"technology_subordination_guardrail: raised action {rec.action.value} → "
            f"{floor.value} ({p.validation_state.value} state)"
        )
        updates["action"] = floor
    return rec.model_copy(update=updates) if updates else rec


def finalize(
    p: PreparedDecision, recommendation: Recommendation, profile: Profile
) -> LoopResult:
    pack = profile.pack(p.request.sector)
    events: list[str] = []
    trace = list(p.trace)
    trace.append(StepTrace(step=14, name="reason_over_options_with_ubuntu_lens",
                           detail={"produced_by": recommendation.produced_by,
                                   "action": recommendation.action.value,
                                   "note": recommendation.note}))

    if p.contradiction.severity_label in (ContradictionSeverity.MODERATE,
                                          ContradictionSeverity.SEVERE):
        events.append(f"contradiction_guardrail: {p.contradiction.severity_label.value} "
                      f"({p.contradiction.contradiction_count} conflict(s))")
    if p.inclusion.state is InclusionState.EXCLUSIONARY:
        events.append(f"inclusion_guardrail: flagged {p.inclusion.flagged_dimensions}")
    if p.ecology.state is EisState.WARNING:
        events.append(f"ecology_guardrail: EIS {p.ecology.eis_score} warning")
    if p.hae.policy_flags:
        events.append(f"24hae_policy: flags {p.hae.policy_flags}")

    # 16 policy postcheck
    rec = postcheck(p, recommendation, events)
    trace.append(StepTrace(step=16, name="run_policy_postcheck",
                           detail={"action": rec.action.value}))

    # 17 local fit
    local_fit = policy.local_fit(p.request.local_fit, pack, profile)
    if local_fit.assessed and not local_fit.local_fit_passed:
        events.append(f"local_fit_guardrail: failed {local_fit.dimensions_failed}")
    trace.append(StepTrace(step=17, name="run_local_fit_test",
                           detail={"passed": local_fit.local_fit_passed,
                                   "not_assessed": local_fit.dimensions_not_assessed}))

    # 19 (decided before the audit ref so it is part of the hashed decision)
    rules_fired, rules_undecided = rule_reasons(pack.escalation_rules,
                                                decision_facts(p, profile))
    reasons = _escalation_reasons(p, local_fit, rec) + rules_fired
    if reasons and rec.action.caution < Action.ESCALATE.caution:
        events.append(f"technology_subordination_guardrail: raised action {rec.action.value} → "
                      "escalate (human escalation required)")
        rec = rec.model_copy(update={"action": Action.ESCALATE})
    allowed = (
        p.validation_state in (ValidationState.TRUSTED, ValidationState.PROVISIONAL)
        and not reasons
    )

    # 15 + 18 decision object and audit ref
    audit_ref = short_id("AUD", {"input": p.input_hash, "config": profile.config_hash,
                                 "recommendation": recommendation})
    decision = Decision(
        decision_id=p.decision_id,
        objective=p.request.objective,
        sector=p.request.sector,
        nation_id=p.request.nation_id,
        validation_state=p.validation_state,
        confidence=p.confidence,
        contradiction_count=p.contradiction.contradiction_count,
        contradiction_severity=p.contradiction.severity_label,
        ecology_state=p.ecology.state,
        ecology_score=p.ecology.eis_score,
        inclusion_state=p.inclusion.state,
        inclusion_score=p.inclusion.inclusion_score,
        hae_alignment_score=p.hae.hae_alignment_score,
        recommended_action=rec,
        human_escalation_required=bool(reasons),
        allowed_for_action=allowed,
        local_fit_passed=local_fit.local_fit_passed,
        local_fit_report=local_fit,
        guardrail_events=events,
        audit_ref=audit_ref,
    )
    escalation = route(reasons, decision_id=p.decision_id, objective=p.request.objective,
                       nation_id=p.request.nation_id, pack=pack, now=p.evaluated_at)
    trace.append(StepTrace(step=15, name="generate_decision_object",
                           detail={"decision_id": p.decision_id}))
    trace.append(StepTrace(step=18, name="create_audit_ref", detail={"audit_ref": audit_ref}))
    trace.append(StepTrace(step=19, name="return_or_escalate",
                           detail={"escalated": escalation is not None,
                                   "reasons": [r.code for r in reasons],
                                   "rules_undecided": rules_undecided}))

    audit = AuditRecord(
        audit_ref=audit_ref,
        decision_id=p.decision_id,
        engine_version=ENGINE_VERSION,
        config_hash=profile.config_hash,
        input_hash=p.input_hash,
        decision_hash=sha256_of({"decision": decision, "escalation": escalation}),
        evaluated_at=p.evaluated_at,
        request=p.request,
        recommendation_as_produced=recommendation,
        trace=sorted(trace, key=lambda t: t.step),
    )
    return LoopResult(decision=decision, escalation=escalation, audit=audit)


# ── Full run and replay ──────────────────────────────────────


async def run(
    request: DecisionRequest,
    profile: Profile,
    now: datetime,
    recommender: Recommender | None = None,
) -> LoopResult:
    prepared = prepare(request, profile, now)
    ctx = prepared.recommendation_context()
    fallback = RuleBasedRecommender()
    if recommender is None:
        rec = fallback.recommend_sync(ctx)
    else:
        try:
            rec = await recommender.recommend(ctx)
        except Exception as exc:  # the loop must never fail because a model failed
            rec = fallback.recommend_sync(ctx, note=f"recommender failed: {type(exc).__name__}")
    return finalize(prepared, rec, profile)


def replay(audit: AuditRecord, profile: Profile) -> LoopResult:
    prepared = prepare(audit.request, profile, audit.evaluated_at)
    return finalize(prepared, audit.recommendation_as_produced, profile)


def verify_replay(audit: AuditRecord, profile: Profile) -> bool:
    """True when the profile is the one the decision ran under and re-execution
    reproduces the recorded decision exactly."""
    if profile.config_hash != audit.config_hash:
        return False
    return replay(audit, profile).audit.decision_hash == audit.decision_hash
