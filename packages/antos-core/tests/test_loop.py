import asyncio
import json
from typing import Any

import pytest
from conftest import NOW, make_signal

from antos_core import DecisionRequest, Profile, Recommendation, RecommendationContext, run
from antos_core.config import UnknownSectorError
from antos_core.contracts import Action, HaeInput, LocalFitInput, ValidationState
from antos_core.hashing import canonical_json
from antos_core.loop import AuditRecord, LoopResult, verify_replay

ALL_FIT = LocalFitInput(**dict.fromkeys(LocalFitInput.model_fields, True))


def request(**overrides: Any) -> DecisionRequest:
    base: dict[str, Any] = {
        "objective": "Assess ICU capacity at Korle Bu Teaching Hospital",
        "sector": "health",
        "signals": [make_signal(payload={"occupancy_rate": 0.85, "source_ref": "KBH-1"}),
                    make_signal(payload={"occupancy_rate": 0.86, "source_ref": "DHIMS-7"},
                                source_id="ghs_dhims2")],
        "local_fit": ALL_FIT,
    }
    return DecisionRequest(**{**base, **overrides})


def go(req: DecisionRequest, profile: Profile, recommender: Any = None) -> LoopResult:
    return asyncio.run(run(req, profile, NOW, recommender))


class FixedRecommender:
    def __init__(self, **fields: Any) -> None:
        self.fields = fields

    async def recommend(self, ctx: RecommendationContext) -> Recommendation:
        return Recommendation(primary_recommendation="model says", produced_by="llm:test",
                              **{"action": Action.PROCEED, **self.fields})


class BrokenRecommender:
    async def recommend(self, ctx: RecommendationContext) -> Recommendation:
        raise TimeoutError("model unreachable")


# ── Happy path ───────────────────────────────────────────────


def test_clean_corroborated_signals_are_trusted_and_actionable(profile: Profile) -> None:
    result = go(request(), profile)
    d = result.decision
    assert d.validation_state is ValidationState.TRUSTED
    assert d.recommended_action.action is Action.PROCEED
    assert d.allowed_for_action and not d.human_escalation_required
    assert result.escalation is None


def test_trace_covers_all_19_steps_in_order(profile: Profile) -> None:
    steps = [t.step for t in go(request(), profile).audit.trace]
    assert steps == list(range(1, 20))


def test_decision_ids_are_deterministic(profile: Profile) -> None:
    first, second = go(request(), profile), go(request(), profile)
    assert first.decision.decision_id == second.decision.decision_id


# ── Runbook production-readiness checks ──────────────────────


def test_worker_dignity_triggers_critical_escalation(profile: Profile) -> None:
    result = go(request(hae=HaeInput(worker_dignity_preserved=False)), profile)
    assert result.escalation is not None
    assert result.escalation.priority == "critical"
    assert result.decision.recommended_action.action.caution >= Action.ESCALATE.caution
    assert not result.decision.allowed_for_action


def test_regulatory_grounding_failure_escalates(profile: Profile) -> None:
    fit = ALL_FIT.model_copy(update={"regulatory_grounding": False})
    result = go(request(local_fit=fit), profile)
    assert result.decision.local_fit_passed is False
    assert result.escalation is not None
    assert "local_fit_hard_fail" in [r.code for r in result.escalation.reasons]


def test_reduces_productive_capacity_escalates_high(profile: Profile) -> None:
    result = go(request(hae=HaeInput(productive_capacity_impact=-0.5)), profile)
    assert result.escalation is not None
    assert result.escalation.priority == "high"


def test_health_critical_routes_to_sovereign_admin_with_15_min_sla(profile: Profile) -> None:
    result = go(request(signals=[make_signal(payload={"occupancy_rate": 0.10}),
                                 make_signal(payload={"occupancy_rate": 0.95},
                                             source_id="ghs_dhims2")]), profile)
    assert result.decision.validation_state is ValidationState.BLOCKED
    esc = result.escalation
    assert esc is not None
    assert (esc.priority, esc.assigned_role, esc.sla_minutes) == ("critical", "sovereign_admin", 15)


def test_high_consequence_requires_human(profile: Profile) -> None:
    result = go(request(high_consequence=True), profile)
    assert result.decision.human_escalation_required
    assert not result.decision.allowed_for_action


# ── Technology subordination and truth guardrails ────────────


def test_model_cannot_proceed_on_blocked_state(profile: Profile) -> None:
    contradicting = [make_signal(payload={"occupancy_rate": 0.10}),
                     make_signal(payload={"occupancy_rate": 0.95}, source_id="ghs_dhims2")]
    result = go(request(signals=contradicting), profile, FixedRecommender(action=Action.PROCEED))
    d = result.decision
    assert d.validation_state is ValidationState.BLOCKED
    assert d.recommended_action.action is Action.BLOCK
    assert any("technology_subordination_guardrail" in e for e in d.guardrail_events)


def test_empty_stale_signal_is_not_trusted(profile: Profile) -> None:
    """Calibration finding C1 (docs/DECISIONS.md): an empty, 48 h-old manual signal
    still scores ≈0.38 because neutral consistency and domain stability add a floor."""
    stale = [make_signal(payload={}, age_hours=48, raw_hash=None, source_type="manual_entry")]
    d = go(request(signals=stale), profile, FixedRecommender(action=Action.PROCEED)).decision
    assert d.validation_state is ValidationState.CONFLICTED
    assert d.confidence == pytest.approx(0.377, abs=0.01)
    assert d.recommended_action.action.caution >= Action.INVESTIGATE.caution
    assert not d.allowed_for_action


def test_unknown_citations_are_removed(profile: Profile) -> None:
    result = go(request(), profile, FixedRecommender(cited_signal_ids=["SIG-INVENTED"]))
    assert result.decision.recommended_action.cited_signal_ids == []
    assert any("truth_guardrail" in e for e in result.decision.guardrail_events)


def test_model_failure_falls_back_to_rules(profile: Profile) -> None:
    rec = go(request(), profile, BrokenRecommender()).decision.recommended_action
    assert rec.produced_by == "rule_based"
    assert "TimeoutError" in rec.note


def test_unknown_sector_rejected(profile: Profile) -> None:
    with pytest.raises(UnknownSectorError):
        go(request(sector="mining"), profile)


# ── Audit replay ─────────────────────────────────────────────


def test_replay_reproduces_decision(profile: Profile) -> None:
    audit = go(request(hae=HaeInput(worker_dignity_preserved=False)), profile,
               FixedRecommender()).audit
    assert verify_replay(audit, profile)


def test_tampered_audit_fails_replay(profile: Profile) -> None:
    audit = go(request(), profile).audit
    tampered = audit.model_copy(update={"decision_hash": "0" * 64})
    assert not verify_replay(tampered, profile)


def test_replay_fails_under_a_different_config(profile: Profile) -> None:
    audit = go(request(), profile).audit
    data = profile.model_dump()
    data["packs"]["health"]["validation_thresholds"]["trusted"] = 0.95
    assert not verify_replay(audit, Profile.model_validate(data))


def test_replay_survives_json_round_trip(profile: Profile) -> None:
    """Replay in production loads the audit record from storage, not memory."""
    audit = go(request(hae=HaeInput(worker_dignity_preserved=False)), profile,
               FixedRecommender()).audit
    stored = json.loads(canonical_json(audit))
    assert verify_replay(AuditRecord.model_validate(stored), profile)


def test_profile_hash_survives_json_round_trip(profile: Profile) -> None:
    reloaded = Profile.model_validate(json.loads(canonical_json(profile)))
    assert reloaded.config_hash == profile.config_hash
