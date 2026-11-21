"""Runbooks (SPEC §11, DOMAIN.md §3).

Permissions follow DOMAIN.md §4: any role in the owning team reads a runbook, `member` or `lead` creates, edits and
deletes it, admins do everything. A runbook the actor cannot see answers 404. Parsing the text into steps is pure and
lives in `parsing`, so `POST /runbooks/parse` previews exactly what create and update save.

Deleting is a soft delete (`deleted_at`): runbook runs keep pointing at the row, and rules that used it are detached
(`runbook_id` set to null) so new alerts no longer start it. Every write is audited (RUN-5).
"""

import uuid

from pydantic import JsonValue, TypeAdapter
from sqlalchemy import exists, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from pagercutie.audit import service as audit
from pagercutie.audit.schemas import AuditAction
from pagercutie.auth.service import CurrentUser
from pagercutie.core.db import NotifyChannel, notify
from pagercutie.core.errors import Conflict, Forbidden, NotFound
from pagercutie.core.schemas import Pagination
from pagercutie.rules.ast import Condition
from pagercutie.rules.models import Rule
from pagercutie.runbooks.models import Runbook
from pagercutie.runbooks.parsing import ParsedRunbook, parse_runbook
from pagercutie.runbooks.schemas import (
    RunbookCreate,
    RunbookFormat,
    RunbookParseRequest,
    RunbookParseResult,
    RunbookRead,
    RunbookUpdate,
)
from pagercutie.teams.models import Team

_RUNBOOK = "Runbook"
_TEAM = "Team"
_ACTIVE = Runbook.deleted_at.is_(None)
_ATTACH = TypeAdapter[Condition | None](Condition | None)


# --- Use cases (called by router.py) ---------------------------------------------------------------------------


async def list_runbooks(
    session: AsyncSession, actor: CurrentUser, pagination: Pagination, team_id: uuid.UUID | None
) -> list[RunbookRead]:
    """Admins see every runbook, other users the runbooks of the teams they belong to."""
    statement = select(Runbook).where(_ACTIVE).order_by(Runbook.id).limit(pagination.limit).offset(pagination.offset)
    if not actor.is_admin:
        statement = statement.where(Runbook.team_id.in_(actor.team_roles))
    if team_id is not None:
        statement = statement.where(Runbook.team_id == team_id)
    return [RunbookRead.model_validate(runbook) for runbook in await session.scalars(statement)]


async def create_runbook(session: AsyncSession, actor: CurrentUser, data: RunbookCreate) -> RunbookRead:
    """`member` or `lead` of `team_id`, or an admin. An explicit `attach` overrides a structured `matches:`."""
    _require_editor(actor, data.team_id)
    if not await session.scalar(select(exists().where(Team.id == data.team_id))):
        raise NotFound(_TEAM, data.team_id)
    # The request's slug wins over a structured runbook's `runbook:` name, so the editor may rename it (ADR-0069).
    parsed = parse_runbook(data.format, data.original)
    runbook = await session.scalar(
        insert(Runbook)
        .values(
            slug=data.slug,
            title=data.title,
            team_id=data.team_id,
            format=data.format,
            original=data.original,
            attach=data.attach if data.attach is not None else parsed.attach,
            steps=parsed.steps,
        )
        .on_conflict_do_nothing(index_elements=[Runbook.slug], index_where=_ACTIVE)
        .returning(Runbook)
    )
    if runbook is None:
        raise Conflict(f"A runbook with slug {data.slug} already exists")
    created = {"after": _audited(runbook.title, runbook.format, runbook.original, runbook.attach)}
    audit.record(session, actor.id, AuditAction.RUNBOOK_CREATED, runbook.id, runbook.team_id, created)
    return RunbookRead.model_validate(runbook)


def parse_runbook_preview(data: RunbookParseRequest) -> RunbookParseResult:
    """Any logged-in user; saves nothing."""
    parsed = parse_runbook(data.format, data.original)
    return RunbookParseResult(attach=parsed.attach, steps=parsed.steps, warnings=parsed.warnings)


async def get_runbook(session: AsyncSession, actor: CurrentUser, runbook_id: uuid.UUID) -> RunbookRead:
    """Any role in the owning team, or an admin."""
    return RunbookRead.model_validate(await _load_visible(session, actor, runbook_id))


