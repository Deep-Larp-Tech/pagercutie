import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pagercutie.users.models import User
from pagercutie.users.schemas import GlobalRole
from pagercutie.users.service import bootstrap_admin

pytestmark = pytest.mark.anyio


async def users(session: AsyncSession) -> list[tuple[str, GlobalRole]]:
    rows = await session.execute(select(User.email, User.role).order_by(User.email))
    return [(email, role) for email, role in rows]


async def test_creates_the_admin_when_none_exists(session: AsyncSession) -> None:
    assert await bootstrap_admin(session, "Admin@Example.com")

    user = await session.scalar(select(User))
    assert user is not None
    assert (user.email, user.display_name, user.timezone, user.role) == (
        "admin@example.com",
        "admin",
        "UTC",
        GlobalRole.ADMIN,
    )


async def test_does_nothing_when_an_admin_exists(session: AsyncSession) -> None:
    session.add(User(email="anna@example.com", display_name="Anna", timezone="UTC", role=GlobalRole.ADMIN))
    await session.flush()

    assert not await bootstrap_admin(session, "admin@example.com")

    assert await users(session) == [("anna@example.com", GlobalRole.ADMIN)]


async def test_promotes_an_existing_user(session: AsyncSession) -> None:
    session.add(User(email="admin@example.com", display_name="Bob", timezone="UTC", role=GlobalRole.USER))
    await session.flush()

    assert await bootstrap_admin(session, "admin@example.com")

    session.expunge_all()
    assert await users(session) == [("admin@example.com", GlobalRole.ADMIN)]
