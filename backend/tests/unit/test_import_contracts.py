"""The hand-kept package lists in `pyproject.toml` name every package that exists (SPEC §5.5, ADR-0111)."""

import tomllib
from pathlib import Path

import pytest

BACKEND = Path(__file__).parents[2]
PACKAGE = BACKEND / "src" / "pagercutie"
PYPROJECT = tomllib.loads((BACKEND / "pyproject.toml").read_text())
CONTRACTS: list[dict[str, object]] = PYPROJECT["tool"]["importlinter"]["contracts"]


def packages(parent: Path) -> set[str]:
    return {child.name for child in parent.iterdir() if (child / "__init__.py").is_file()}


STAGES = {f"pagercutie.pipeline.{name}" for name in packages(PACKAGE / "pipeline")}
ENTITIES = {f"pagercutie.{name}" for name in packages(PACKAGE) - {"pipeline"}}


def contract(name: str) -> dict[str, object]:
    return next(c for c in CONTRACTS if c["name"] == name)


def modules(value: object) -> set[str]:
    assert isinstance(value, list)
    return {str(module) for module in value}


@pytest.mark.parametrize(
    ("name", "key"),
    [
        ("Pipeline stages do not import each other", "modules"),
        ("Only the orchestrator chains the stages", "source_modules"),
    ],
)
def test_the_stage_contracts_list_every_stage_package(name: str, key: str) -> None:
    assert modules(contract(name)[key]) == STAGES


def test_the_entity_contract_lists_every_package_outside_the_pipeline() -> None:
    assert modules(contract("Entity packages do not depend on the pipeline")["source_modules"]) == ENTITIES


def test_every_stage_entrypoint_module_has_a_protected_contract() -> None:
    protected = set().union(*(modules(c["protected_modules"]) for c in CONTRACTS if c["type"] == "protected"))

    assert protected == {f"{stage}.stage" for stage in STAGES}


def test_routers_may_import_no_entity_models() -> None:
    banned = PYPROJECT["tool"]["ruff"]["lint"]["flake8-tidy-imports"]["banned-api"]
    models = {f"pagercutie.{path.parent.name}.models" for path in PACKAGE.glob("*/models.py")} - {
        "pagercutie.core.models"
    }

    assert set(banned) == models
