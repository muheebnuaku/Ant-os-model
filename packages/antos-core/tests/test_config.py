import pytest
from pydantic import ValidationError

from antos_core.config import ConfidenceWeights, Profile, ValidationThresholds, deep_merge

CORE_8 = {"health", "agriculture", "finance", "energy", "transport", "education", "governance",
          "ports"}

# Paper Table I (λ per hour). Derived λ = ln2 / t½ must match to 3 decimals.
PAPER_LAMBDA = {
    "health": 0.693, "finance": 0.347, "energy": 0.231, "transport": 0.139,
    "ports": 0.099, "agriculture": 0.035, "governance": 0.020,
}


def test_profile_loads_core_8_sectors(profile: Profile) -> None:
    assert set(profile.packs) == CORE_8


@pytest.mark.parametrize(("sector", "lam"), PAPER_LAMBDA.items())
def test_derived_lambda_matches_paper_table(profile: Profile, sector: str, lam: float) -> None:
    assert profile.pack(sector).decay_lambda == pytest.approx(lam, abs=1e-3)


def test_finance_lambda_runbook_check(profile: Profile) -> None:
    assert profile.pack("finance").decay_lambda == pytest.approx(0.347, abs=1e-3)


def test_sector_overrides_merge_over_defaults(profile: Profile) -> None:
    health = profile.pack("health")
    assert health.validation_thresholds.trusted == 0.88
    assert health.validation_thresholds.provisional == 0.60  # inherited
    assert health.escalation_routing["critical"].role == "sovereign_admin"
    assert health.escalation_routing["low"].role == "analyst"  # inherited


@pytest.mark.parametrize("sector", sorted(CORE_8))
def test_normalized_positive_weights_sum_to_one(profile: Profile, sector: str) -> None:
    weights = profile.pack(sector).confidence_weights.normalized()
    positive = sum(v for k, v in weights.items() if k != "contradiction_penalty")
    assert positive == pytest.approx(1.0)


def test_base_weights_as_authored_sum_to_090() -> None:
    """Documents spec issue S1: the manifest's W1–W5 sum to 0.90, not 1.0."""
    w = ConfidenceWeights(evidence_strength=0.28, signal_freshness=0.18, source_reliability=0.16,
                          cross_signal_consistency=0.18, domain_stability_modifier=0.10,
                          contradiction_penalty=0.10)
    assert w.positive_total == pytest.approx(0.90)


def test_thresholds_must_be_ordered() -> None:
    with pytest.raises(ValidationError):
        ValidationThresholds(trusted=0.6, provisional=0.85, conflicted=0.3,
                             decay_freshness_floor=0.25)


def test_all_zero_weights_rejected() -> None:
    with pytest.raises(ValidationError):
        ConfidenceWeights(evidence_strength=0, signal_freshness=0, source_reliability=0,
                          cross_signal_consistency=0, domain_stability_modifier=0,
                          contradiction_penalty=0.1)


def test_pack_missing_escalation_priority_rejected(profile: Profile) -> None:
    data = profile.pack("ports").model_dump()
    del data["escalation_routing"]["low"]
    with pytest.raises(ValidationError):
        type(profile.pack("ports")).model_validate(data)


def test_config_hash_is_stable_and_sensitive(profile: Profile) -> None:
    same = Profile.model_validate(profile.model_dump())
    assert same.config_hash == profile.config_hash

    data = profile.model_dump()
    data["packs"]["health"]["half_life_hours"] = 1.5
    assert Profile.model_validate(data).config_hash != profile.config_hash


def test_deep_merge_does_not_mutate_inputs() -> None:
    base = {"a": {"b": 1, "c": 2}}
    merged = deep_merge(base, {"a": {"b": 9}})
    assert merged == {"a": {"b": 9, "c": 2}}
    assert base == {"a": {"b": 1, "c": 2}}


def test_canonical_json_ignores_tzinfo_implementation() -> None:
    from datetime import UTC, datetime, timedelta, timezone

    from antos_core.hashing import sha256_of
    a = {"nested": [{"at": datetime(2026, 1, 1, tzinfo=UTC)}]}
    b = {"nested": [{"at": datetime(2026, 1, 1, tzinfo=timezone(timedelta(0)))}]}
    assert sha256_of(a) == sha256_of(b)
