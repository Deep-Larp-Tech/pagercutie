import uuid

from sqlalchemy import ColumnElement, or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from pagercutie.alerts.models import Alert, Delivery
from pagercutie.alerts.schemas import DeliveryRead, DeliveryStatus
from pagercutie.auth.deps import CurrentUser
from pagercutie.core.enums import Channel
from pagercutie.core.errors import NotFound
from pagercutie.core.schemas import Pagination
from pagercutie.rules.models import Rule

_ALERT = "Alert"


def visible_alerts(actor: CurrentUser) -> ColumnElement[bool]:
    """Condition on `Alert` rows the actor may see (DOMAIN.md §4, ADR-0073).

    Admins see every alert. Others see alerts of their teams (any role), alerts escalated to one of their teams, and
    alerts of their own personal rules.
    """
    if actor.is_admin:
        return true()
    team_ids = list(actor.team_roles)
    conditions = [Alert.rule_id.in_(select(Rule.id).where(Rule.user_id == actor.id))]
    if team_ids:
        conditions += [Alert.team_id.in_(team_ids), Alert.escalated_team_ids.overlap(team_ids)]
    return or_(*conditions)


async def list_user_deliveries(
    session: AsyncSession, user_id: uuid.UUID, pagination: Pagination, channels: list[Channel] | None
) -> list[DeliveryRead]:
    """The user's deliveries, newest first, optionally only on these channels."""
    query = select(Delivery).where(Delivery.user_id == user_id)
    if channels:
        query = query.where(Delivery.channel.in_(channels))
    query = query.order_by(Delivery.created_at.desc(), Delivery.id.desc())
    query = query.limit(pagination.limit).offset(pagination.offset)
    return [DeliveryRead.model_validate(d) for d in await session.scalars(query)]


async def list_deliveries(
    session: AsyncSession,
    actor: CurrentUser,
    pagination: Pagination,
    channels: list[Channel] | None,
    statuses: list[DeliveryStatus] | None,
) -> list[DeliveryRead]:
    """Deliveries of the alerts the actor can see, newest first, optionally only these channels and statuses."""
    query = select(Delivery).join(Alert, Alert.id == Delivery.alert_id).where(visible_alerts(actor))
    if channels:
        query = query.where(Delivery.channel.in_(channels))
    if statuses:
        query = query.where(Delivery.status.in_(statuses))
    query = query.order_by(Delivery.created_at.desc(), Delivery.id.desc())
    query = query.limit(pagination.limit).offset(pagination.offset)
    return [DeliveryRead.model_validate(d) for d in await session.scalars(query)]


async def list_alert_deliveries(session: AsyncSession, actor: CurrentUser, alert_id: uuid.UUID) -> list[DeliveryRead]:
    """The alert's deliveries, newest first. An alert the actor cannot see is a 404, so its existence does not leak."""
    if await session.scalar(select(Alert.id).where(Alert.id == alert_id, visible_alerts(actor))) is None:
        raise NotFound(_ALERT, alert_id)
    deliveries = await session.scalars(
        select(Delivery).where(Delivery.alert_id == alert_id).order_by(Delivery.created_at.desc(), Delivery.id.desc())
    )
    return [DeliveryRead.model_validate(d) for d in deliveries]
