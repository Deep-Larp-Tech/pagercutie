import uuid

import pytest
from pydantic import ValidationError

from pagercutie.rules.schemas import Routing

RECIPIENTS = [{"type": "user", "user_id": str(uuid.uuid7())}]


def test_routing_channels_reject_an_empty_list() -> None:
    with pytest.raises(ValidationError):
        Routing.model_validate({"recipients": RECIPIENTS, "channels": []})


@pytest.mark.parametrize("channels", [None, ["sms"]])
def test_routing_channels_accept_null_or_a_list(channels: list[str] | None) -> None:
    assert Routing.model_validate({"recipients": RECIPIENTS, "channels": channels}).channels == channels
