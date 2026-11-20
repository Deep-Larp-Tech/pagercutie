import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from factories import a_person, a_skill
from pagercutie.core.errors import InvalidInput
from pagercutie.core.schemas import Pagination
from pagercutie.events import service as events_service
from pagercutie.events.schemas import LarpEventQuery
from pagercutie.imports import service
from pagercutie.imports.schemas import ImportFormat, ImportPhase, ImportProgress, ImportSummaryRead
from pagercutie.imports.service import import_events
from pagercutie.persons import service as persons_service
from pagercutie.persons.elo import DEFAULT_ELO, elo_delta

pytestmark = pytest.mark.anyio

HEADER = "first_name,last_name,skill_name,skill_difficulty,occurred_at,believability,description,location"


def csv_file(*rows: str) -> bytes:
    return "\n".join([HEADER, *rows]).encode()


async def run_import(session: AsyncSession, content: bytes) -> tuple[list[ImportProgress], ImportSummaryRead]:
    progress: list[ImportProgress] = []
    summaries: list[ImportSummaryRead] = []
    async for item in import_events(session, content, ImportFormat.CSV):
        assert not summaries, "summary must be the last item"
        if isinstance(item, ImportProgress):
            progress.append(item)
        else:
            summaries.append(item)
    assert len(summaries) == 1
    return progress, summaries[0]


async def test_import_creates_missing_persons_and_skills_and_reuses_existing(session: AsyncSession) -> None:
    await a_person(session, first_name="Stas", last_name="Yurich")
    content = csv_file(
        "Stas,Yurich,Vim,7,2026-01-01T09:00:00Z,9,Exited Vim,",
        "Ada,Pupil,Vim,7,2026-01-02T09:00:00Z,3,Typed :q!,Lab",
        "Ada,Pupil,Feigning,2,2026-01-03T09:00:00Z,8,Nodded wisely,",
    )

    _, summary = await run_import(session, content)

    assert summary == ImportSummaryRead(persons_created=1, skills_created=2, events_created=3)
    assert {p.first_name for p in await persons_service.list_persons(session, Pagination())} == {"Stas", "Ada"}


async def test_progress_reports_each_phase_and_every_batch(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(service, "BATCH_SIZE", 2)
    content = csv_file(*(f"Ada,Pupil,Vim,7,2026-01-0{day}T09:00:00Z,5,Event {day}," for day in range(1, 6)))

    progress, _ = await run_import(session, content)

    assert [(p.phase, p.processed, p.total) for p in progress] == [
        (ImportPhase.PARSING, 0, None),
        (ImportPhase.VALIDATING, 0, 5),
        (ImportPhase.WRITING, 0, 5),
        (ImportPhase.WRITING, 2, 5),
        (ImportPhase.WRITING, 4, 5),
        (ImportPhase.WRITING, 5, 5),
    ]


async def test_empty_file_completes_with_nothing_created(session: AsyncSession) -> None:
    progress, summary = await run_import(session, csv_file())

    assert progress[-1] == ImportProgress(phase=ImportPhase.WRITING, processed=0, total=0)
    assert summary == ImportSummaryRead(persons_created=0, skills_created=0, events_created=0)


async def test_elo_is_applied_in_chronological_order(session: AsyncSession) -> None:
    content = csv_file(
        "Ada,Pupil,Vim,7,2026-01-02T09:00:00Z,1,Second,",  # file order != time order
        "Ada,Pupil,Vim,7,2026-01-01T09:00:00Z,10,First,",
    )

    await run_import(session, content)

    first = elo_delta(DEFAULT_ELO, 7, 10)
    second = elo_delta(DEFAULT_ELO + first, 7, 1)
    events = await events_service.list_events(session, LarpEventQuery())  # newest first
    assert [e.elo_delta for e in events] == [second, first]


async def test_conflicting_skill_difficulty_rejects_the_whole_file_before_writing(session: AsyncSession) -> None:
    await a_skill(session, name="Vim", difficulty=7)
    content = csv_file(
        "Ada,Pupil,Feigning,2,2026-01-01T09:00:00Z,8,Fine row,",
        "Ada,Pupil,Vim,3,2026-01-02T09:00:00Z,8,Vim is not that easy,",
    )
    phases = []

    with pytest.raises(InvalidInput) as raised:
        async for item in import_events(session, content, ImportFormat.CSV):
            phases.append(item.phase if isinstance(item, ImportProgress) else None)

    assert phases == [ImportPhase.PARSING, ImportPhase.VALIDATING]
    assert [e.loc for e in raised.value.errors] == [("rows", 1, "skill_difficulty")]
    assert await persons_service.list_persons(session, Pagination()) == []


async def test_existing_persons_and_skills_are_found_across_lookup_chunks(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(service, "LOOKUP_CHUNK", 1)
    await a_person(session, first_name="Stas", last_name="Yurich")
    await a_person(session, first_name="Ada", last_name="Pupil")
    await a_skill(session, name="Vim", difficulty=7)
    content = csv_file(
        "Stas,Yurich,Vim,7,2026-01-01T09:00:00Z,9,Exited Vim,",
        "Ada,Pupil,Feigning,2,2026-01-02T09:00:00Z,8,Nodded wisely,",
        "Ann,Other,Vim,7,2026-01-03T09:00:00Z,5,Opened Vim,",
    )

    _, summary = await run_import(session, content)

    assert summary == ImportSummaryRead(persons_created=1, skills_created=1, events_created=3)
