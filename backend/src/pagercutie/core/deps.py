from typing import Annotated

from fastapi import Depends, Query, Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pagercutie.core.broadcast import Broadcast
from pagercutie.core.db import get_session, get_sessionmaker
from pagercutie.core.redis import get_redis
from pagercutie.core.schemas import Pagination
from pagercutie.core.settings import Settings


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_alert_changes(request: Request) -> Broadcast:
    """The replica's broadcast of `NOTIFY alert_changed` payloads, set by `create_app`."""
    broadcast = request.app.state.alert_changes
    if not isinstance(broadcast, Broadcast):
        raise TypeError("app.state.alert_changes is not a Broadcast; create the app with create_app")
    return broadcast


SessionDep = Annotated[AsyncSession, Depends(get_session, scope="function")]
SessionmakerDep = Annotated[async_sessionmaker[AsyncSession], Depends(get_sessionmaker)]
RedisDep = Annotated[Redis, Depends(get_redis)]
SettingsDep = Annotated[Settings, Depends(get_app_settings)]
AlertChangesDep = Annotated[Broadcast, Depends(get_alert_changes)]
PaginationDep = Annotated[Pagination, Query()]
