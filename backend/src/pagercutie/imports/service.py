import asyncio
from collections.abc import AsyncIterator
from itertools import batched

from sqlalchemy import select, tuple_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from pagercutie.core.errors import Conflict, FieldError, InvalidInput
from pagercutie.events.service import is_in_future, record_event
from pagercutie.imports.parsing import parse_rows
from pagercutie.imports.schemas import ImportFormat, ImportPhase, ImportProgress, ImportSummaryRead, LarpEventImportRow
from pagercutie.persons.elo import DEFAULT_ELO
from pagercutie.persons.models import Person
from pagercutie.skills.models import Skill

# Rows written per flush; each flush is reported as one progress step.
BATCH_SIZE = 500
# Existing persons and skills are looked up this many keys per query.
LOOKUP_CHUNK = 1000


async def import_events(
    session: AsyncSession, content: bytes, fmt: ImportFormat
) -> AsyncIterator[ImportProgress | ImportSummaryRead]:
    """Yield progress, then the summary as the last item. Only flushes: the caller commits, or rolls back to drop
    everything (any invalid row rejects the whole file). Elo is applied in chronological order."""
    yield ImportProgress(phase=ImportPhase.PARSING)
    rows = await asyncio.to_thread(parse_rows, content, fmt)
    total = len(rows)
    yield ImportProgress(phase=ImportPhase.VALIDATING, total=total)

    person_keys = {(r.first_name, r.last_name) for r in rows}
    skill_names = {r.skill_name for r in rows}
    persons: dict[tuple[str, str], Person] = {}
    skills: dict[str, Skill] = {}
    # Chunked: one IN with tens of thousands of row values exceeds Postgres' stack depth limit.
    for keys in batched(person_keys, LOOKUP_CHUNK, strict=False):
        found_persons = await session.scalars(
            select(Person).where(tuple_(Person.first_name, Person.last_name).in_(keys)).with_for_update()
        )
        persons.update(((p.first_name, p.last_name), p) for p in found_persons)
    for names in batched(skill_names, LOOKUP_CHUNK, strict=False):
        skills.update((s.name, s) for s in await session.scalars(select(Skill).where(Skill.name.in_(names))))

    _validate(rows, skills)
    yield ImportProgress(phase=ImportPhase.WRITING, total=total)

    persons_created = skills_created = 0
    for index, row in enumerate(sorted(rows, key=lambda r: r.occurred_at), start=1):
        person = persons.get((row.first_name, row.last_name))
        if person is None:
            # Explicit Elo: the column default is applied only at INSERT, but record_event needs it now.
            person = Person(first_name=row.first_name, last_name=row.last_name, larp_elo=DEFAULT_ELO)
            persons[(row.first_name, row.last_name)] = person
            session.add(person)
            persons_created += 1
        skill = skills.get(row.skill_name)
        if skill is None:
            skill = skills[row.skill_name] = Skill(name=row.skill_name, difficulty=row.skill_difficulty)
            session.add(skill)
            skills_created += 1
        record_event(
            session,
            person,
            skill,
            occurred_at=row.occurred_at,
            believability=row.believability,
            description=row.description,
            location=row.location,
        )
        if index % BATCH_SIZE == 0 or index == total:
            await _flush(session)
            yield ImportProgress(phase=ImportPhase.WRITING, processed=index, total=total)

    yield ImportSummaryRead(persons_created=persons_created, skills_created=skills_created, events_created=total)


async def _flush(session: AsyncSession) -> None:
    try:
        async with session.begin_nested():
            await session.flush()
    except IntegrityError as e:
        raise Conflict("A concurrent change created the same person or skill, retry the import") from e


def _validate(rows: list[LarpEventImportRow], existing_skills: dict[str, Skill]) -> None:
    errors: list[FieldError] = []
    difficulties = {name: skill.difficulty for name, skill in existing_skills.items()}
    for index, row in enumerate(rows):
        if is_in_future(row.occurred_at):
            errors.append(FieldError(("rows", index, "occurred_at"), "must not be in the future"))
        known = difficulties.setdefault(row.skill_name, row.skill_difficulty)
        if known != row.skill_difficulty:
            errors.append(
                FieldError(("rows", index, "skill_difficulty"), f"skill {row.skill_name!r} has difficulty {known}")
            )
    if errors:
        raise InvalidInput(errors)
