"""Entrypoints of the dispatch stage, called by its loop in every replica (`worker.py`)."""

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from pagercutie.core.enums import Channel
from pagercutie.core.errors import NotImplementedYet


@dataclass(frozen=True)
class DeliveryJob:
    """A `pending` delivery leased to this replica by `claim_due`."""

    delivery_id: uuid.UUID
    alert_id: uuid.UUID
    user_id: uuid.UUID
    channel: Channel
    # Rendered for the channel when routing created the delivery.
    message: str
    # Earlier send attempts; the basis of the retry backoff.
    attempts: int


@dataclass(frozen=True)
class Sent:
    at: datetime


@dataclass(frozen=True)
class SendFailed:
    """The channel adapter failed; the delivery is retried with backoff (DEL-5) unless the failure is permanent."""

    error: str
    # The send can never succeed as configured, e.g. the user has no phone number; no retry is scheduled.
    permanent: bool = False


@dataclass(frozen=True)
class Throttled:
    """The recipient's token bucket is empty; the delivery joins their next digest (SPEC §9)."""


type SendResult = Sent | SendFailed | Throttled


class ChannelAdapter(Protocol):
    """Sends deliveries on one channel; replacing a simulated provider touches only its adapter (DEL-4)."""

    async def send(self, job: DeliveryJob) -> Sent | SendFailed:
        """Send `job.message` to `job.user_id`. Returns `SendFailed` for provider errors instead of raising."""
        ...


class Throttle(Protocol):
    """Per-recipient token buckets shared by every replica; the Redis implementation (SPEC §5.2)."""

    async def allow(self, user_id: uuid.UUID) -> bool:
        """Take one token for `user_id`. True when Redis cannot be reached: throttling fails open."""
        ...


async def claim_due(session: AsyncSession, limit: int, now: datetime) -> list[DeliveryJob]:
    """Lease up to `limit` due deliveries with `FOR UPDATE SKIP LOCKED` for 30 s (SPEC §10)."""
    raise NotImplementedYet("Delivery claiming")


async def send(job: DeliveryJob, adapters: Mapping[Channel, ChannelAdapter], throttle: Throttle) -> SendResult:
    """Throttle, then send through the adapter for `job.channel`. Runs outside any transaction."""
    raise NotImplementedYet("Delivery sending")


async def complete(session: AsyncSession, job: DeliveryJob, result: SendResult) -> None:
    """Mark the delivery `sent`, or `failed` with `retry_at`, and end its lease (DEL-6)."""
    raise NotImplementedYet("Delivery completion")
