"""Writes the standalone JSON Schemas of the rule and runbook models (SPEC §4.3) into the given directory."""

import json
import sys
from pathlib import Path

from pydantic import TypeAdapter

from pagercutie.rules.schemas import RuleCreate
from pagercutie.runbooks.schemas import StructuredRunbook

_SCHEMAS = {
    "rule.schema.json": TypeAdapter(RuleCreate),
    "runbook.schema.json": TypeAdapter(StructuredRunbook),
}

out = Path(sys.argv[1])
for name, adapter in _SCHEMAS.items():
    schema = {"$schema": "https://json-schema.org/draft/2020-12/schema", **adapter.json_schema()}
    (out / name).write_text(json.dumps(schema, indent=2) + "\n")
