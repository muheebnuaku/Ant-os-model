"""Steps 1–5: ingest, classify, attach provenance, freshness, source reliability."""

from datetime import datetime

from antos_core.config import Manifest, Profile, SectorPack
from antos_core.contracts import Signal, SignalAssessment, SignalInput
from antos_core.hashing import short_id

SOURCE_REF_KEYS = ("source_ref", "reference")


def normalize_signal(raw: SignalInput, *, sector: str, nation_id: str, now: datetime) -> Signal:
    """Steps 1–3. The signal ID is derived from content so re-ingest is idempotent."""
    resolved_sector = raw.sector or sector
    signal_id = raw.signal_id or short_id(
        "SIG",
        {
            "signal_type": raw.signal_type,
            "source_id": raw.source_id,
            "observed_at": raw.observed_at,
            "payload": raw.payload,
        },
    )
    return Signal(
        signal_id=signal_id,
        signal_type=raw.signal_type,
        source_id=raw.source_id,
        source_type=raw.source_type,
        sector=resolved_sector,
        nation_id=nation_id,
        payload=raw.payload,
        observed_at=raw.observed_at,
        received_at=raw.received_at or now,
        raw_hash=raw.raw_hash,
    )


def freshness(age_hours: float, half_life_hours: float) -> float:
    """F = exp(-λt) with λ = ln2 / t½, i.e. 0.5 ** (t / t½). Negative ages clamp to 0."""
    return float(0.5 ** (max(age_hours, 0.0) / half_life_hours))


def signal_age(signal: Signal, now: datetime) -> tuple[float, str]:
    """Age from the source's observation time; falls back to receipt time (decision S8)."""
    if signal.observed_at is not None:
        return (now - signal.observed_at).total_seconds() / 3600, "observed"
    return (now - signal.received_at).total_seconds() / 3600, "received"


def evidence_strength(signal: Signal, pack: SectorPack) -> float:
    """Heuristic evidence score in [0, 1]; components sum to exactly 1.0.

    base 0.30 · measurable value 0.25 · cited source 0.15 · observation time 0.15
    · raw lineage hash 0.15. A declared ``compare_field`` must be numeric to
    count as measurable; undeclared types earn a reduced 0.10 for any number.
    """
    score = 0.30
    spec = pack.signal_types.get(signal.signal_type)
    if spec is not None and spec.compare_field is not None:
        if _is_number(signal.payload.get(spec.compare_field)):
            score += 0.25
    elif any(_is_number(v) for v in signal.payload.values()):
        score += 0.10
    if any(signal.payload.get(k) for k in SOURCE_REF_KEYS):
        score += 0.15
    if signal.observed_at is not None:
        score += 0.15
    if signal.raw_hash:
        score += 0.15
    return round(min(score, 1.0), 6)


def source_reliability(signal: Signal, manifest: Manifest) -> float:
    return manifest.source_reliability.get(signal.source_type, manifest.default_source_reliability)


def assess_signal(signal: Signal, profile: Profile, now: datetime) -> SignalAssessment:
    pack = profile.pack(signal.sector)
    age, basis = signal_age(signal, now)
    return SignalAssessment(
        signal_id=signal.signal_id,
        age_hours=round(age, 6),
        timestamp_basis=basis,
        freshness=round(freshness(age, pack.half_life_hours), 6),
        evidence_strength=evidence_strength(signal, pack),
        source_reliability=source_reliability(signal, profile.manifest),
    )


def _is_number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)
