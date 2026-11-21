# ADR-0091: The rule set is loaded per replica and dropped with the source catalog

- **ID:** ADR-0091
- **Timestamp:** 2026-11-21T08:05+01:00
- **Status:** Accepted, amends ADR-0061 (rule set no longer `501`) and ADR-0063 (`on_lost` drops both caches)
- **See:** SPEC §5.2, §5.3, §8, `backend/src/pagercutie/pipeline/adapters.py`

## Decision

- `rule_set_reloader(state)` loads `evaluation.load_rule_set` in a session of its own and swaps `IngestState.rule_set`
  in one assignment. The listener runs it on every (re)connect and on `NOTIFY rules_changed` and `access_changed`;
  both channels map to one reloader object, so a reconnect reloads the rules once.
- Until the first load, `current_rule_set` raises `NotReady`: the webhook answers `503`, a WebSocket handshake is
  denied with `503`, and an open WebSocket closes with `1013` on its next frame, as for the catalog.
- `IngestState.drop_catalog` becomes `drop_caches`: a lost listening connection drops the catalog and the rule set.

Considered and rejected:

| Option | Why not |
|---|---|
| Keep the last rule set when the connection is lost | A disabled rule or a changed recipient keeps alerting on a cut-off replica, the same failure ADR-0063 rules out for tokens. |
| Load the rules once in the lifespan as well | The listener already runs every reloader on connect; a second load path could race it. |

## Rationale

- `RUL-5`: rule edits take effect on every replica without a restart.
- One fail-closed rule for both per-replica caches; a producer retries a `503`.
