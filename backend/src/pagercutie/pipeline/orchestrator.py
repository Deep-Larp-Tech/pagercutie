"""Runs one ingested event through every stage and commits the result before ingest answers (SPEC §5.1).

The only module that imports the stages; they never import each other (import-linter contracts in pyproject.toml).
"""

from typing import assert_never

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pagercutie.pipeline.dedup import stage as dedup
from pagercutie.pipeline.evaluation import stage as evaluation
from pagercutie.pipeline.executor import stage as executor
from pagercutie.pipeline.ingest import stage as ingest
from pagercutie.pipeline.messages import DedupOutcome, IngestResult, Match, Opened, RawEvent, Renotified, Repeated
from pagercutie.pipeline.routing import stage as routing


async def process_event(
    raw: RawEvent,
    sessionmaker: async_sessionmaker[AsyncSession],
    catalog: ingest.SourceCatalog,
    rules: evaluation.RuleSet,
    windows: dedup.WindowStore,
) -> IngestResult:
    """Normalise, evaluate, deduplicate and route `raw`; returns once every outcome is committed.

    Raises what `ingest.normalise` raises for input it rejects. Any other failure releases the dedup windows this
    event claimed and propagates, and nothing is committed.
    """
    event = await ingest.normalise(raw, catalog, ingest.schema_loader(sessionmaker))
    matches = evaluation.evaluate(event, rules)
    claims = [(match, await dedup.claim(match, windows)) for match in matches]
    try:
        outcomes = await _deduplicate(sessionmaker, claims, windows)
    except BaseException:
        for _, claim in claims:
            await dedup.release(claim, windows)
        raise
    for claim, outcome in outcomes:
        await dedup.confirm(claim, outcome, windows)
    return IngestResult(event_id=event.event_id, matches=len(matches))


async def _deduplicate(
    sessionmaker: async_sessionmaker[AsyncSession],
    claims: list[tuple[Match, dedup.Claim]],
    windows: dedup.WindowStore,
) -> list[tuple[dedup.Claim, DedupOutcome]]:
    """Counts held windows in Redis, and records every other match in one transaction."""
    outcomes: list[tuple[dedup.Claim, DedupOutcome]] = []
    to_record: list[tuple[Match, dedup.Recordable]] = []
    for match, claim in claims:
        match claim:
            case dedup.Held():
                outcomes.append((claim, await dedup.repeat(match, claim, windows)))
            case dedup.Won() | dedup.Pending() | dedup.Unavailable():
                to_record.append((match, claim))
            case _:
                assert_never(claim)
    if to_record:
        async with sessionmaker() as session, session.begin():
            for match, claim in to_record:
                outcomes.append((claim, await _record(session, match, claim)))
    return outcomes


async def _record(session: AsyncSession, match: Match, claim: dedup.Recordable) -> DedupOutcome:
    """Upserts the alert, then routes it and starts its runbook run as the outcome requires."""
    outcome = await dedup.record(session, match, claim)
    match outcome:
        case Opened():
            await routing.route(session, outcome)
            await executor.start_run(session, outcome)
        case Renotified():
            await routing.route(session, outcome)
        case Repeated():
            pass
        case _:
            assert_never(outcome)
    return outcome
