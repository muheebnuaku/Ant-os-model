"""Escalation rule language for sector packs (step 19).

A rule is a boolean expression over *facts* about one decision::

    bed_capacity_signal.occupancy_rate > 90% AND disease_outbreak_signal.status = confirmed

Grammar (keywords are case-insensitive)::

    expr       := and_expr ("OR" and_expr)*
    and_expr   := unary ("AND" unary)*
    unary      := "NOT" unary | "(" expr ")" | comparison
    comparison := path OP (literal | path)
    OP         := < | <= | > | >= | = | == | !=
    literal    := number | number% | 'string' | "string" | true | false | symbol

A *path* contains a dot (``signal_type.field``) or names a decision fact
(``confidence``, ``contradiction_severity``, …). On the right-hand side a bare
word without a dot is a symbol literal, so ``status = confirmed`` compares with
the string "confirmed". ``30%`` means 0.30: rates in payloads are fractions.

Evaluation uses three-valued logic. A missing fact or a type mismatch makes a
comparison *unknown*, and a rule fires only when the whole expression is
definitely true, so missing data can never trigger an escalation (not even
through ``NOT``). There is no ``eval``: rules are parsed by hand.
"""

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal, cast

FactValue = float | bool | str
Facts = Mapping[str, FactValue]

DECISION_FACTS = frozenset({
    "sector", "nation_id", "validation_state", "confidence", "mean_freshness",
    "contradiction_severity", "contradiction_count", "high_consequence",
    "eis_score", "inclusion_score", "hae_alignment_score",
})

# Ordered vocabularies: two symbols from the same scale compare by rank.
ORDINAL_SCALES: tuple[tuple[str, ...], ...] = (
    ("none", "minor", "moderate", "severe"),
    ("low", "medium", "high", "critical"),
)

_RANK = {word: (i, scale) for scale, words in enumerate(ORDINAL_SCALES)
         for i, word in enumerate(words)}

Op = Literal["<", "<=", ">", ">=", "=", "!="]


class RuleSyntaxError(ValueError):
    pass


# ── AST ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class Path:
    name: str


@dataclass(frozen=True)
class Value:
    value: FactValue


@dataclass(frozen=True)
class Compare:
    left: Path
    op: Op
    right: Path | Value


@dataclass(frozen=True)
class Not:
    operand: "Node"


@dataclass(frozen=True)
class BoolOp:
    op: Literal["and", "or"]
    operands: tuple["Node", ...]


Node = Compare | Not | BoolOp


# ── Tokenizer and parser ─────────────────────────────────────

_TOKEN = re.compile(r"""
    \s*(?:
      (?P<num>-?\d+(?:\.\d+)?%?)
    | (?P<str>'[^']*'|"[^"]*")
    | (?P<op><=|>=|!=|==|<|>|=)
    | (?P<lp>\() | (?P<rp>\))
    | (?P<word>[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)
    )""", re.VERBOSE)

_KEYWORDS = {"and", "or", "not", "true", "false"}


def _tokenize(text: str) -> list[tuple[str, str]]:
    tokens: list[tuple[str, str]] = []
    pos = 0
    text = text.rstrip()
    while pos < len(text):
        m = _TOKEN.match(text, pos)
        if m is None or m.end() == pos:
            raise RuleSyntaxError(f"unexpected character at {pos}: {text[pos:pos + 12]!r}")
        kind = m.lastgroup
        assert kind is not None
        value = m.group(kind)
        if kind == "word" and value.lower() in _KEYWORDS:
            kind, value = "kw", value.lower()
        tokens.append((kind, value))
        pos = m.end()
    return tokens


