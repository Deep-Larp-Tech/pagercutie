import structlog
from sqlalchemy import exists, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from pagercutie.preferences.schemas import ChannelPreferences
from pagercutie.users.models import User
from pagercutie.users.schemas import GlobalRole

log = structlog.get_logger("users")


async def bootstrap_admin(session: AsyncSession, email: str) -> bool:
    """Make `email` an admin, creating the user if needed, unless an admin already exists. True if it wrote one."""
    if await session.scalar(select(exists().where(User.role == GlobalRole.ADMIN))):
        return False
    email = email.lower()
    statement = insert(User).values(
        email=email,
        display_name=email.partition("@")[0],
        timezone="UTC",
        role=GlobalRole.ADMIN,
        channel_preferences=ChannelPreferences(),
    )
    # The upsert promotes an existing user, and lets API replicas starting together write the same row safely.
    await session.execute(statement.on_conflict_do_update(index_elements=[User.email], set_={"role": GlobalRole.ADMIN}))
    log.info("users.admin_bootstrapped", email=email)
    return True
