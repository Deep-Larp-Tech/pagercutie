from typing import TypeAliasType, get_args

from pagercutie.runbooks.steps import AddedStep, Step, Wait


def _actions(alias: TypeAliasType) -> set[str]:
    """The `action` literals of a step union declared as `type X = Annotated[A | B | …, Field(discriminator=…)]`."""
    union = get_args(alias.__value__)[0]
    return {get_args(model.model_fields["action"].annotation)[0] for model in get_args(union)}


def test_every_action_except_wait_can_be_added() -> None:
    wait = get_args(Wait.model_fields["action"].annotation)[0]
    assert _actions(AddedStep) == _actions(Step) - {wait}
