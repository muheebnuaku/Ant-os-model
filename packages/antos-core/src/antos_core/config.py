"""Profile configuration: the engine-wide manifest plus resolved sector packs.

A profile directory holds ``manifest.yaml`` (with a ``sector_defaults`` block)
and ``sector_packs.yaml``. Each pack is deep-merged over ``sector_defaults``
and then validated, so every engine receives a fully resolved pack.
"""

import math
from collections.abc import Mapping
from functools import cached_property
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from antos_core.contracts import EscalationPriority, SourceType
from antos_core.engines.triggers import RuleSyntaxError, parse
from antos_core.hashing import sha256_of

LN2 = math.log(2)

POSITIVE_WEIGHT_KEYS = (
    "evidence_strength",
    "signal_freshness",
    "source_reliability",
    "cross_signal_consistency",
    "domain_stability_modifier",
)


class Config(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class UnknownSectorError(KeyError):
    pass


# ── Sector pack ──────────────────────────────────────────────


class ConfidenceWeights(Config):
    evidence_strength: float = Field(ge=0)
    signal_freshness: float = Field(ge=0)
    source_reliability: float = Field(ge=0)
    cross_signal_consistency: float = Field(ge=0)
    domain_stability_modifier: float = Field(ge=0)
    contradiction_penalty: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def _has_positive_weight(self) -> "ConfidenceWeights":
        if self.positive_total <= 0:
            raise ValueError("at least one positive confidence weight (W1–W5) must be > 0")
        return self

    @property
    def positive_total(self) -> float:
        return sum(float(getattr(self, k)) for k in POSITIVE_WEIGHT_KEYS)

    def normalized(self) -> dict[str, float]:
        """W1–W5 rescaled to sum to 1.0 (decision S1); W6 kept as authored."""
        total = self.positive_total
        weights = {k: float(getattr(self, k)) / total for k in POSITIVE_WEIGHT_KEYS}
        weights["contradiction_penalty"] = self.contradiction_penalty
        return weights


class ValidationThresholds(Config):
    trusted: float = Field(gt=0, le=1)
    provisional: float = Field(gt=0, le=1)
    conflicted: float = Field(ge=0, le=1)
    decay_freshness_floor: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def _ordered(self) -> "ValidationThresholds":
        if not self.trusted > self.provisional > self.conflicted:
            raise ValueError("thresholds must satisfy trusted > provisional > conflicted")
        return self


class SignalTypeSpec(Config):
    compare_field: str | None = None
    tolerance: float | None = Field(default=None, gt=0, le=1)


class EscalationRoute(Config):
    role: str
    sla_minutes: int = Field(gt=0)


class EscalationRule(Config):
    """A sector escalation rule (see ``engines.triggers`` for the language).
    ``role`` and ``sla_minutes`` override the pack's per-priority routing."""

    id: str = Field(pattern=r"^[a-z0-9_]+$")
    when: str
    priority: EscalationPriority
    role: str | None = None
    sla_minutes: int | None = Field(default=None, gt=0)
    description: str = ""

    @field_validator("when")
    @classmethod
    def _parses(cls, rule: str) -> str:
        try:
            parse(rule)
        except RuleSyntaxError as exc:
            raise ValueError(f"invalid rule: {exc}") from None
        return rule


class Languages(Config):
    primary: str
    secondary: list[str] = Field(default_factory=list)


class SectorPack(Config):
    sector_id: str
    sector_name: str
    jurisdiction: str
    priority_24hae: Literal["CRITICAL", "HIGH", "MEDIUM"]
    half_life_hours: float = Field(gt=0)
    domain_modifier: float = Field(gt=0)
    domain_stability: float = Field(ge=0, le=1)
    domain_sensitivity: float = Field(gt=0)
    confidence_weights: ConfidenceWeights
    validation_thresholds: ValidationThresholds
    default_tolerance: float = Field(gt=0, le=1)
    signal_types: dict[str, SignalTypeSpec] = Field(default_factory=dict)
    eis_warning_threshold: float = Field(gt=0, le=1)
    eis_critical_threshold: float = Field(gt=0, le=1)
    ecology_active_metrics: list[str] = Field(default_factory=list)
    jurisdiction_laws: list[str] = Field(default_factory=list)
    languages: Languages
    infrastructure_profile: Literal[
        "full_connectivity", "intermittent_connectivity", "offline_capable"
    ]
    escalation_routing: dict[EscalationPriority, EscalationRoute]
    escalation_rules: list[EscalationRule] = Field(default_factory=list)
    # Step 14 routing: "sovereign" packs may only use an on-prem model and never
    # fall back to a cloud provider; "rules_only" never calls a model.
    model_route: Literal["default", "sovereign", "rules_only"] = "default"

    @model_validator(mode="after")
    def _consistent(self) -> "SectorPack":
        if self.eis_warning_threshold >= self.eis_critical_threshold:
            raise ValueError("eis_warning_threshold must be below eis_critical_threshold")
        missing = set(EscalationPriority) - set(self.escalation_routing)
        if missing:
            raise ValueError(f"escalation_routing missing priorities: {sorted(missing)}")
        ids = [r.id for r in self.escalation_rules]
        if len(ids) != len(set(ids)):
            raise ValueError("escalation rule ids must be unique within a pack")
        return self

    @property
    def decay_lambda(self) -> float:
        """λ derived from half-life (decision S7): λ = ln2 / t½."""
        return LN2 / self.half_life_hours

    def tolerance_for(self, signal_type: str) -> float:
        spec = self.signal_types.get(signal_type)
        if spec is not None and spec.tolerance is not None:
            return spec.tolerance
        return self.default_tolerance


# ── Engine-wide manifest ─────────────────────────────────────


class ContradictionConfig(Config):
    moderate_from: float = Field(gt=0, le=1)
    severe_from: float = Field(gt=0, le=1)

    @model_validator(mode="after")
    def _ordered(self) -> "ContradictionConfig":
        if self.moderate_from >= self.severe_from:
            raise ValueError("moderate_from must be below severe_from")
        return self


class EcologyConfig(Config):
    component_weights: dict[str, float]
    variable_weights: dict[str, dict[str, float]]

    @model_validator(mode="after")
    def _components_match(self) -> "EcologyConfig":
        if set(self.component_weights) != set(self.variable_weights):
            raise ValueError("component_weights and variable_weights must name the same components")
        return self


class InclusionConfig(Config):
    weights: dict[str, float]
    pass_threshold: float = Field(ge=0, le=1)
    flag_below: float = Field(ge=0, le=1)
    critical_below: float = Field(ge=0, le=1)


class HaeConfig(Config):
    weights: dict[str, float]
    aligned_from: float
    neutral_from: float
    misaligned_from: float


class LocalFitConfig(Config):
    pass_threshold: float = Field(ge=0, le=1)
    hard_fail_dimensions: list[str]


class Manifest(Config):
    name: str
    version: str
    domain_modifier_mode: Literal["none", "multiply"]
    neutral_consistency: float = Field(ge=0, le=1)
    contradiction: ContradictionConfig
    source_reliability: dict[SourceType, float]
    default_source_reliability: float = Field(ge=0, le=1)
    ecology: EcologyConfig
    inclusion: InclusionConfig
    hae: HaeConfig
    local_fit: LocalFitConfig


class Profile(Config):
    manifest: Manifest
    packs: dict[str, SectorPack]

    def pack(self, sector: str) -> SectorPack:
        try:
            return self.packs[sector]
        except KeyError:
            raise UnknownSectorError(sector) from None

    @cached_property
    def config_hash(self) -> str:
        return sha256_of(self.model_dump(mode="json"))


# ── Loading ──────────────────────────────────────────────────


def deep_merge(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, Mapping) and isinstance(merged.get(key), Mapping):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _read_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    return data


def load_profile(directory: str | Path) -> Profile:
    directory = Path(directory)
    return build_profile(_read_yaml(directory / "manifest.yaml"),
                         _read_yaml(directory / "sector_packs.yaml"))


def build_profile(manifest_doc: Mapping[str, Any], packs_doc: Mapping[str, Any]) -> Profile:
    """Build a profile from the two documents as authored (before merging)."""
    defaults = manifest_doc.get("sector_defaults", {})
    packs = {
        sector_id: SectorPack.model_validate(
            deep_merge(defaults, {"sector_id": sector_id, **(overrides or {})})
        )
        for sector_id, overrides in packs_doc["packs"].items()
    }
    return Profile(manifest=Manifest.model_validate(manifest_doc["manifest"]), packs=packs)
