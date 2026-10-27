"""Step 14: reason over options with the Ubuntu lens.

This is the only step where a language model may take part. A recommender sees
the deterministic results but cannot change them: its output carries no
scores or states, only an action from a fixed enum, narrative text, and the
IDs of the signals it relied on. Step 16 then checks it (see ``loop.postcheck``).
"""

from typing import Protocol

from pydantic import Field

from antos_core.contracts import (
    Action,
    Contract,
    ContradictionSeverity,
    EcologyResult,
    HaeResult,
    InclusionResult,
    Signal,
    ValidationState,
)


class RecommendationContext(Contract):
    objective: str
    sector: str
    nation_id: str
    signals: list[Signal]
    validation_state: ValidationState
    confidence: float
    contradiction_severity: ContradictionSeverity
    contradiction_count: int
    inclusion: InclusionResult
    hae: HaeResult
    ecology: EcologyResult
    high_consequence: bool


class Recommendation(Contract):
    action: Action
    primary_recommendation: str
    secondary_recommendations: list[str] = Field(default_factory=list)
    ubuntu_note: str = ""
    hae_note: str = ""
    escalation_suggested: bool = False
    cited_signal_ids: list[str] = Field(default_factory=list)
    produced_by: str  # "rule_based" or "llm:<model-id>"
    note: str = ""


class Recommender(Protocol):
    async def recommend(self, ctx: RecommendationContext) -> Recommendation: ...


class RuleBasedRecommender:
    """Deterministic recommender. Used offline, when no model is bound, and as the
    fallback whenever a model call fails — the reasoning loop never stops."""

    async def recommend(self, ctx: RecommendationContext) -> Recommendation:
        return self.recommend_sync(ctx)

    def recommend_sync(self, ctx: RecommendationContext, note: str = "") -> Recommendation:
        state = ctx.validation_state
        if state is ValidationState.BLOCKED:
            action = Action.BLOCK
            primary = "Evidence is insufficient or unsafe. Gather verified signals before acting."
        elif state is ValidationState.CONFLICTED or ctx.contradiction_count:
            action = Action.INVESTIGATE
            primary = "Signals disagree. Resolve the conflicts before committing to action."
        elif state is ValidationState.DECAYED:
            action = Action.DEFER
            primary = "Signals are stale. Refresh them from the primary source before acting."
        elif state is ValidationState.TRUSTED:
            action = Action.PROCEED
            primary = f"Confidence {ctx.confidence:.0%} supports action on: {ctx.objective}"
        else:
            action = Action.DEFER
            primary = (
                f"Provisional confidence ({ctx.confidence:.0%}). "
                "Verify with an independent source before acting."
            )

        if "WORKER_DIGNITY_AT_RISK" in ctx.hae.policy_flags:
            action = max(action, Action.ESCALATE, key=lambda a: a.caution)
            primary = "Worker dignity risk detected. Escalate to the sector lead before any action."

        return Recommendation(
            action=action,
            primary_recommendation=primary,
            secondary_recommendations=[
                "Record every signal source for the audit trail.",
                "Notify the responsible sector lead of the outcome.",
            ],
            ubuntu_note="Consult the community actors affected before implementation.",
            hae_note="Confirm the action sustains 24-hour productive continuity.",
            cited_signal_ids=[s.signal_id for s in ctx.signals],
            produced_by="rule_based",
            note=note,
        )
