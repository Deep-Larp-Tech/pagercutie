import pytest

from pagercutie.pipeline.dispatch.channels.contacts import mask_phone


@pytest.mark.parametrize(
    ("phone", "masked"),
    [("+420123456789", "**********789"), ("123", "123"), ("12", "12"), ("", "")],
)
def test_mask_phone_keeps_the_last_three_characters(phone: str, masked: str) -> None:
    assert mask_phone(phone) == masked
