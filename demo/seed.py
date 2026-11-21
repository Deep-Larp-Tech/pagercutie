"""Seeds the demo: two teams with members and rotations, event schemas, sources of every type, runbooks in every
format and alert rules.

Idempotent: existing teams, users, schemas, sources, runbooks and rules are reused by slug, email or name. Every run
rotates the source tokens and writes them to the state file that `load.py` reads. Routes that still answer 501 are
reported, not fatal.
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import httpx

DRAFT = "https://json-schema.org/draft/2020-12/schema"

# `checkout` owns everything below; `platform` is the target of the `job-retry` runbook's escalate step.
TEAMS = [
    {"slug": "checkout", "name": "Checkout", "description": "Demo team seeded by demo/seed.py"},
    {"slug": "platform", "name": "Platform", "description": "Demo escalation team seeded by demo/seed.py"},
]

# Team slug to (email, display name, team role); the first user of each team starts its rotation.
USERS = {
    "checkout": [
        ("dana.lead@example.com", "Dana Lead", "lead"),
        ("eli.member@example.com", "Eli Member", "member"),
        ("fay.member@example.com", "Fay Member", "member"),
    ],
    "platform": [
        ("gus.lead@example.com", "Gus Lead", "lead"),
        ("hana.member@example.com", "Hana Member", "member"),
    ],
}

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


RUNBOOK_DIR = Path(__file__).parent / "runbooks"

# File extension to runbook format (SPEC §11.1).
FORMATS = {".yaml": "structured", ".md": "markdown", ".link": "link", ".txt": "text"}

# File in RUNBOOK_DIR to title; the file name without extension is the slug.
RUNBOOKS = {
    "job-retry.yaml": "Retry a failed job, then escalate",
    "disk-full.yaml": "Free disk space on a host",
    "checkout-5xx.md": "Checkout answers 5xx",
    "payment-declined.md": "Large payment declined",
    "slow-requests.link": "Slow checkout requests",
    "critical-event.txt": "Critical event triage",
}

# Rule name to the slug of the runbook it links. "Job failed after retries" links none: `job-retry` attaches to it
# through its `matches:` block (ADR-0089).
RULE_RUNBOOKS = {
    "Checkout 5xx": "checkout-5xx",
    "Slow checkout requests": "slow-requests",
    "Disk almost full": "disk-full",
    "Large payment declined": "payment-declined",
    "Any critical event": "critical-event",
}


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


def seed_teams(api: Api) -> dict[str, str]:
    ids = {}
    for spec in TEAMS:
        team = api.find("/teams", "slug", spec["slug"]) or api.call("POST", "/teams", json=spec).json()
        ids[team["slug"]] = team["id"]
        print(f"team      {team['slug']} {team['id']}")
    return ids


def seed_users(api: Api, team_id: str, users: list[tuple[str, str, str]]) -> None:
    user_ids = []
    for email, name, role in users:
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


def seed_runbooks(api: Api, team_id: str) -> dict[str, str]:
    ids = {}
    for file, title in RUNBOOKS.items():
        path = RUNBOOK_DIR / file
        runbook = (
            api.find("/runbooks", "slug", path.stem, team_id=team_id)
            or api.call(
                "POST",
                "/runbooks",
                json={
                    "slug": path.stem,
                    "title": title,
                    "team_id": team_id,
                    "format": FORMATS[path.suffix],
                    "original": path.read_text(),
                },
            ).json()
        )
        ids[runbook["slug"]] = runbook["id"]
        print(f"runbook   {runbook['slug']} ({runbook['format']}, {len(runbook['steps'])} steps)")
    return ids


def seed_rules(api: Api, team_id: str, schema_ids: dict[str, str], runbook_ids: dict[str, str]) -> None:
    listed = api.call("GET", "/rules", ok=(200, 501), params={"team_id": team_id, "limit": 100})
    existing = {rule["name"]: rule for rule in listed.json()} if listed.status_code == 200 else {}
    for rule in rules(team_id, schema_ids):
        slug = RULE_RUNBOOKS.get(rule["name"])
        runbook_id = runbook_ids[slug] if slug else None
        if (current := existing.get(rule["name"])) is not None:
            if current["runbook_id"] != runbook_id:
                api.call("PATCH", f"/rules/{current['id']}", json={"runbook_id": runbook_id})
                print(f"rule      {rule['name']} exists, runbook linked: {slug}")
            else:
                print(f"rule      {rule['name']} exists")
            continue
        response = api.call("POST", "/rules", ok=(201, 501), json={**rule, "runbook_id": runbook_id})
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
    team_ids = seed_teams(api)
    for team_slug, users in USERS.items():
        seed_users(api, team_ids[team_slug], users)
    team_id = team_ids["checkout"]
    schema_ids = seed_schemas(api, team_id)
    sources = seed_sources(api, team_id)
    # Before the rules, so the rotated tokens are saved even if a later step fails.
    args.state.parent.mkdir(parents=True, exist_ok=True)
    args.state.write_text(json.dumps({"sources": sources}, indent=2))
    print(f"state     {args.state} ({len(sources)} sources)")
    runbook_ids = seed_runbooks(api, team_id)
    seed_rules(api, team_id, schema_ids, runbook_ids)


if __name__ == "__main__":
    main()
