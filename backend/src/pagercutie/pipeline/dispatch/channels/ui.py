"""UI channel: the delivery row is the notification; SSE feeds refresh when it is marked sent (UI-1, SPEC §10)."""

from datetime import UTC, datetime

from pagercutie.pipeline.dispatch.stage import DeliveryJob, SendFailed, Sent


class UiAdapter:
    """Does no I/O: `complete` announces the alert on `alert_changed` as `alert.updated` in the transaction that marks
    the delivery `sent` (`announces_on_sent`)."""

    async def send(self, job: DeliveryJob) -> Sent | SendFailed:
        return Sent(at=datetime.now(UTC))
