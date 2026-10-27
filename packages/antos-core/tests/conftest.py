from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from antos_core.config import Profile, load_profile
from antos_core.contracts import SignalInput, SourceType

PROFILE_DIR = Path(__file__).resolve().parents[3] / "profiles" / "africa"
NOW = datetime(2026, 10, 25, 12, 0, tzinfo=UTC)


@pytest.fixture(scope="session")
def profile() -> Profile:
    return load_profile(PROFILE_DIR)


def make_signal(
    signal_type: str = "bed_capacity_signal",
    payload: dict[str, Any] | None = None,
    *,
    source_id: str = "korle_bu_emr",
    source_type: SourceType = SourceType.FORMAL_INSTITUTION,
    age_hours: float | None = 0.0,
    raw_hash: str | None = "sha256:abc",
    **kwargs: Any,
) -> SignalInput:
    return SignalInput(
        signal_type=signal_type,
        source_id=source_id,
        source_type=source_type,
        payload=payload if payload is not None else {"occupancy_rate": 0.85, "source_ref": "KBH-1"},
        observed_at=None if age_hours is None else NOW - timedelta(hours=age_hours),
        raw_hash=raw_hash,
        **kwargs,
    )
