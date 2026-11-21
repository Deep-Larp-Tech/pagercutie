import pytest
from pydantic import ValidationError

from pagercutie.core.settings import Settings


def test_the_defaults_fit_the_send_and_the_connection_wait_inside_the_lease() -> None:
    settings = Settings()

    assert settings.delivery_send_timeout_seconds + settings.db_worker_pool_timeout_seconds < (
        settings.delivery_lease_seconds
    )


def test_a_send_timeout_that_could_outlive_the_lease_is_rejected() -> None:
    with pytest.raises(ValidationError, match="must not exceed delivery_lease_seconds"):
        Settings(delivery_lease_seconds=30, delivery_send_timeout_seconds=25, db_worker_pool_timeout_seconds=5)
