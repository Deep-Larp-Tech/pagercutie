"""A delivery row's state as one tagged union, parsed from its columns in one place (SPEC §10, ADR-0110).

The row encodes the state in `status`, `retry_at`, `lease_until` and `digest_id`; this module is the only reader of
that encoding, in Python (`parse`) and in SQL (`due`, `open_for_resolved_alert`).
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import assert_never

from sqlalchemy import ColumnElement, and_, or_

from pagercutie.alerts.models import Delivery
from pagercutie.alerts.schemas import DeliveryStatus


@dataclass(frozen=True)
class Due:
    """`pending` and not held back: the next claim may take it."""


@dataclass(frozen=True)
class HeldBack:
    """`pending` with `retry_at` ahead: throttled until the recipient's bucket holds a token again."""

    retry_at: datetime


@dataclass(frozen=True)
class InDigest:
    """`pending` and merged into a digest; sent or failed with the digest, never claimed itself (ADR-0081)."""

    digest_id: uuid.UUID


@dataclass(frozen=True)
class Leased:
    """Claimed by a dispatcher whose lease has not passed; no other replica may take it."""

    lease_until: datetime


@dataclass(frozen=True)
class Retrying:
    """`failed` with `retry_at`: the last attempt failed transiently (DEL-5)."""

    retry_at: datetime


@dataclass(frozen=True)
class Delivered:
    """`sent`: terminal."""


@dataclass(frozen=True)
class Undeliverable:
    """Failed permanently and never retried (ADR-0082); a fallback channel may take over (ADR-0110). Terminal.

    Rows written before `undeliverable` existed are `failed` with no `retry_at` and parse to this state too.
    """


@dataclass(frozen=True)
class Cancelled:
    """Its alert was resolved before it was sent (ADR-0110). Terminal."""


type DeliveryState = Due | HeldBack | InDigest | Leased | Retrying | Delivered | Undeliverable | Cancelled


def parse(
    status: DeliveryStatus,
    retry_at: datetime | None,
    lease_until: datetime | None,
    digest_id: uuid.UUID | None,
    now: datetime,
) -> DeliveryState:
    """The state of a row with these columns at `now`."""
    match status:
        case DeliveryStatus.SENT:
            return Delivered()
        case DeliveryStatus.UNDELIVERABLE:
            return Undeliverable()
        case DeliveryStatus.CANCELLED:
            return Cancelled()
        case DeliveryStatus.PENDING | DeliveryStatus.FAILED:
            pass
        case _:
            assert_never(status)
    if lease_until is not None and lease_until >= now:
        return Leased(lease_until)
    if status is DeliveryStatus.FAILED:
        return Undeliverable() if retry_at is None else Retrying(retry_at)
    if digest_id is not None:
        return InDigest(digest_id)
    if retry_at is not None and retry_at > now:
        return HeldBack(retry_at)
    return Due()


def is_claimable(state: DeliveryState, now: datetime) -> bool:
    """Whether a claim at `now` takes a row in `state`; `due` is the same test in SQL."""
    match state:
        case Due():
            return True
        case Retrying(retry_at=retry_at):
            return retry_at <= now
        case HeldBack() | InDigest() | Leased() | Delivered() | Undeliverable() | Cancelled():
            return False
        case _:
            assert_never(state)


def unleased(now: datetime) -> ColumnElement[bool]:
    """No dispatcher holds the row at `now`."""
    return or_(Delivery.lease_until.is_(None), Delivery.lease_until < now)


def due(now: datetime) -> ColumnElement[bool]:
    """SQL for `is_claimable`: `Due`, or `Retrying` whose `retry_at` passed."""
    return and_(
        unleased(now),
        or_(
            and_(
                Delivery.status == DeliveryStatus.PENDING,
                Delivery.digest_id.is_(None),
                or_(Delivery.retry_at.is_(None), Delivery.retry_at <= now),
            ),
            and_(Delivery.status == DeliveryStatus.FAILED, Delivery.retry_at <= now),
        ),
    )


def unsent(now: datetime) -> ColumnElement[bool]:
    """Not terminal and not leased: `Due`, `HeldBack`, `InDigest` or `Retrying`; what resolving an alert cancels."""
    return and_(
        unleased(now),
        or_(
            Delivery.status == DeliveryStatus.PENDING,
            and_(Delivery.status == DeliveryStatus.FAILED, Delivery.retry_at.is_not(None)),
        ),
    )
