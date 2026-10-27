"""Steps 10–13 and 17: inclusion, 24HAE, ecology (EIS), intra-African trade, local fit."""

from antos_core.config import Profile, SectorPack
from antos_core.contracts import (
    EcologyInput,
    EcologyResult,
    EisState,
    HaeInput,
    HaeResult,
    HaeState,
    InclusionInput,
    InclusionResult,
    InclusionState,
    LocalFitInput,
    LocalFitResult,
)
from antos_core.engines.scoring import partial_weighted_mean

# ── Step 10: inclusion ───────────────────────────────────────


def inclusion(inp: InclusionInput | None, profile: Profile) -> InclusionResult:
    cfg = profile.manifest.inclusion
    values = inp.model_dump() if inp else {}
    mean, coverage = partial_weighted_mean(values, cfg.weights)
    if mean is None:
        return InclusionResult(
            state=InclusionState.NOT_ASSESSED, inclusion_score=None, coverage=0.0,
            flagged_dimensions=[],
        )
    flagged = [d for d in cfg.weights if values.get(d) is not None and values[d] < cfg.flag_below]
    if mean < cfg.critical_below:
        state = InclusionState.CRITICAL_EXCLUSION
    elif mean < cfg.pass_threshold:
        state = InclusionState.EXCLUSIONARY
    else:
        state = InclusionState.INCLUSIVE
    return InclusionResult(
        state=state, inclusion_score=round(mean, 6), coverage=round(coverage, 6),
        flagged_dimensions=flagged,
    )


# ── Steps 11 + 13: 24-Hour Africa Economy alignment ──────────

HAE_FLAGS = {
    "intra_african_value_creation": "NO_INTRA_AFRICAN_VALUE_CREATION",
    "informal_actor_inclusion": "INFORMAL_ACTORS_EXCLUDED",
    "worker_dignity_preserved": "WORKER_DIGNITY_AT_RISK",
    "dependency_reduction": "DEPENDENCY_NOT_REDUCED",
    "data_sovereignty_preserved": "SOVEREIGNTY_AT_RISK",
}


def hae(inp: HaeInput | None, profile: Profile) -> HaeResult:
    cfg = profile.manifest.hae
    raw = inp.model_dump() if inp else {}

    # Productive capacity is in [-1, 1]; map to [0, 1]. Booleans count as 1/0.
    values: dict[str, float | None] = {}
    for key in cfg.weights:
        v = raw.get(key)
        if v is None:
            values[key] = None
        elif key == "productive_capacity_impact":
            values[key] = (float(v) + 1.0) / 2.0
        else:
            values[key] = 1.0 if v else 0.0

    flags = []
    if raw.get("productive_capacity_impact") is not None and raw["productive_capacity_impact"] < 0:
        flags.append("REDUCES_PRODUCTIVE_CAPACITY")
    flags += [flag for key, flag in HAE_FLAGS.items() if raw.get(key) is False]

    mean, coverage = partial_weighted_mean(values, cfg.weights)
    if mean is None:
        state = HaeState.NOT_ASSESSED
    elif mean >= cfg.aligned_from:
        state = HaeState.ALIGNED
    elif mean >= cfg.neutral_from:
        state = HaeState.NEUTRAL
    elif mean >= cfg.misaligned_from:
        state = HaeState.MISALIGNED
    else:
        state = HaeState.CRITICAL
    return HaeResult(
        state=state,
        hae_alignment_score=None if mean is None else round(mean, 6),
        coverage=round(coverage, 6),
        policy_flags=flags,
        intra_african_aligned=raw.get("intra_african_value_creation"),
    )


# ── Step 12: Ecology Impact Score ────────────────────────────


def ecology(inp: EcologyInput | None, pack: SectorPack, profile: Profile) -> EcologyResult:
    cfg = profile.manifest.ecology
    components: dict[str, float | None] = {}
    component_coverage: dict[str, float] = {}
    for name, var_weights in cfg.variable_weights.items():
        values = getattr(inp, name).model_dump() if inp else {}
        components[name], component_coverage[name] = partial_weighted_mean(values, var_weights)

    eis, _ = partial_weighted_mean(components, cfg.component_weights)
    total = sum(cfg.component_weights.values())
    coverage = sum(cfg.component_weights[c] * component_coverage[c] for c in components) / total

    if eis is None:
        state, action = EisState.NOT_ASSESSED, "assess_before_action"
    elif eis >= pack.eis_critical_threshold:
        state = EisState.CRITICAL
        action = "block" if inp and inp.irreversible else "escalate"
    elif eis >= pack.eis_warning_threshold:
        state, action = EisState.WARNING, "modify_decision_and_flag"
    else:
        state, action = EisState.ACCEPTABLE, "allow_with_logging"
    return EcologyResult(
        state=state,
        eis_score=None if eis is None else round(eis, 6),
        component_scores={k: None if v is None else round(v, 6) for k, v in components.items()},
        coverage=round(coverage, 6),
        enforcement_action=action,
    )


# ── Step 17: local fit test ──────────────────────────────────

REMEDIATION = {
    "institutional_alignment": "Update the sector pack to match the institution's organogram.",
    "linguistic_appropriateness": "Add output localisation for the target operator language.",
    "infrastructure_feasibility": "Add an offline or async delivery pathway for this output.",
    "cultural_safety": "Add cultural context notes to the sector pack and re-run.",
    "regulatory_grounding": "Update jurisdiction_laws in the sector pack and recheck statutes.",
    "resource_realism": "Add resource constraint parameters to the sector pack and re-scope.",
}


def local_fit(inp: LocalFitInput | None, pack: SectorPack, profile: Profile) -> LocalFitResult:
    cfg = profile.manifest.local_fit
    dims: dict[str, bool | None] = dict(inp.model_dump()) if inp else dict.fromkeys(REMEDIATION)

    # Automatic check from pack data: no governing law configured = not grounded.
    if not pack.jurisdiction_laws:
        dims["regulatory_grounding"] = False

    evaluated = [d for d, v in dims.items() if v is not None]
    failed = [d for d in evaluated if dims[d] is False]
    not_assessed = [d for d, v in dims.items() if v is None]
    hard_fail = any(d in cfg.hard_fail_dimensions for d in failed)

    if not evaluated:
        return LocalFitResult(
            assessed=False, local_fit_passed=None, overall_score=None,
            dimensions_evaluated=[], dimensions_failed=[], dimensions_not_assessed=not_assessed,
            hard_fail_triggered=False, escalation_triggered=False, recommended_remediation=[],
        )

    score = (len(evaluated) - len(failed)) / len(evaluated)
    passed = score >= cfg.pass_threshold and not hard_fail
    return LocalFitResult(
        assessed=True,
        local_fit_passed=passed,
        overall_score=round(score, 6),
        dimensions_evaluated=evaluated,
        dimensions_failed=failed,
        dimensions_not_assessed=not_assessed,
        hard_fail_triggered=hard_fail,
        escalation_triggered=not passed,
        recommended_remediation=[REMEDIATION[d] for d in failed],
    )
