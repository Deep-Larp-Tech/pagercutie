"""Rule condition AST (SPEC §4.3). A discriminated union on `op`.

Adding a node: add the model to `Condition`, regenerate the contract, then handle it everywhere the type
checkers point at (SPEC §4.4).
"""

from typing import Annotated, Literal, assert_never

from pydantic import AfterValidator, Field

from pagercutie.core.schemas import FieldPath, InputModel

type Scalar = str | int | float | bool | None

type Condition = Annotated[
    And | Or | Not | Compare | In | Contains | Glob | Exists,
    Field(discriminator="op"),
]


class And(InputModel):
    op: Literal["and"]
    args: list[Condition] = Field(min_length=1)


class Or(InputModel):
    op: Literal["or"]
    args: list[Condition] = Field(min_length=1)


class Not(InputModel):
    op: Literal["not"]
    arg: Condition


class Compare(InputModel):
    op: Literal["eq", "ne", "gt", "gte", "lt", "lte"]
    field: FieldPath
    value: Scalar


class In(InputModel):
    op: Literal["in", "not_in"]
    field: FieldPath
    value: list[Scalar] = Field(min_length=1)


class Contains(InputModel):
    """Substring for strings, membership for arrays."""

    op: Literal["contains"]
    field: FieldPath
    value: Scalar


class Glob(InputModel):
    """Shell-style wildcards: `pricing-engine-*`, `trade.rejected.*`."""

    op: Literal["glob"]
    field: FieldPath
    value: str


class Exists(InputModel):
    op: Literal["exists"]
    field: FieldPath


MAX_DEPTH = 32
"""Deepest allowed condition nesting; a leaf counts 1. Keeps evaluation free of `RecursionError` (SPEC §4.3)."""


def depth(condition: Condition) -> int:
    """Nesting depth of `condition`: 1 for a predicate, 1 + the deepest argument for a group."""
    match condition:
        case And(args=args) | Or(args=args):
            return 1 + max(depth(arg) for arg in args)
        case Not(arg=arg):
            return 1 + depth(arg)
        case Compare() | In() | Contains() | Glob() | Exists():
            return 1
        case _:
            assert_never(condition)


def _within_max_depth(condition: Condition) -> Condition:
    if depth(condition) > MAX_DEPTH:
        raise ValueError(f"condition is nested deeper than {MAX_DEPTH} levels")
    return condition


# A plain alias, not a `type` statement: Pydantic gives `type` aliases their own `$defs` entry in the contract.
BoundedCondition = Annotated[Condition, AfterValidator(_within_max_depth)]
