# ADR-0030: Hand-written ORM models with DTO value objects as typed jsonb

- **ID:** ADR-0030
- **Timestamp:** 2026-11-20T22:10+01:00
- **Status:** Accepted
- **See:** SPEC §12.2, DOMAIN.md

## Decision

We write SQLAlchemy models by hand in `<module>/models.py` and autogenerate migrations from them
(`mise run migration`). Value objects keep their DTO type: `PydanticJSONB(TypeAdapter(T))` in `core/models.py`
stores a `Condition`, `Routing`, `list[Step]`, `ChannelPreferences` or similar in a `jsonb` column and validates it on
load, so `Mapped[Condition]` is the type the API exposes. `migrations/env.py` renders these columns as plain `JSONB`,
so migrations never import application types. `tests/integration/test_migrations.py` runs `alembic check` and fails
when a model changes without a migration.

Considered and rejected:

| Option | Why not |
|---|---|
| Generate models from the DTOs / OpenAPI | No maintained generator. DTOs lack foreign keys, delete rules, indexes and the columns the API never shows (token hashes, `retry_at`, sessions), and their shape differs from the tables (`Owner` union → two columns + check). |
| SQLModel (one class for table and DTO) | Breaks the router → service → models split and the `banned-api` rule; weak with discriminated unions and jsonb. |
| Database first (DDL, then `sqlacodegen`) | Reverses the existing Alembic workflow; loses typed jsonb, `uuid7` defaults and `lazy="raise"`; regenerating overwrites edits. |

## Rationale

- Each value object has one definition, so the database holds what the contract validates.
- Alembic generates migrations from models, the direction its autogenerate supports.
- `ty` checks every column type; no column is typed `Any`.
