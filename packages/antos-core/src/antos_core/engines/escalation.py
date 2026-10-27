"""Step 19: decide whether a human must own the decision, and route it.

Reasons come from the loop's guardrails and from the pack's escalation rules
(``engines.triggers``). The highest priority wins. Among reasons at that
priority, the shortest SLA wins, and its role (a rule's own role, or the
pack's role for that priority) takes the item.
"""

from datetime import datetime, timedelta

from antos_core.config import EscalationRule, SectorPack
from antos_core.contracts import Contract, EscalationPriority
from antos_core.engines.triggers import Facts, evaluate, parse


class EscalationReason(Contract):
    code: str
    priority: EscalationPriority
    message: str
    role: str | None = None  # set by a rule that names its own route
    sla_minutes: int | None = None


def rule_reasons(
    rules: list[EscalationRule], facts: Facts
) -> tuple[list[EscalationReason], list[str]]:
    """Evaluate the pack's rules. Returns the reasons for rules that fired and
    the ids of rules that could not be decided because facts were missing."""
    fired: list[EscalationReason] = []
    undecided: list[str] = []
    for rule in rules:
        result = evaluate(parse(rule.when), facts)
        if result is None:
            undecided.append(rule.id)
        elif result:
            fired.append(EscalationReason(
                code=f"rule:{rule.id}", priority=rule.priority,
                message=rule.description or rule.when,
                role=rule.role, sla_minutes=rule.sla_minutes,
            ))
    return fired, undecided


class EscalationItem(Contract):
    escalation_id: str
    decision_id: str
    sector: str
    nation_id: str
    objective: str
    priority: EscalationPriority
    assigned_role: str
    sla_minutes: int
    due_at: datetime
    reasons: list[EscalationReason]


def highest_priority(reasons: list[EscalationReason]) -> EscalationPriority:
    return max((r.priority for r in reasons), key=lambda p: p.rank)


def route(
    reasons: list[EscalationReason],
    *,
    decision_id: str,
    objective: str,
    nation_id: str,
    pack: SectorPack,
    now: datetime,
) -> EscalationItem | None:
    if not reasons:
        return None
    priority = highest_priority(reasons)
    default = pack.escalation_routing[priority]
    candidates = [
        (r.sla_minutes or default.sla_minutes, r.role or default.role)
        for r in reasons if r.priority is priority
    ]
    sla_minutes, role = min(candidates, key=lambda c: c[0])
    return EscalationItem(
        escalation_id=decision_id.replace("DEC-", "ESC-", 1),
        decision_id=decision_id,
        sector=pack.sector_id,
        nation_id=nation_id,
        objective=objective,
        priority=priority,
        assigned_role=role,
        sla_minutes=sla_minutes,
        due_at=now + timedelta(minutes=sla_minutes),
        reasons=reasons,
    )
