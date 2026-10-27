import asyncio
from typing import Any

import pytest
from conftest import NOW, make_signal
from hypothesis import given
from hypothesis import strategies as st

from antos_core import DecisionRequest, Profile, run
from antos_core.config import EscalationRule
from antos_core.contracts import LocalFitInput
from antos_core.engines.triggers import RuleSyntaxError, evaluate, parse

ALL_FIT = LocalFitInput(**dict.fromkeys(LocalFitInput.model_fields, True))


def check(rule: str, **facts: Any) -> bool | None:
    return evaluate(parse(rule), {k.replace("__", "."): v for k, v in facts.items()})


# ── Parsing ──────────────────────────────────────────────────


@pytest.mark.parametrize("rule", [
    "",
    "bed.rate >",
    "bed.rate > 90% AND",
    "(bed.rate > 1",
    "bed.rate 90",
    "rate > 1",                       # bare fact that is not a decision fact
    "bed.rate > 1 extra.thing",
    "bed.rate > 1; drop table",
    "__import__('os').system('x') = 1",
])
def test_malformed_rules_are_rejected(rule: str) -> None:
    with pytest.raises(RuleSyntaxError):
        parse(rule)


def test_invalid_rule_fails_profile_validation() -> None:
    with pytest.raises(ValueError, match="invalid rule"):
        EscalationRule(id="bad", when="bed.rate >>> 1", priority="high")


# ── Evaluation ───────────────────────────────────────────────


def test_percent_literals_are_fractions() -> None:
    assert check("bed.rate > 90%", bed__rate=0.95) is True
    assert check("bed.rate > 90%", bed__rate=0.85) is False


def test_symbols_compare_case_insensitively() -> None:
    assert check("outbreak.status = confirmed", outbreak__status="CONFIRMED") is True
    assert check("outbreak.status != confirmed", outbreak__status="suspected") is True


def test_ordinal_scales_compare_by_rank() -> None:
    assert check("contradiction_severity >= moderate", contradiction_severity="severe") is True
    assert check("contradiction_severity >= moderate", contradiction_severity="minor") is False
    assert check("risk.severity >= high", risk__severity="critical") is True
    # Different scales, or words on no scale, are not comparable.
    assert check("risk.severity >= high", risk__severity="severe") is None
    assert check("risk.label > alpha", risk__label="beta") is None


def test_path_on_right_hand_side() -> None:
    rule = "drug.stock_days < drug.safety_days"
    assert check(rule, drug__stock_days=3.0, drug__safety_days=7.0) is True
    assert check(rule, drug__stock_days=3.0) is None


def test_booleans() -> None:
    assert check("outage.hospitals = true", outage__hospitals=True) is True
    assert check("outage.hospitals = true", outage__hospitals=False) is False
    assert check("outage.hospitals > true", outage__hospitals=True) is None
    assert check("outage.hospitals = 1", outage__hospitals=True) is None


def test_precedence_and_parentheses() -> None:
    facts = {"a__x": 1.0, "b__x": 0.0, "c__x": 0.0}
    # AND binds tighter than OR: a OR (b AND c)
    assert check("a.x = 1 OR b.x = 1 AND c.x = 1", **facts) is True
    assert check("(a.x = 1 OR b.x = 1) AND c.x = 1", **facts) is False


def test_missing_data_never_fires_even_through_not() -> None:
    assert check("bed.rate > 90%") is None
    assert check("NOT bed.rate > 90%") is None
    assert check("bed.rate > 90% AND outbreak.status = confirmed", bed__rate=0.95) is None
    # ...but a definite answer still wins where Kleene logic allows it.
    assert check("bed.rate > 90% AND outbreak.status = confirmed", bed__rate=0.5) is False
    assert check("bed.rate > 90% OR outbreak.status = confirmed", bed__rate=0.95) is True


def test_type_mismatch_is_unknown() -> None:
    assert check("bed.rate > 90%", bed__rate="high") is None


@given(st.floats(allow_nan=False, allow_infinity=False),
       st.floats(allow_nan=False, allow_infinity=False))
def test_not_is_the_exact_complement_when_known(a: float, b: float) -> None:
    facts = {"x.a": a, "x.b": b}
    plain = evaluate(parse("x.a < x.b"), facts)
    negated = evaluate(parse("NOT x.a < x.b"), facts)
    assert plain is not None and negated is (not plain)


# ── Loop integration ─────────────────────────────────────────


def decide(profile: Profile, sector: str, signals: list[Any]) -> Any:
    req = DecisionRequest(objective="rule test", sector=sector, signals=signals, local_fit=ALL_FIT)
    return asyncio.run(run(req, profile, NOW))


def test_health_outbreak_rule_routes_to_sovereign_admin(profile: Profile) -> None:
    signals = [
        make_signal(payload={"occupancy_rate": 0.95, "source_ref": "KBH-1"}),
        make_signal(payload={"occupancy_rate": 0.95, "source_ref": "DHIMS-1"},
                    source_id="ghs_dhims2"),
        make_signal(signal_type="disease_outbreak_signal",
                    payload={"case_count": 40, "status": "confirmed", "source_ref": "GHS-7"}),
    ]
    result = decide(profile, "health", signals)
    esc = result.escalation
    assert esc is not None
    assert "rule:outbreak_with_low_bed_capacity" in [r.code for r in esc.reasons]
    assert (esc.priority, esc.assigned_role, esc.sla_minutes) == ("critical", "sovereign_admin", 15)
    assert not result.decision.allowed_for_action


def test_rule_with_its_own_sla_overrides_pack_default(profile: Profile) -> None:
    # finance mobile_money_float_low: HIGH, 20 min, while the pack default for HIGH is 30.
    signals = [make_signal(signal_type="mobile_money_transaction", source_id="mtn_momo",
                           source_type="api_feed",
                           payload={"volume_ghs": 1.0e6, "float_hours": 30, "source_ref": "M-1"})]
    esc = decide(profile, "finance", signals).escalation
    assert esc is not None
    assert (esc.priority, esc.sla_minutes) == ("high", 20)


def test_missing_rule_facts_are_traced_not_fired(profile: Profile) -> None:
    result = decide(profile, "health", [make_signal(payload={"occupancy_rate": 0.85,
                                                             "source_ref": "KBH-1"})])
    step19 = next(t for t in result.audit.trace if t.step == 19)
    assert "maternal_death_reported" in step19.detail["rules_undecided"]
    # 0.85 is not > 90%, so the AND is definitely false even without outbreak data.
    assert "outbreak_with_low_bed_capacity" not in step19.detail["rules_undecided"]
    assert not any(c.startswith("rule:") for c in step19.detail["reasons"])


def test_per_type_contradiction_fact(profile: Profile) -> None:
    signals = [
        make_signal(signal_type="electoral_signal", sector="governance",
                    payload={"turnout_rate": 0.40, "source_ref": "EC-1"}),
        make_signal(signal_type="electoral_signal", sector="governance", source_id="observer",
                    payload={"turnout_rate": 0.70, "source_ref": "OBS-1"}),
    ]
    esc = decide(profile, "governance", signals).escalation
    assert esc is not None
    assert "rule:electoral_contradiction" in [r.code for r in esc.reasons]
