from datetime import timedelta

import pytest
from conftest import NOW, make_signal
from hypothesis import given
from hypothesis import strategies as st

from antos_core.config import Profile
from antos_core.contracts import (
    ContradictionSeverity,
    EcologyInput,
    EisState,
    EnvironmentalImpact,
    HaeInput,
    HaeState,
    InclusionInput,
    InclusionState,
    LocalFitInput,
    ResourceStress,
    SocialImpact,
    SourceType,
    ValidationState,
)
from antos_core.engines import confidence, contradiction, policy
from antos_core.engines.signals import assess_signal, freshness, normalize_signal

unit = st.floats(min_value=0, max_value=1, allow_nan=False)


def _signals(profile: Profile, *inputs):  # type: ignore[no-untyped-def]
    sigs = [normalize_signal(i, sector="health", nation_id="GH", now=NOW) for i in inputs]
    return sigs, {s.signal_id: assess_signal(s, profile, NOW) for s in sigs}


# ── Freshness and evidence ───────────────────────────────────


def test_health_freshness_at_one_hour_is_half(profile: Profile) -> None:
    """Runbook readiness check: health freshness at 1 h ≈ 0.50."""
    assert freshness(1.0, profile.pack("health").half_life_hours) == pytest.approx(0.5)


def test_agriculture_freshness_at_twenty_hours_is_half(profile: Profile) -> None:
    assert freshness(20.0, profile.pack("agriculture").half_life_hours) == pytest.approx(0.5)


@given(a=st.floats(0, 500), b=st.floats(0, 500), half=st.floats(0.1, 100))
def test_freshness_never_increases_with_age(a: float, b: float, half: float) -> None:
    lo, hi = sorted((a, b))
    assert freshness(hi, half) <= freshness(lo, half)


def test_freshness_uses_observation_time_not_receipt(profile: Profile) -> None:
    sig = normalize_signal(make_signal(age_hours=2.0, received_at=NOW), sector="health",
                           nation_id="GH", now=NOW)
    a = assess_signal(sig, profile, NOW)
    assert a.timestamp_basis == "observed"
    assert a.freshness == pytest.approx(0.25)


def test_missing_observed_at_falls_back_and_lowers_evidence(profile: Profile) -> None:
    with_time = assess_signal(normalize_signal(make_signal(), sector="health", nation_id="GH",
                                               now=NOW), profile, NOW)
    without = assess_signal(normalize_signal(make_signal(age_hours=None), sector="health",
                                             nation_id="GH", now=NOW), profile, NOW)
    assert without.timestamp_basis == "received"
    assert without.evidence_strength == pytest.approx(with_time.evidence_strength - 0.15)


def test_full_evidence_scores_one(profile: Profile) -> None:
    a = assess_signal(normalize_signal(make_signal(), sector="health", nation_id="GH", now=NOW),
                      profile, NOW)
    assert a.evidence_strength == pytest.approx(1.0)


def test_signal_id_is_content_derived_and_stable() -> None:
    a = normalize_signal(make_signal(), sector="health", nation_id="GH", now=NOW)
    b = normalize_signal(make_signal(), sector="health", nation_id="GH", now=NOW + timedelta(1))
    assert a.signal_id == b.signal_id


# ── Contradiction ────────────────────────────────────────────


def test_relative_difference() -> None:
    assert contradiction.relative_difference(80, 100) == pytest.approx(0.2)
    assert contradiction.relative_difference(0, 0) == 0.0


def test_agreement_within_tolerance(profile: Profile) -> None:
    sigs, by_id = _signals(profile,
                           make_signal(payload={"occupancy_rate": 0.80}),
                           make_signal(payload={"occupancy_rate": 0.84}, source_id="ghs_dhims2"))
    result = contradiction.evaluate(sigs, by_id, profile)
    assert result.contradiction_count == 0
    assert result.consistency == 1.0
    assert result.severity_label is ContradictionSeverity.NONE


def test_conflict_severity_follows_manifest_model(profile: Profile) -> None:
    # rel = 0.5, both formal (0.80), health sensitivity 1.10 → 0.5 × 0.8 × 1.1 = 0.44
    sigs, by_id = _signals(profile,
                           make_signal(payload={"occupancy_rate": 0.40}),
                           make_signal(payload={"occupancy_rate": 0.80}, source_id="ghs_dhims2"))
    result = contradiction.evaluate(sigs, by_id, profile)
    assert result.contradiction_count == 1
    assert result.max_severity == pytest.approx(0.44)
    assert result.severity_label is ContradictionSeverity.MODERATE
    assert result.consistency == 0.0


