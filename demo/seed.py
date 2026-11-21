"""Seeds the demo: one team with members and a rotation, event schemas, sources of every type and alert rules.

Idempotent: existing teams, users, schemas and sources are reused by slug, email or name. Every run rotates the source
tokens and writes them to the state file that `load.py` reads. Routes that still answer 501 are reported, not fatal.
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import httpx

DRAFT = "https://json-schema.org/draft/2020-12/schema"

TEAM = {"slug": "checkout", "name": "Checkout", "description": "Demo team seeded by demo/seed.py"}

# Email, display name, team role. The first user starts the rotation.
USERS = [
    ("dana.lead@example.com", "Dana Lead", "lead"),
    ("eli.member@example.com", "Eli Member", "member"),
    ("fay.member@example.com", "Fay Member", "member"),
]

LEVELS = {"DEBUG": "debug", "INFO": "info", "WARNING": "warn", "ERROR": "error", "CRITICAL": "critical"}

# Disjoint `required` sets, so every generated payload in load.py matches exactly one schema (SPEC §7).
SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "http-request",
        "description": "One request served by a checkout service",
        "json_schema": {
            "$schema": DRAFT,
            "type": "object",
            "required": ["service", "method", "path", "status", "latency_ms"],
            "properties": {
                "service": {"type": "string", "maxLength": 100},
                "method": {"enum": ["GET", "POST", "PUT", "DELETE"]},
                "path": {"type": "string"},
                "status": {"type": "integer", "minimum": 100, "maximum": 599},
                "latency_ms": {"type": "number", "minimum": 0},
                "level": {"type": "string"},
            },
        },
    },
    {
        "name": "job-run",
        "description": "One finished run of a background job",
        "json_schema": {
            "$schema": DRAFT,
            "type": "object",
            "required": ["job", "run_id", "outcome", "duration_s", "attempts"],
            "properties": {
                "job": {"type": "string"},
                "run_id": {"type": "string"},
                "outcome": {"enum": ["succeeded", "failed"]},
                "duration_s": {"type": "number", "minimum": 0},
                "attempts": {"type": "integer", "minimum": 1},
                "error": {"$ref": "#/$defs/error"},
                "level": {"type": "string"},
            },
            "$defs": {
                "error": {
                    "type": "object",
                    "required": ["code"],
                    "properties": {"code": {"type": "string"}, "message": {"type": "string", "maxLength": 500}},
                }
            },
        },
    },
    {
        "name": "host-metric",
        "description": "One metric sample from a host agent",
        "json_schema": {
            "$schema": DRAFT,
            "type": "object",
            "required": ["host", "metric", "value", "unit"],
            "properties": {
                "host": {"type": "string"},
                "metric": {"type": "string"},
                "value": {"type": "number"},
                "unit": {"type": "string"},
                "level": {"type": "string"},
            },
        },
    },
    {
        "name": "payment-event",
        "description": "A payment changing state",
        "json_schema": {
            "$schema": DRAFT,
            "type": "object",
            "required": ["payment_id", "amount", "currency", "state"],
            "properties": {
                "payment_id": {"type": "string"},
                "amount": {"type": "number", "minimum": 0},
                "currency": {"type": "string", "minLength": 3, "maxLength": 3},
                "state": {"enum": ["authorized", "captured", "declined", "refunded"]},
                "tags": {"type": "array", "items": {"type": "string"}, "maxItems": 10},
                "level": {"type": "string"},
            },
        },
    },
]

SEVERITY = {"field": "level", "values": LEVELS, "default": "info"}

SOURCES = [
    {"slug": "checkout-api", "name": "Checkout API", "type": "webhook"},
    {"slug": "billing-jobs", "name": "Billing jobs", "type": "webhook"},
    {"slug": "edge-metrics", "name": "Edge metrics", "type": "websocket"},
    {"slug": "payments-stream", "name": "Payments stream", "type": "websocket"},
    {"slug": "ledger-grpc", "name": "Ledger gRPC", "type": "protobuf"},
]


def rules(team_id: str, schema_ids: dict[str, str]) -> list[dict[str, Any]]:
    """`RuleCreate` bodies over the seeded schemas; load.py generates a share of events that match each one."""
    on_call = [{"type": "on_call", "team_id": team_id}]
    team = [{"type": "team", "team_id": team_id}]
    owner = {"type": "team", "team_id": team_id}
    return [
        {
            "name": "Checkout 5xx",
            "owner": owner,
            "schema_ids": [schema_ids["http-request"]],
            "condition": {
                "op": "and",
                "args": [
                    {"op": "gte", "field": "payload.status", "value": 500},
                    {"op": "glob", "field": "payload.service", "value": "checkout-*"},
                ],
            },
            "dedup": {"fields": ["payload.service", "payload.path"], "window_s": 300},
            "routing": {"recipients": on_call, "channels": None},
            "presentation": {
                "title": "{{ payload.service }} answered {{ payload.status }} on {{ payload.path }}",
                "fields": ["payload.method", "payload.latency_ms"],
                "severity": "error",
                "colour": "red",
            },
        },
        {
            "name": "Slow checkout requests",
            "owner": owner,
            "schema_ids": [schema_ids["http-request"]],
            "condition": {"op": "gt", "field": "payload.latency_ms", "value": 2000},
            "dedup": {"fields": ["payload.service"], "window_s": 600},
            "routing": {"recipients": team, "channels": ["ui"]},
            "presentation": {
                "title": "{{ payload.service }} took {{ payload.latency_ms }} ms",
                "severity": "warn",
                "colour": "yellow",
            },
        },
        {
            "name": "Job failed after retries",
            "owner": owner,
            "schema_ids": [schema_ids["job-run"]],
            "condition": {
                "op": "and",
                "args": [
                    {"op": "eq", "field": "payload.outcome", "value": "failed"},
                    {"op": "gte", "field": "payload.attempts", "value": 3},
                ],
            },
            "dedup": {"fields": ["payload.job"], "window_s": 900},
            "routing": {"recipients": on_call, "channels": None},
            "presentation": {
                "title": "{{ payload.job }} failed after {{ payload.attempts }} attempts",
                "body": "Error {{ payload.error.code }}: {{ payload.error.message }}",
                "severity": "error",
                "colour": "orange",
            },
        },
        {
            "name": "Disk almost full",
            "owner": owner,
            "schema_ids": [schema_ids["host-metric"]],
            "condition": {
                "op": "and",
                "args": [
                    {"op": "eq", "field": "payload.metric", "value": "disk_used_pct"},
                    {"op": "gt", "field": "payload.value", "value": 90},
                ],
            },
            "dedup": {"fields": ["payload.host"], "window_s": 1800},
            "routing": {"recipients": on_call, "channels": None},
            "presentation": {
                "title": "{{ payload.host }} disk at {{ payload.value }}%",
                "severity": "critical",
                "colour": "red",
            },
        },
        {
            "name": "Large payment declined",
            "owner": owner,
            "schema_ids": [schema_ids["payment-event"]],
            "condition": {
                "op": "and",
                "args": [
                    {"op": "eq", "field": "payload.state", "value": "declined"},
                    {"op": "gte", "field": "payload.amount", "value": 10_000},
                    {"op": "not", "arg": {"op": "contains", "field": "payload.tags", "value": "test"}},
                ],
            },
            "dedup": {"fields": ["payload.payment_id"], "window_s": 300},
            "routing": {"recipients": team, "channels": None},
            "presentation": {
                "title": "Payment {{ payload.payment_id }} of {{ payload.amount }} {{ payload.currency }} declined",
                "severity": "warn",
                "colour": "orange",
            },
        },
        {
            "name": "Any critical event",
            "owner": owner,
            "schema_ids": [],
            "condition": {"op": "gte", "field": "severity", "value": "critical"},
            "dedup": {"fields": ["source"], "window_s": 300},
            "routing": {"recipients": on_call, "channels": None},
            "presentation": {"title": "Critical event from {{ source }}", "severity": "critical", "colour": "red"},
        },
    ]


class Api:
    """The management API as the admin; `call` exits on any status outside `ok`."""

    def __init__(self, base_url: str) -> None:
        self.client = httpx.Client(base_url=base_url, timeout=10)

    def call(self, method: str, path: str, ok: tuple[int, ...] = (200, 201), **kwargs: Any) -> httpx.Response:
        response = self.client.request(method, path, **kwargs)
        if response.status_code not in ok:
            sys.exit(f"{method} {path} answered {response.status_code}: {response.text}")
        return response

    def find(self, path: str, key: str, value: object, **params: Any) -> dict[str, Any] | None:
        """The first item of a paginated list whose `key` equals `value`."""
        offset = 0
        while True:
            page = self.call("GET", path, params={**params, "limit": 100, "offset": offset}).json()
            for item in page:
                if item.get(key) == value:
                    return item
            if len(page) < 100:
                return None
            offset += 100


def seed_team(api: Api) -> str:
    team = api.find("/teams", "slug", TEAM["slug"]) or api.call("POST", "/teams", json=TEAM).json()
    print(f"team      {team['slug']} {team['id']}")
    return team["id"]


def seed_users(api: Api, team_id: str) -> None:
    user_ids = []
    for email, name, role in USERS:
        user = (
            api.find("/users", "email", email)
            or api.call("POST", "/users", json={"email": email, "display_name": name}).json()
        )
        api.call("PUT", f"/teams/{team_id}/members/{user['id']}", json={"role": role})
        user_ids.append(user["id"])
        print(f"user      {email} ({role})")
    api.call("PUT", f"/teams/{team_id}/rotation", json={"user_ids": user_ids})
    print(f"rotation  {len(user_ids)} users")


def seed_schemas(api: Api, team_id: str) -> dict[str, str]:
    ids = {}
    for schema in SCHEMAS:
        existing = api.find("/event-schemas", "version", 1, name=schema["name"], team_id=team_id)
        created = (
            existing or api.call("POST", "/event-schemas", json={**schema, "version": 1, "team_id": team_id}).json()
        )
        ids[schema["name"]] = created["id"]
        print(f"schema    {schema['name']} v1 {created['id']}")
    return ids


def seed_sources(api: Api, team_id: str) -> list[dict[str, str]]:
    seeded = []
    for spec in SOURCES:
        source = api.find("/sources", "slug", spec["slug"])
        if source is None:
            response = api.call(
                "POST", "/sources", ok=(201, 422), json={**spec, "team_id": team_id, "severity": SEVERITY}
            )
            if response.status_code == 422:
                reasons = "; ".join(error["msg"] for error in response.json()["detail"])
                print(f"source    {spec['slug']} ({spec['type']}) skipped: {reasons}")
                continue
            source = response.json()
        token = api.call("POST", f"/sources/{source['id']}/token").json()["token"]
        seeded.append(
            {"slug": source["slug"], "type": source["type"], "ingest_url": source["ingest_url"], "token": token}
        )
        print(f"source    {source['slug']} ({source['type']}) {source['ingest_url']}, token rotated")
    return seeded


def seed_rules(api: Api, team_id: str, schema_ids: dict[str, str]) -> None:
    listed = api.call("GET", "/rules", ok=(200, 501), params={"team_id": team_id, "limit": 100})
    existing = {rule["name"] for rule in listed.json()} if listed.status_code == 200 else set()
    for rule in rules(team_id, schema_ids):
        if rule["name"] in existing:
            print(f"rule      {rule['name']} exists")
            continue
        response = api.call("POST", "/rules", ok=(201, 501), json=rule)
        outcome = "created" if response.status_code == 201 else "skipped: POST /rules answers 501"
        print(f"rule      {rule['name']} {outcome}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=os.environ.get("DEMO_BASE_URL", "http://localhost:5173/api"))
    parser.add_argument("--admin", default=os.environ.get("DEMO_ADMIN_EMAIL", "admin@example.com"))
    parser.add_argument("--state", type=Path, default=Path(os.environ.get("DEMO_STATE", "demo-state.json")))
    args = parser.parse_args()

    api = Api(args.base_url)
    api.call("POST", "/auth/login", json={"email": args.admin})
    team_id = seed_team(api)
    seed_users(api, team_id)
    schema_ids = seed_schemas(api, team_id)
    sources = seed_sources(api, team_id)
    # Before the rules, so the rotated tokens are saved even if a later step fails.
    args.state.parent.mkdir(parents=True, exist_ok=True)
    args.state.write_text(json.dumps({"sources": sources}, indent=2))
    print(f"state     {args.state} ({len(sources)} sources)")
    seed_rules(api, team_id, schema_ids)


if __name__ == "__main__":
    main()
