"""Data contracts shared by every engine and the reasoning loop.

Design rule (plan §5.5): unknown is never scored as zero. Every optional
assessment carries an explicit ``not_assessed`` state and a coverage figure.
"""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Contract(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


# ── Enumerations ─────────────────────────────────────────────


class SourceType(StrEnum):
    FORMAL_INSTITUTION = "formal_institution"
    API_FEED = "api_feed"
    SATELLITE = "satellite"
    INFORMAL_OPERATOR = "informal_operator"
    COMMUNITY_SOURCE = "community_source"
    MANUAL_ENTRY = "manual_entry"


class ValidationState(StrEnum):
    TRUSTED = "trusted"
    PROVISIONAL = "provisional"
    CONFLICTED = "conflicted"
    DECAYED = "decayed"
    BLOCKED = "blocked"


class ContradictionSeverity(StrEnum):
    NONE = "none"
    MINOR = "minor"
    MODERATE = "moderate"
    SEVERE = "severe"


class EisState(StrEnum):
    NOT_ASSESSED = "not_assessed"
    ACCEPTABLE = "acceptable"
    WARNING = "warning"
    CRITICAL = "critical"


class InclusionState(StrEnum):
    NOT_ASSESSED = "not_assessed"
    INCLUSIVE = "inclusive"
    EXCLUSIONARY = "exclusionary"
    CRITICAL_EXCLUSION = "critical_exclusion"


class HaeState(StrEnum):
    NOT_ASSESSED = "not_assessed"
    ALIGNED = "aligned"
    NEUTRAL = "neutral"
    MISALIGNED = "misaligned"
    CRITICAL = "critical"


class Action(StrEnum):
    PROCEED = "proceed"
    DEFER = "defer"
    INVESTIGATE = "investigate"
    ESCALATE = "escalate"
    BLOCK = "block"

    @property
    def caution(self) -> int:
        return _ACTION_CAUTION[self]


_ACTION_CAUTION = {
    Action.PROCEED: 0,
    Action.DEFER: 1,
    Action.INVESTIGATE: 2,
    Action.ESCALATE: 3,
    Action.BLOCK: 4,
}


class EscalationPriority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    @property
    def rank(self) -> int:
        return _PRIORITY_RANK[self]


_PRIORITY_RANK = {
    EscalationPriority.LOW: 0,
    EscalationPriority.MEDIUM: 1,
    EscalationPriority.HIGH: 2,
    EscalationPriority.CRITICAL: 3,
}


# ── Signals ──────────────────────────────────────────────────


class SignalInput(Contract):
    """A signal as submitted by an adapter or operator."""

    signal_type: str
    source_id: str
    source_type: SourceType = SourceType.MANUAL_ENTRY
    payload: dict[str, Any] = Field(default_factory=dict)
    sector: str | None = None
    signal_id: str | None = None
    observed_at: datetime | None = None
    received_at: datetime | None = None
    raw_hash: str | None = None


class Signal(Contract):
    """A normalised signal with provenance attached (steps 1–3)."""

    signal_id: str
    signal_type: str
    source_id: str
    source_type: SourceType
    sector: str
    nation_id: str
    payload: dict[str, Any]
    observed_at: datetime | None
    received_at: datetime
    raw_hash: str | None


class SignalAssessment(Contract):
    """Per-signal validation results (steps 4–5)."""

    signal_id: str
    age_hours: float
    timestamp_basis: str  # "observed" | "received"
    freshness: float
    evidence_strength: float
    source_reliability: float


# ── Optional context inputs (None = not assessed) ────────────


class EnvironmentalImpact(Contract):
    carbon_emission_delta: float | None = Field(default=None, ge=0, le=1)
    land_use_change_risk: float | None = Field(default=None, ge=0, le=1)
    water_contamination_risk: float | None = Field(default=None, ge=0, le=1)
    biodiversity_disruption_index: float | None = Field(default=None, ge=0, le=1)
    waste_generation_level: float | None = Field(default=None, ge=0, le=1)


class SocialImpact(Contract):
    community_displacement_risk: float | None = Field(default=None, ge=0, le=1)
    health_risk_to_population: float | None = Field(default=None, ge=0, le=1)
    equity_impact_score: float | None = Field(default=None, ge=0, le=1)
    cultural_heritage_risk: float | None = Field(default=None, ge=0, le=1)
    livelihood_disruption_index: float | None = Field(default=None, ge=0, le=1)


class ResourceStress(Contract):
    water_extraction_rate: float | None = Field(default=None, ge=0, le=1)
    energy_demand_stress: float | None = Field(default=None, ge=0, le=1)
    soil_degradation_index: float | None = Field(default=None, ge=0, le=1)
    infrastructure_load_factor: float | None = Field(default=None, ge=0, le=1)
    raw_material_depletion_risk: float | None = Field(default=None, ge=0, le=1)


class EcologyInput(Contract):
    environmental_impact: EnvironmentalImpact = EnvironmentalImpact()
    social_impact: SocialImpact = SocialImpact()
    resource_stress: ResourceStress = ResourceStress()
    irreversible: bool = False


class InclusionInput(Contract):
    informal_economy_inclusion: float | None = Field(default=None, ge=0, le=1)
    rural_and_agricultural_inclusion: float | None = Field(default=None, ge=0, le=1)
    gender_equity: float | None = Field(default=None, ge=0, le=1)
    youth_inclusion: float | None = Field(default=None, ge=0, le=1)
    disability_and_vulnerability: float | None = Field(default=None, ge=0, le=1)


class HaeInput(Contract):
    productive_capacity_impact: float | None = Field(default=None, ge=-1, le=1)
    intra_african_value_creation: bool | None = None
    informal_actor_inclusion: bool | None = None
    worker_dignity_preserved: bool | None = None
    dependency_reduction: bool | None = None
    data_sovereignty_preserved: bool | None = None


class LocalFitInput(Contract):
    institutional_alignment: bool | None = None
    linguistic_appropriateness: bool | None = None
    infrastructure_feasibility: bool | None = None
    cultural_safety: bool | None = None
    regulatory_grounding: bool | None = None
    resource_realism: bool | None = None


# ── Engine results ───────────────────────────────────────────


class Conflict(Contract):
    signal_a: str
    signal_b: str
    signal_type: str
    field: str
    value_a: float
    value_b: float
    relative_difference: float
    tolerance: float
    severity: float


class ContradictionResult(Contract):
    comparable_pairs: int
    agreeing_pairs: int
    conflicts: list[Conflict]
    max_severity: float
    severity_label: ContradictionSeverity
    consistency: float | None  # None when no comparable pairs exist
    recommended_action: str

    @property
    def contradiction_count(self) -> int:
        return len(self.conflicts)


class ConfidenceResult(Contract):
    confidence: float
    raw_score: float
    inputs: dict[str, float]
    weights_applied: dict[str, float]
    domain_modifier_applied: float


class EcologyResult(Contract):
    state: EisState
    eis_score: float | None
    component_scores: dict[str, float | None]
    coverage: float
    enforcement_action: str


class InclusionResult(Contract):
    state: InclusionState
    inclusion_score: float | None
    coverage: float
    flagged_dimensions: list[str]


class HaeResult(Contract):
    state: HaeState
    hae_alignment_score: float | None
    coverage: float
    policy_flags: list[str]
    intra_african_aligned: bool | None


class LocalFitResult(Contract):
    assessed: bool
    local_fit_passed: bool | None
    overall_score: float | None
    dimensions_evaluated: list[str]
    dimensions_failed: list[str]
    dimensions_not_assessed: list[str]
    hard_fail_triggered: bool
    escalation_triggered: bool
    recommended_remediation: list[str]