def test_large_conflict_is_severe(profile: Profile) -> None:
    sigs, by_id = _signals(profile,
                           make_signal(payload={"occupancy_rate": 0.10}),
                           make_signal(payload={"occupancy_rate": 0.95}, source_id="ghs_dhims2"))
    assert contradiction.evaluate(sigs, by_id, profile).severity_label is \
        ContradictionSeverity.SEVERE


def test_raw_counts_are_not_compared_against_fractional_tolerance(profile: Profile) -> None:
    """Regression for the reference bug: 3 vs 5 beds is not a 2.0 'difference'."""
    sigs, by_id = _signals(profile,
                           make_signal("drug_stock_level", {"stock_days": 30}),
                           make_signal("drug_stock_level", {"stock_days": 32}, source_id="rms"))
    assert contradiction.evaluate(sigs, by_id, profile).contradiction_count == 0


def test_undeclared_signal_types_are_not_compared(profile: Profile) -> None:
    sigs, by_id = _signals(profile, make_signal("unknown_signal", {"x": 1}),
                           make_signal("unknown_signal", {"x": 100}, source_id="b"))
    result = contradiction.evaluate(sigs, by_id, profile)
    assert result.comparable_pairs == 0
    assert result.consistency is None


# ── Confidence and validation state ──────────────────────────


@pytest.mark.parametrize("sector", ["health", "agriculture", "finance", "energy", "transport",
                                    "education", "governance", "ports"])
def test_trusted_is_reachable_in_every_sector(profile: Profile, sector: str) -> None:
    """Regression for S1/S2: with the authored weights × modifier, agriculture capped near 0.855."""
    pack = profile.pack(sector)
    result = confidence.score(evidence_strength=1, signal_freshness=1, source_reliability=1,
                              cross_signal_consistency=1, domain_stability_modifier=1,
                              contradiction_penalty=0, pack=pack, profile=profile)
    assert result.confidence >= pack.validation_thresholds.trusted


@given(e=unit, f=unit, r=unit, x=unit, d=unit, p=unit)
def test_confidence_bounded(profile: Profile, e: float, f: float, r: float, x: float,
                            d: float, p: float) -> None:
    c = confidence.score(evidence_strength=e, signal_freshness=f, source_reliability=r,
                         cross_signal_consistency=x, domain_stability_modifier=d,
                         contradiction_penalty=p, pack=profile.pack("finance"), profile=profile)
    assert 0.0 <= c.confidence <= 1.0


@given(base=unit, p1=unit, p2=unit)
def test_more_contradiction_never_raises_confidence(profile: Profile, base: float, p1: float,
                                                    p2: float) -> None:
    lo, hi = sorted((p1, p2))
    kwargs = dict(evidence_strength=base, signal_freshness=base, source_reliability=base,
                  cross_signal_consistency=base, domain_stability_modifier=base,
                  pack=profile.pack("health"), profile=profile)
    assert confidence.score(contradiction_penalty=hi, **kwargs).confidence <= \
        confidence.score(contradiction_penalty=lo, **kwargs).confidence


def test_out_of_range_input_rejected(profile: Profile) -> None:
    with pytest.raises(ValueError):
        confidence.score(evidence_strength=1.2, signal_freshness=1, source_reliability=1,
                         cross_signal_consistency=1, domain_stability_modifier=1,
                         contradiction_penalty=0, pack=profile.pack("health"), profile=profile)


@pytest.mark.parametrize(("conf", "fresh", "sev", "expected"), [
    (0.95, 1.0, ContradictionSeverity.SEVERE, ValidationState.BLOCKED),
    (0.20, 1.0, ContradictionSeverity.NONE, ValidationState.BLOCKED),
    (0.95, 1.0, ContradictionSeverity.MODERATE, ValidationState.CONFLICTED),
    (0.95, 0.10, ContradictionSeverity.NONE, ValidationState.DECAYED),
    (0.95, 1.0, ContradictionSeverity.MINOR, ValidationState.TRUSTED),
    (0.70, 1.0, ContradictionSeverity.NONE, ValidationState.PROVISIONAL),
    (0.45, 1.0, ContradictionSeverity.NONE, ValidationState.CONFLICTED),
])
def test_validation_state_precedence(profile: Profile, conf: float, fresh: float,
                                     sev: ContradictionSeverity,
                                     expected: ValidationState) -> None:
    assert confidence.assign_state(conf, fresh, sev, profile.pack("health")) is expected


