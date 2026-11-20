from typing import Annotated

from fastapi import Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from larper.core.db import get_session, get_sessionmaker
from larper.core.schemas import Pagination
from larper.core.settings import Settings


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings


SessionDep = Annotated[AsyncSession, Depends(get_session, scope="function")]
SessionmakerDep = Annotated[async_sessionmaker[AsyncSession], Depends(get_sessionmaker)]
SettingsDep = Annotated[Settings, Depends(get_app_settings)]
PaginationDep = Annotated[Pagination, Query()]
