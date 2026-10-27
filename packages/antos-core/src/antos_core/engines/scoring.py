"""Shared helper: weighted mean over the inputs that were actually supplied."""

from collections.abc import Mapping


def partial_weighted_mean(
    values: Mapping[str, float | None], weights: Mapping[str, float]
) -> tuple[float | None, float]:
    """Return (mean over supplied values with weights renormalised, weight coverage).

    Missing values are excluded rather than treated as zero; coverage is the
    share of total weight that was supplied, so callers can show how much of
    the assessment was based on evidence.
    """
    total = sum(weights.values())
    present = {k: (v, w) for k, w in weights.items() if (v := values.get(k)) is not None}
    covered = sum(w for _, w in present.values())
    if total <= 0 or covered <= 0:
        return None, 0.0
    mean = sum(v * w for v, w in present.values()) / covered
    return mean, covered / total
