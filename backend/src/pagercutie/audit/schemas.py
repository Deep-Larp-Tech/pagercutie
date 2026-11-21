import uuid
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Self, assert_never

from pydantic import BaseModel, BeforeValidator, Field, model_validator

from pagercutie.core.schemas import ReadModel, UtcDatetime


class AuditEntityType(StrEnum):
    """Kind of entity an audit entry names; `entity_id` is the id of a row of that kind."""

    USER = "user"
    TEAM = "team"
    SOURCE = "source"
    EVENT_SCHEMA = "event_schema"
    RULE = "rule"
    RUNBOOK = "runbook"
    ALERT = "alert"


class AuditAction(StrEnum):
    """What an audit entry records, `<entity>.<verb>`; `step.*` and `runbook_run.*` entries name the alert of the run.

    Includes the actions SPEC §11 and DOMAIN.md §6 require of routes and loops that still answer 501, so the
    Postgres enum needs no `ADD VALUE` migration when they land (ADR-0079).
    """

    USER_CREATED = "user.created"
    USER_UPDATED = "user.updated"
    USER_DELETED = "user.deleted"
    USER_CHANNEL_PREFERENCES_UPDATED = "user.channel_preferences_updated"
    USER_LOGGED_IN = "user.logged_in"
    USER_LOGGED_OUT = "user.logged_out"
    TEAM_CREATED = "team.created"
    TEAM_UPDATED = "team.updated"
    TEAM_DELETED = "team.deleted"
    TEAM_MEMBER_ADDED = "team.member_added"
    TEAM_MEMBER_ROLE_CHANGED = "team.member_role_changed"
    TEAM_MEMBER_REMOVED = "team.member_removed"
    TEAM_CHANNEL_PREFERENCES_UPDATED = "team.channel_preferences_updated"
    TEAM_ROTATION_UPDATED = "team.rotation_updated"
    SOURCE_CREATED = "source.created"
    SOURCE_UPDATED = "source.updated"
    SOURCE_DELETED = "source.deleted"
    SOURCE_TOKEN_ROTATED = "source.token_rotated"
    EVENT_SCHEMA_CREATED = "event_schema.created"
    RULE_CREATED = "rule.created"
    RULE_UPDATED = "rule.updated"
    RULE_DELETED = "rule.deleted"
    RUNBOOK_CREATED = "runbook.created"
    RUNBOOK_UPDATED = "runbook.updated"
    RUNBOOK_DELETED = "runbook.deleted"
    ALERT_CREATED = "alert.created"
    ALERT_RENOTIFIED = "alert.renotified"
    ALERT_ACKNOWLEDGED = "alert.acknowledged"
    ALERT_RESOLVED = "alert.resolved"
    ALERT_ESCALATED = "alert.escalated"
    STEP_AWAITING_APPROVAL = "step.awaiting_approval"
    STEP_AWAITING_ANSWER = "step.awaiting_answer"
    STEP_AWAITING_MANUAL = "step.awaiting_manual"
    STEP_STARTED = "step.started"
    STEP_SUCCEEDED = "step.succeeded"
    STEP_FAILED = "step.failed"
    STEP_SKIPPED = "step.skipped"
    STEP_APPROVED = "step.approved"
    STEP_REJECTED = "step.rejected"
    STEP_ANSWERED = "step.answered"
    STEP_DONE = "step.done"
    RUNBOOK_RUN_STARTED = "runbook_run.started"
    RUNBOOK_RUN_FINISHED = "runbook_run.finished"
    STEP_RETRY_FAILED = "step.retry_failed"


