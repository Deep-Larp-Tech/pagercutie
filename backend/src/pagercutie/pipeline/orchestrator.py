"""Runs one ingested event through the in-request stages and commits the result before ingest answers (SPEC §5.1).

The only module that chains the stages; they never import each other (import-linter contracts in pyproject.toml).
Adapters also call `ingest.authenticate`, and `pipeline.state` reloads the stages' caches (SPEC §5.5).
"""

from typing import assert_never

import structlog
from opentelemetry import metrics, trace
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pagercutie.pipeline.dedup import stage as dedup
from pagercutie.pipeline.evaluation import stage as evaluation
from pagercutie.pipeline.executor import stage as executor
from pagercutie.pipeline.ingest import stage as ingest
from pagercutie.pipeline.messages import DedupOutcome, IngestResult, Match, Opened, RawEvent, Renotified, Repeated
from pagercutie.pipeline.routing import stage as routing

log = structlog.get_logger("pipeline")

_tracer = trace.get_tracer("pagercutie.pipeline")
_failed = metrics.get_meter("pagercutie.pipeline").create_counter(
    "matches_failed_total",
    description="Matches whose record, route or runbook start raised and was rolled back to its savepoint (ADR-0100)",
)


async def process_event(
    raw: RawEvent,
    sessionmaker: async_sessionmaker[AsyncSession],
    load_schemas: ingest.SchemaLoader,
    rules: evaluation.RuleSet,
    windows: dedup.WindowStore,
) -> IngestResult:
    """Normalise, evaluate, deduplicate and route `raw`; returns once every outcome is committed.

    Raises what `ingest.normalise` raises for input it rejects. A match whose record, route or runbook start raises
    is rolled back to its savepoint, logged and counted, and the other matches still commit. Any other failure, and
    a cancellation, releases the dedup windows this event claimed and propagates, and nothing is committed.
    """
    with _tracer.start_as_current_span("ingest.normalise"):
        event = await ingest.normalise(raw, load_schemas)
    with structlog.contextvars.bound_contextvars(event_id=str(event.event_id)):
        with _tracer.start_as_current_span("evaluation.evaluate", attributes={"event_id": str(event.event_id)}):
            matches = evaluation.evaluate(event, rules)
        outcomes, failed = await _deduplicate(sessionmaker, matches, windows) if matches else ([], [])
        log.info(
            "pipeline.event_processed",
            message="Event processed",
            source=event.source,
            schema=event.schema_name,
            rule_ids=[str(match.rule.id) for match in matches],
            outcomes=[_describe(outcome) for outcome in outcomes],
            failed_rule_ids=[str(match.rule.id) for match in failed],
        )
    return IngestResult(event_id=event.event_id, matches=len(matches))


async def _deduplicate(
    sessionmaker: async_sessionmaker[AsyncSession], matches: list[Match], windows: dedup.WindowStore
) -> tuple[list[DedupOutcome], list[Match]]:
    """Claims every window, records the matches that need Postgres in one transaction with a savepoint each, and
    settles the windows after the commit. Returns the committed outcomes and the matches that failed."""
    failed: list[Match] = []
    with _tracer.start_as_current_span("dedup.deduplicate", attributes={"matches": len(matches)}):
        async with dedup.deduplicate(matches, windows) as scope:
            if scope.to_record:
                async with sessionmaker() as session, session.begin():
                    for item in scope.to_record:
                        try:
                            async with session.begin_nested():
                                await _record(session, scope, item)
                        except Exception:
                            # Only this match rolls back; a BaseException (cancellation) aborts the whole event.
                            scope.discard(item)
                            failed.append(item.match)
                            _failed.add(1)
                            log.exception("pipeline.match_failed", rule_id=str(item.match.rule.id))
    return scope.outcomes(), failed


async def _record(session: AsyncSession, scope: dedup.Deduplication, item: dedup.ToRecord) -> None:
    """Upserts the alert, then routes it and starts its runbook run as the outcome requires."""
    with _tracer.start_as_current_span("dedup.record", attributes={"rule_id": str(item.match.rule.id)}):
        outcome = await scope.record(session, item)
    match outcome:
        case Opened():
            with _tracer.start_as_current_span("routing.route", attributes={"alert_id": str(outcome.alert_id)}):
                await routing.route(session, outcome)
            with _tracer.start_as_current_span("executor.start_run", attributes={"alert_id": str(outcome.alert_id)}):
                await executor.start_run(session, outcome)
        case Renotified():
            with _tracer.start_as_current_span("routing.route", attributes={"alert_id": str(outcome.alert_id)}):
                await routing.route(session, outcome)
        case Repeated():
            pass
        case _:
            assert_never(outcome)


def _describe(outcome: DedupOutcome) -> dict[str, str]:
    """One outcome for the event's log line."""
    match outcome:
        case Opened():
            kind = "opened"
        case Renotified():
            kind = "renotified"
        case Repeated():
            kind = "repeated"
        case _:
            assert_never(outcome)
    return {"rule_id": str(outcome.match.rule.id), "alert_id": str(outcome.alert_id), "outcome": kind}
