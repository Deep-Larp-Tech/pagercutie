"""Metrics of the dispatch stage, recorded from what `claim_due`, `cancel_for_resolved_alerts` and `complete` return
(SPEC §13); the SQL writers record none themselves."""

from collections.abc import Sequence
from typing import assert_never

from opentelemetry import metrics

from pagercutie.alerts.schemas import DeliveryStatus
from pagercutie.core.enums import Channel
from pagercutie.pipeline.dispatch.fallback import FellBack, Unreachable
from pagercutie.pipeline.dispatch.stage import Completion, Delivered, GaveUp, LeaseLost, Postponed, RetryScheduled

_meter = metrics.get_meter("pagercutie.dispatch")
_deliveries = _meter.create_counter(
    "deliveries_total", description="Send attempts that ended sent, failed or undeliverable, by channel and status"
)
_retries = _meter.create_counter("delivery_retries_total", description="Failed sends scheduled for another attempt")
_latency = _meter.create_histogram(
    "end_to_end_latency_seconds",
    unit="s",
    description="Time from ingest receiving the event to the delivery being sent",
    explicit_bucket_boundaries_advisory=[0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 300],
)
_throttled = _meter.create_counter(
    "deliveries_throttled_total", description="Sends held back because the recipient's token bucket was empty"
)
_digests = _meter.create_counter("digests_created_total", description="Digest deliveries created from throttled ones")
_cancelled = _meter.create_counter(
    "deliveries_cancelled_total", description="Unsent deliveries cancelled because their alert was resolved"
)
_fallbacks = _meter.create_counter(
    "delivery_fallbacks_total", description="Fallback deliveries created after a permanent failure, by channel pair"
)
_unreachable = _meter.create_counter(
    "recipients_unreachable_total",
    description="Permanent failures with no untried channel left for the recipient, by the last channel",
)
_leases_lost = _meter.create_counter(
    "delivery_leases_lost_total", description="Results dropped because the lease expired before completion"
)


def record_completion(completion: Completion) -> None:
    """Count one `complete` call."""
    match completion:
        case Delivered(channel=channel, latencies_s=latencies):
            _deliveries.add(1, {"channel": channel.value, "status": DeliveryStatus.SENT.value})
            for seconds in latencies:
                _latency.record(seconds, {"channel": channel.value})
        case RetryScheduled(channel=channel):
            _deliveries.add(1, {"channel": channel.value, "status": DeliveryStatus.FAILED.value})
            _retries.add(1, {"channel": channel.value})
        case GaveUp(channel=channel, fallbacks=fallbacks):
            _deliveries.add(1, {"channel": channel.value, "status": DeliveryStatus.UNDELIVERABLE.value})
            for fallback in fallbacks:
                match fallback:
                    case FellBack(from_channel=source, to_channel=target):
                        _fallbacks.add(1, {"from_channel": source.value, "to_channel": target.value})
                    case Unreachable(channel=last):
                        _unreachable.add(1, {"channel": last.value})
                    case _:
                        assert_never(fallback)
        case Postponed(channel=channel, merged=merged):
            _throttled.add(1, {"channel": channel.value})
            if merged is not None and merged.created:
                _digests.add(1, {"channel": channel.value})
        case LeaseLost(channel=channel):
            _leases_lost.add(1, {"channel": channel.value})
        case _:
            assert_never(completion)


def record_cancelled(channels: Sequence[Channel]) -> None:
    """Count the deliveries one `cancel_for_resolved_alerts` call cancelled."""
    for channel in channels:
        _cancelled.add(1, {"channel": channel.value})