class _Parser:
    def __init__(self, text: str) -> None:
        self.tokens = _tokenize(text)
        self.i = 0

    def peek(self) -> tuple[str, str] | None:
        return self.tokens[self.i] if self.i < len(self.tokens) else None

    def take(self) -> tuple[str, str]:
        tok = self.peek()
        if tok is None:
            raise RuleSyntaxError("unexpected end of rule")
        self.i += 1
        return tok

    def accept_kw(self, word: str) -> bool:
        if self.peek() == ("kw", word):
            self.i += 1
            return True
        return False

    def parse(self) -> Node:
        node = self.expr()
        extra = self.peek()
        if extra is not None:
            raise RuleSyntaxError(f"unexpected token {extra[1]!r}")
        return node

    def expr(self) -> Node:
        operands = [self.and_expr()]
        while self.accept_kw("or"):
            operands.append(self.and_expr())
        return operands[0] if len(operands) == 1 else BoolOp("or", tuple(operands))

    def and_expr(self) -> Node:
        operands = [self.unary()]
        while self.accept_kw("and"):
            operands.append(self.unary())
        return operands[0] if len(operands) == 1 else BoolOp("and", tuple(operands))

    def unary(self) -> Node:
        if self.accept_kw("not"):
            return Not(self.unary())
        if self.peek() == ("lp", "("):
            self.take()
            node = self.expr()
            if self.take() != ("rp", ")"):
                raise RuleSyntaxError("expected ')'")
            return node
        return self.comparison()

    def comparison(self) -> Compare:
        kind, value = self.take()
        if kind != "word":
            raise RuleSyntaxError(f"expected a fact name, got {value!r}")
        if "." not in value and value not in DECISION_FACTS:
            raise RuleSyntaxError(
                f"unknown fact {value!r}: use signal_type.field or one of {sorted(DECISION_FACTS)}"
            )
        kind, op = self.take()
        if kind != "op":
            raise RuleSyntaxError(f"expected a comparison operator after {value!r}, got {op!r}")
        return Compare(Path(value), cast(Op, "=" if op == "==" else op), self.operand())

    def operand(self) -> Path | Value:
        kind, value = self.take()
        if kind == "num":
            if value.endswith("%"):
                return Value(float(value[:-1]) / 100)
            return Value(float(value))
        if kind == "str":
            return Value(value[1:-1])
        if kind == "kw" and value in ("true", "false"):
            return Value(value == "true")
        if kind == "word":
            return Path(value) if "." in value else Value(value)
        raise RuleSyntaxError(f"expected a value, got {value!r}")


@lru_cache(maxsize=1024)
def parse(rule: str) -> Node:
    if not rule.strip():
        raise RuleSyntaxError("empty rule")
    return _Parser(rule).parse()


# ── Evaluation (Kleene three-valued logic) ───────────────────

Truth = bool | None  # None = unknown


def _compare(a: FactValue, op: Op, b: FactValue) -> Truth:
    if isinstance(a, bool) or isinstance(b, bool):
        if not (isinstance(a, bool) and isinstance(b, bool)) or op not in ("=", "!="):
            return None
        return (a == b) == (op == "=")
    if isinstance(a, float) and isinstance(b, float):
        left, right = a, b
    elif isinstance(a, str) and isinstance(b, str):
        a_l, b_l = a.lower(), b.lower()
        if op in ("=", "!="):
            return (a_l == b_l) == (op == "=")
        ra, rb = _RANK.get(a_l), _RANK.get(b_l)
        if ra is None or rb is None or ra[1] != rb[1]:
            return None
        left, right = float(ra[0]), float(rb[0])
    else:
        return None
    match op:
        case "<":
            return left < right
        case "<=":
            return left <= right
        case ">":
            return left > right
        case ">=":
            return left >= right
        case "=":
            return math.isclose(left, right, rel_tol=1e-9, abs_tol=1e-12)
        case "!=":
            return not math.isclose(left, right, rel_tol=1e-9, abs_tol=1e-12)


def evaluate(node: Node, facts: Facts) -> Truth:
    match node:
        case Compare(left, op, right):
            a = facts.get(left.name)
            b = facts.get(right.name) if isinstance(right, Path) else right.value
            if a is None or b is None:
                return None
            return _compare(a, op, b)
        case Not(operand):
            value = evaluate(operand, facts)
            return None if value is None else not value
        case BoolOp("and", operands):
            results = [evaluate(o, facts) for o in operands]
            if False in results:
                return False
            return None if None in results else True
        case BoolOp(_, operands):
            results = [evaluate(o, facts) for o in operands]
            if True in results:
                return True
            return None if None in results else False
    raise TypeError(f"not a rule node: {node!r}")  # pragma: no cover


def fact_value(value: object) -> FactValue | None:
    """Coerce a payload value to a fact. Lists, mappings and NaN are not facts."""
    if isinstance(value, bool | str):
        return value
    if isinstance(value, int | float) and not math.isnan(value):
        return float(value)
    return None
