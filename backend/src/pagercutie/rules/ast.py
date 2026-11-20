"""Rule condition AST (SPEC §4.3). A discriminated union on `op`.

Adding a node: add the model to `Condition`, regenerate the contract, then handle it everywhere the type
checkers point at (SPEC §4.4).
"""

from typing import Annotated, Literal

from pydantic import Field

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