async def update_runbook(
    session: AsyncSession, actor: CurrentUser, runbook_id: uuid.UUID, data: RunbookUpdate
) -> RunbookRead:
    """`member` or `lead` of the owning team, or an admin.

    A new `format` or `original` re-parses the steps; runs already started keep the steps they copied (SPEC §11.3).
    `attach` is the request's when given, else a re-parsed structured runbook's `matches:`, else unchanged.
    """
    runbook = await _load_editable(session, actor, runbook_id)
    format = data.format if data.format is not None else runbook.format
    original = data.original if data.original is not None else runbook.original
    parsed: ParsedRunbook | None = None
    if format != runbook.format or original != runbook.original:
        parsed = parse_runbook(format, original)
    attach = runbook.attach
    if data.attach is not None:
        attach = data.attach
    elif parsed is not None and parsed.attach is not None:
        attach = parsed.attach
    title = data.title if data.title is not None else runbook.title

    before = _audited(runbook.title, runbook.format, runbook.original, runbook.attach)
    after = _audited(title, format, original, attach)
    changed = [name for name in after if after[name] != before[name]]
    if not changed:
        return RunbookRead.model_validate(runbook)
    values: dict[str, object] = {"title": title, "format": format, "original": original, "attach": attach}
    if parsed is not None:
        values["steps"] = parsed.steps
    updated = await session.scalar(
        update(Runbook).where(Runbook.id == runbook_id, _ACTIVE).values(**values).returning(Runbook)
    )
    if updated is None:
        raise NotFound(_RUNBOOK, runbook_id)
    diff = audit.changes(before, after)
    audit.record(session, actor.id, AuditAction.RUNBOOK_UPDATED, runbook_id, updated.team_id, diff)
    return RunbookRead.model_validate(updated)


async def delete_runbook(session: AsyncSession, actor: CurrentUser, runbook_id: uuid.UUID) -> None:
    """`member` or `lead` of the owning team, or an admin. Soft delete; detaches the rules that used the runbook."""
    runbook = await _load_editable(session, actor, runbook_id)
    deleted = await session.scalar(
        update(Runbook).where(Runbook.id == runbook_id, _ACTIVE).values(deleted_at=func.now()).returning(Runbook.id)
    )
    if deleted is None:
        raise NotFound(_RUNBOOK, runbook_id)
    detached = list(
        await session.scalars(
            update(Rule).where(Rule.runbook_id == runbook_id).values(runbook_id=None).returning(Rule.id)
        )
    )
    if detached:
        await notify(session, NotifyChannel.RULES_CHANGED)
    deleted: dict[str, JsonValue] = {
        "slug": runbook.slug,
        "title": runbook.title,
        "detached_rule_ids": [str(rule) for rule in sorted(detached)],
    }
    audit.record(session, actor.id, AuditAction.RUNBOOK_DELETED, runbook_id, runbook.team_id, deleted)


# --- Rules -----------------------------------------------------------------------------------------------------


def _require_editor(actor: CurrentUser, team_id: uuid.UUID) -> None:
    # Checked before any DB access so non-members can't probe which team IDs exist.
    if not actor.can_edit_team(team_id):
        raise Forbidden("Only members and leads of the owning team, or an admin, can change its runbooks")


async def _load_visible(session: AsyncSession, actor: CurrentUser, runbook_id: uuid.UUID) -> Runbook:
    runbook = await session.scalar(select(Runbook).where(Runbook.id == runbook_id, _ACTIVE))
    if runbook is None or not actor.can_see_team(runbook.team_id):
        raise NotFound(_RUNBOOK, runbook_id)
    return runbook


async def _load_editable(session: AsyncSession, actor: CurrentUser, runbook_id: uuid.UUID) -> Runbook:
    """404 for a runbook the actor cannot see, 403 for one they can see but not change (a viewer)."""
    runbook = await _load_visible(session, actor, runbook_id)
    _require_editor(actor, runbook.team_id)
    return runbook


def _audited(title: str, format: RunbookFormat, original: str, attach: Condition | None) -> dict[str, JsonValue]:
    """The audited fields as JSON. Steps are left out: they follow from `format` and `original`."""
    return {
        "title": title,
        "format": format.value,
        "original": original,
        "attach": _ATTACH.dump_python(attach, mode="json"),
    }
