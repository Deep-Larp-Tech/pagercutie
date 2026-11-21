# ADR-0038: Models as dataclasses

- **ID:** ADR-0038
- **Timestamp:** 2026-11-21T01:09+01:00
- **Status:** Accepted
- **Decided by:** TechPriest
- **See:** SPEC §12.2, ADR-0030, ADR-0031

## Decision

- SQLAlchemy models subclass `MappedAsDataclass`, so each model gets a generated, statically typed `__init__`.
  Constructor mistakes become type errors instead of runtime errors. No model has a hand-written `__init__`.
- `core/models.py` defines a private `_Dataclass(MappedAsDataclass, kw_only=True, eq=False, repr=False)`. `Base`
  and every mixin subclass it. SQLAlchemy reads the dataclass options from the first dataclass in the MRO, so a
  mixin without them would silently bring back `eq=True` and unhashable models. Any mixin with mapped columns
  lives in core and subclasses `_Dataclass`.
- `eq=False` keeps identity equality and hashing, which the session's identity map, sets and dict keys rely on.
- `repr=False` keeps `object.__repr__`. The generated repr reads every field and raised `InvalidRequestError` or
  `MissingGreenlet` under asyncio on loaded or expired instances with `lazy="raise"` relationships.
- Every model repeats `kw_only=True` in its class line (`class User(IdMixin, CreatedAtMixin, Base, kw_only=True)`),
  because ty applies `kw_only` only to the class that declares it. A custom metaclass on SQLAlchemy's private
  `DCTransformDeclarative` would avoid the repetition but depends on undocumented API, so we rejected it.
- Constructor rules per column:
  - Columns the database or a default fills (`id`, `created_at`, `updated_at`, other server defaults) are
    `init=False`.
  - `id` keeps uuid7 through `insert_default=uuid.uuid7` and is still assigned at flush. `default=` together with
    `init=False` is deprecated.
  - Nullable columns get `default=None`, so the argument is optional.
  - Nullable columns where a forgotten value would silently write wrong data stay required:
    `AuditEntry.actor_user_id` (null = system), `Alert.team_id` (null = personal alert), `Rule.team_id` and
    `Rule.user_id` (exactly one owner).
  - Mutable or callable defaults use `default_factory`: `default_factory=list` for relationship collections,
    `default_factory=ChannelPreferences` for `channel_preferences`.
  - Foreign keys filled through a parent's relationship collection (`StepRun.run_id`, `RotationMember.team_id`)
    are `init=False`.
  - Columns with no default today stay required. No new convenience defaults.
- Call sites pass explicit keyword arguments, never `**model_dump()`, because `dict[str, Any]` defeats the check.
- The schema does not change: the DDL is identical and no migration is needed.

## Rationale

- A wrong constructor call (missing, unknown or mistyped argument) fails `ty` before it reaches the database.
- The options in `_Dataclass` keep the identity semantics and the plain repr the session and async code already
  depend on.

## Consequences

- ty catches missing, unknown and wrong-type arguments, values for `init=False` fields and positional calls. It
  does not check `default=` values against the column type, it treats models as unhashable although they are
  hashable at runtime, and it accepts SQL expressions as constructor values.
- No checker catches a new model that forgets `kw_only=True`.
- `channel_preferences` with `default_factory` has no Core column default, so a raw `insert()` that leaves the
  column out fails NOT NULL. No such insert exists today; a later review of channel preferences covers it.
- `dataclasses.asdict()` and `replace()` work on models, and `asdict` walks relationships.
- All models switch at once: with only core converted, the existing model calls fail.