# ── Inclusion, 24HAE, ecology, local fit ─────────────────────


def test_unassessed_context_is_not_scored_as_zero(profile: Profile) -> None:
    pack = profile.pack("health")
    assert policy.inclusion(None, profile).state is InclusionState.NOT_ASSESSED
    assert policy.hae(None, profile).state is HaeState.NOT_ASSESSED
    assert policy.ecology(None, pack, profile).state is EisState.NOT_ASSESSED


def test_eis_golden_value(profile: Profile) -> None:
    inp = EcologyInput(
        environmental_impact=EnvironmentalImpact(**dict.fromkeys(
            EnvironmentalImpact.model_fields, 0.5)),
        social_impact=SocialImpact(**dict.fromkeys(SocialImpact.model_fields, 1.0)),
        resource_stress=ResourceStress(**dict.fromkeys(ResourceStress.model_fields, 0.0)),
    )
    # 0.40 × 0.5 + 0.35 × 1.0 + 0.25 × 0 = 0.55 → warning (default thresholds)
    result = policy.ecology(inp, profile.pack("transport"), profile)
    assert result.eis_score == pytest.approx(0.55)
    assert result.state is EisState.WARNING
    assert result.coverage == pytest.approx(1.0)


def test_eis_partial_inputs_report_coverage(profile: Profile) -> None:
    inp = EcologyInput(environmental_impact=EnvironmentalImpact(carbon_emission_delta=0.9))
    result = policy.ecology(inp, profile.pack("energy"), profile)
    assert result.eis_score == pytest.approx(0.9)
    assert result.coverage == pytest.approx(0.40 * 0.30)


def test_irreversible_critical_eis_blocks(profile: Profile) -> None:
    inp = EcologyInput(environmental_impact=EnvironmentalImpact(land_use_change_risk=0.95),
                       irreversible=True)
    result = policy.ecology(inp, profile.pack("agriculture"), profile)
    assert result.state is EisState.CRITICAL
    assert result.enforcement_action == "block"


def test_inclusion_flags_exclusionary_dimensions(profile: Profile) -> None:
    """Runbook readiness check: an exclusionary result flags dimensions."""
    result = policy.inclusion(
        InclusionInput(informal_economy_inclusion=0.2, rural_and_agricultural_inclusion=0.8,
                       gender_equity=0.5, youth_inclusion=0.5, disability_and_vulnerability=0.3),
        profile)
    assert result.state is InclusionState.EXCLUSIONARY
    assert result.flagged_dimensions == ["informal_economy_inclusion",
                                         "disability_and_vulnerability"]


def test_hae_reduces_productive_capacity_flag(profile: Profile) -> None:
    """Runbook readiness check: REDUCES_PRODUCTIVE_CAPACITY triggers."""
    result = policy.hae(HaeInput(productive_capacity_impact=-0.4), profile)
    assert "REDUCES_PRODUCTIVE_CAPACITY" in result.policy_flags
    assert result.hae_alignment_score == pytest.approx(0.3)


def test_local_fit_regulatory_failure_is_hard_fail(profile: Profile) -> None:
    result = policy.local_fit(LocalFitInput(**dict.fromkeys(LocalFitInput.model_fields, True))
                              .model_copy(update={"regulatory_grounding": False}),
                              profile.pack("health"), profile)
    assert result.hard_fail_triggered
    assert result.local_fit_passed is False
    assert result.overall_score == pytest.approx(5 / 6)


def test_local_fit_auto_fails_pack_without_laws(profile: Profile) -> None:
    pack = profile.pack("ports").model_copy(update={"jurisdiction_laws": []})
    result = policy.local_fit(None, pack, profile)
    assert result.dimensions_failed == ["regulatory_grounding"]
    assert result.hard_fail_triggered


def test_unverified_source_defaults_to_half(profile: Profile) -> None:
    sig = normalize_signal(make_signal(source_type=SourceType.MANUAL_ENTRY), sector="health",
                           nation_id="GH", now=NOW)
    assert assess_signal(sig, profile, NOW).source_reliability == 0.5
