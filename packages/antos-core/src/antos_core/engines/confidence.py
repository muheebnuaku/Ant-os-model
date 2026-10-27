"""Steps 8–9: confidence calibration and validation state.

C = W1·E + W2·F + W3·R + W4·X + W5·D − W6·P, with W1–W5 normalised to 1.0
(decision S1). The sector domain modifier is recorded but only multiplied in
when the manifest sets ``domain_modifier_mode: multiply`` (decision S2).
"""

from antos_core.config import Profile, SectorPack
from antos_core.contracts import (
    ConfidenceResult,
    ContradictionResult,
    ContradictionSeverity,
    SignalAssessment,
    ValidationState,
)


def score(
    *,
    evidence_strength: float,
    signal_freshness: float,
    source_reliability: float,
    cross_signal_consistency: float,
    domain_stability_modifier: float,
    contradiction_penalty: float,
    pack: SectorPack,
    profile: Profile,
) -> ConfidenceResult:
    inputs = {
        "evidence_strength": evidence_strength,
        "signal_freshness": signal_freshness,
        "source_reliability": source_reliability,
        "cross_signal_consistency": cross_signal_consistency,
        "domain_stability_modifier": domain_stability_modifier,
        "contradiction_penalty": contradiction_penalty,
    }
    for name, value in inputs.items():
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"{name} must be in [0, 1], got {value}")

    weights = pack.confidence_weights.normalized()
    raw = sum(weights[k] * v for k, v in inputs.items() if k != "contradiction_penalty")
    raw -= weights["contradiction_penalty"] * contradiction_penalty

    modifier = pack.domain_modifier if profile.manifest.domain_modifier_mode == "multiply" else 1.0
    confidence = min(1.0, max(0.0, raw * modifier))
    return ConfidenceResult(
        confidence=round(confidence, 6),
        raw_score=round(raw, 6),
        inputs=inputs,
        weights_applied=weights,
        domain_modifier_applied=modifier,
    )


def score_signals(
    assessments: list[SignalAssessment],
    contradiction: ContradictionResult,
    pack: SectorPack,
    profile: Profile,
) -> ConfidenceResult:
    if not assessments:
        raise ValueError("at least one signal is required to compute confidence")
    n = len(assessments)
    consistency = contradiction.consistency
    return score(
        evidence_strength=sum(a.evidence_strength for a in assessments) / n,
        signal_freshness=sum(a.freshness for a in assessments) / n,
        source_reliability=sum(a.source_reliability for a in assessments) / n,
        cross_signal_consistency=(
            consistency if consistency is not None else profile.manifest.neutral_consistency
        ),
        domain_stability_modifier=pack.domain_stability,
        contradiction_penalty=contradiction.max_severity,
        pack=pack,
        profile=profile,
    )


def assign_state(
    confidence: float,
    mean_freshness: float,
    severity: ContradictionSeverity,
    pack: SectorPack,
) -> ValidationState:
    """Map confidence to a validation state.

    Order of precedence: severe contradiction → blocked; below the conflicted
    threshold → blocked; moderate contradiction → conflicted; otherwise by
    score, except that a would-be trusted/provisional result built on stale
    signals (mean freshness under the floor) is ``decayed`` (decision S8).
    """
    t = pack.validation_thresholds
    if severity is ContradictionSeverity.SEVERE or confidence < t.conflicted:
        return ValidationState.BLOCKED
    if severity is ContradictionSeverity.MODERATE:
        return ValidationState.CONFLICTED
    if confidence >= t.provisional and mean_freshness < t.decay_freshness_floor:
        return ValidationState.DECAYED
    if confidence >= t.trusted:
        return ValidationState.TRUSTED
    if confidence >= t.provisional:
        return ValidationState.PROVISIONAL
    return ValidationState.CONFLICTED
