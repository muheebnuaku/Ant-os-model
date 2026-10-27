"""Step 7: contradiction graph engine.

Tolerance is a *relative* difference on the field each signal type declares
(decision S5): rel = |a − b| / max(|a|, |b|). Severity follows the manifest
model S = impact × confidence × domain_sensitivity, where impact is the
relative difference and confidence is the mean reliability of the two sources.
"""

from itertools import combinations

from antos_core.config import Profile
from antos_core.contracts import (
    Conflict,
    ContradictionResult,
    ContradictionSeverity,
    Signal,
    SignalAssessment,
)

ACTIONS = {
    ContradictionSeverity.NONE: "proceed",
    ContradictionSeverity.MINOR: "downgrade_confidence",
    ContradictionSeverity.MODERATE: "mark_conflicted",
    ContradictionSeverity.SEVERE: "block_and_escalate",
}


def relative_difference(a: float, b: float) -> float:
    scale = max(abs(a), abs(b))
    return 0.0 if scale == 0 else abs(a - b) / scale


def classify(severity: float, has_conflict: bool, profile: Profile) -> ContradictionSeverity:
    if not has_conflict:
        return ContradictionSeverity.NONE
    cfg = profile.manifest.contradiction
    if severity >= cfg.severe_from:
        return ContradictionSeverity.SEVERE
    if severity >= cfg.moderate_from:
        return ContradictionSeverity.MODERATE
    return ContradictionSeverity.MINOR


def evaluate(
    signals: list[Signal],
    assessments: dict[str, SignalAssessment],
    profile: Profile,
) -> ContradictionResult:
    comparable = agreeing = 0
    conflicts: list[Conflict] = []

    for a, b in combinations(signals, 2):
        if a.signal_type != b.signal_type or a.sector != b.sector:
            continue
        pack = profile.pack(a.sector)
        spec = pack.signal_types.get(a.signal_type)
        if spec is None or spec.compare_field is None:
            continue
        field = spec.compare_field
        va, vb = a.payload.get(field), b.payload.get(field)
        if not (_is_number(va) and _is_number(vb)):
            continue

        comparable += 1
        rel = relative_difference(float(va), float(vb))  # type: ignore[arg-type]
        tolerance = pack.tolerance_for(a.signal_type)
        if rel <= tolerance:
            agreeing += 1
            continue

        pair_confidence = (
            assessments[a.signal_id].source_reliability
            + assessments[b.signal_id].source_reliability
        ) / 2
        severity = min(1.0, min(rel, 1.0) * pair_confidence * pack.domain_sensitivity)
        conflicts.append(
            Conflict(
                signal_a=a.signal_id,
                signal_b=b.signal_id,
                signal_type=a.signal_type,
                field=field,
                value_a=float(va),  # type: ignore[arg-type]
                value_b=float(vb),  # type: ignore[arg-type]
                relative_difference=round(rel, 6),
                tolerance=tolerance,
                severity=round(severity, 6),
            )
        )

    max_severity = max((c.severity for c in conflicts), default=0.0)
    label = classify(max_severity, bool(conflicts), profile)
    return ContradictionResult(
        comparable_pairs=comparable,
        agreeing_pairs=agreeing,
        conflicts=conflicts,
        max_severity=max_severity,
        severity_label=label,
        consistency=(agreeing / comparable) if comparable else None,
        recommended_action=ACTIONS[label],
    )


def _is_number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)