def entity_type_of(action: AuditAction) -> AuditEntityType:
    """The kind of entity every entry with this action names."""
    match action:
        case (
            AuditAction.USER_CREATED
            | AuditAction.USER_UPDATED
            | AuditAction.USER_DELETED
            | AuditAction.USER_CHANNEL_PREFERENCES_UPDATED
            | AuditAction.USER_LOGGED_IN
            | AuditAction.USER_LOGGED_OUT
        ):
            return AuditEntityType.USER
        case (
            AuditAction.TEAM_CREATED
            | AuditAction.TEAM_UPDATED
            | AuditAction.TEAM_DELETED
            | AuditAction.TEAM_MEMBER_ADDED
            | AuditAction.TEAM_MEMBER_ROLE_CHANGED
            | AuditAction.TEAM_MEMBER_REMOVED
            | AuditAction.TEAM_CHANNEL_PREFERENCES_UPDATED
            | AuditAction.TEAM_ROTATION_UPDATED
        ):
            return AuditEntityType.TEAM
        case (
            AuditAction.SOURCE_CREATED
            | AuditAction.SOURCE_UPDATED
            | AuditAction.SOURCE_DELETED
            | AuditAction.SOURCE_TOKEN_ROTATED
        ):
            return AuditEntityType.SOURCE
        case AuditAction.EVENT_SCHEMA_CREATED:
            return AuditEntityType.EVENT_SCHEMA
        case AuditAction.RULE_CREATED | AuditAction.RULE_UPDATED | AuditAction.RULE_DELETED:
            return AuditEntityType.RULE
        case AuditAction.RUNBOOK_CREATED | AuditAction.RUNBOOK_UPDATED | AuditAction.RUNBOOK_DELETED:
            return AuditEntityType.RUNBOOK
        case (
            AuditAction.ALERT_CREATED
            | AuditAction.ALERT_RENOTIFIED
            | AuditAction.ALERT_ACKNOWLEDGED
            | AuditAction.ALERT_RESOLVED
            | AuditAction.ALERT_ESCALATED
            | AuditAction.STEP_AWAITING_APPROVAL
            | AuditAction.STEP_AWAITING_ANSWER
            | AuditAction.STEP_AWAITING_MANUAL
            | AuditAction.STEP_STARTED
            | AuditAction.STEP_SUCCEEDED
            | AuditAction.STEP_FAILED
            | AuditAction.STEP_SKIPPED
            | AuditAction.STEP_APPROVED
            | AuditAction.STEP_REJECTED
            | AuditAction.STEP_ANSWERED
            | AuditAction.STEP_DONE
            | AuditAction.RUNBOOK_RUN_STARTED
            | AuditAction.RUNBOOK_RUN_FINISHED
            | AuditAction.STEP_RETRY_FAILED
        ):
            return AuditEntityType.ALERT
        case _:
            assert_never(action)


class AuditEntryRead(ReadModel):
    id: uuid.UUID
    at: UtcDatetime
    actor_user_id: uuid.UUID | None = Field(description="null: done by the system")
    actor_name: str | None = Field(
        default=None, description="Display name of the actor, kept after a soft delete; null for the system"
    )
    action: AuditAction
    entity_type: AuditEntityType
    entity_id: uuid.UUID
    team_id: uuid.UUID | None
    data: dict[str, Any]


def _iso_8601(value: object) -> object:
    if isinstance(value, str):
        datetime.fromisoformat(value)
    return value


IsoUtcDatetime = Annotated[UtcDatetime, BeforeValidator(_iso_8601)]


class AuditQuery(BaseModel):
    """`GET /audit` filters; every one that is set narrows the result."""

    team_id: uuid.UUID | None = None
    without_team: bool = Field(
        default=False, description="Only entries without a team; only admins read those. Not with `team_id`"
    )
    entity_type: AuditEntityType | None = None
    entity_id: uuid.UUID | None = None
    actor_user_id: uuid.UUID | None = None
    system: bool = Field(default=False, description="Only entries done by the system. Not with `actor_user_id`")
    action: list[AuditAction] = Field(default=[], description="Any of these actions; empty for every action")
    since: IsoUtcDatetime | None = Field(default=None, description="Inclusive lower bound on `at`")
    until: IsoUtcDatetime | None = Field(default=None, description="Exclusive upper bound on `at`; after `since`")

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.without_team and self.team_id is not None:
            raise ValueError("without_team cannot be combined with team_id")
        if self.system and self.actor_user_id is not None:
            raise ValueError("system cannot be combined with actor_user_id")
        if self.since is not None and self.until is not None and self.since >= self.until:
            raise ValueError("until must be after since")
        return self
