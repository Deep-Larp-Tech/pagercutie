import pytest
from pydantic import ValidationError

from pagercutie.core.enums import Role
from pagercutie.core.settings import Settings


def test_default_role_is_api_alone() -> None:
    assert Settings().roles == {Role.API}


@pytest.mark.parametrize(
    ("value", "roles"),
    [
        ("dedup", {Role.DEDUP}),
        ("worker", {Role.EVALUATOR, Role.DEDUP, Role.DISPATCHER, Role.EXECUTOR}),
        ("all", set(Role)),
    ],
)
def test_roles_are_read_from_the_environment(monkeypatch: pytest.MonkeyPatch, value: str, roles: set[Role]) -> None:
    monkeypatch.setenv("APP_ROLES", value)

    assert Settings().roles == roles


def test_unknown_role_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate({"roles": "scheduler"})
