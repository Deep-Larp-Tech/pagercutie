"""Entrypoints of the dedup stage.

The orchestrator calls them in order: `claim` before the transaction, `record` inside it, then `confirm` after the
commit or `release` after a failure (SPEC §5.2).
"""

import uuid
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from pagercutie.core.errors import NotImplementedYet
from pagercutie.pipeline.messages import DedupOutcome, Match, Repeated


@dataclass(frozen=True)
class Won:
    """This match claimed the dedup window; the key holds `pending` until `confirm`."""

    key: str


@dataclass(frozen=True)
class Held:
    """The window is claimed and its alert is committed: count the occurrence in Redis only."""

    key: str
    alert_id: uuid.UUID


@dataclass(frozen=True)
class Pending:
    """The window is claimed but its alert is not committed yet, or its winner failed: upsert in Postgres."""

    key: str


@dataclass(frozen=True)
class Unavailable:
    """Redis could not be reached: upsert in Postgres."""

    key: str


type Claim = Won | Held | Pending | Unavailable

# Claims whose match is upserted in Postgres.
type Recordable = Won | Pending | Unavailable


class WindowStore(Protocol):
    """Dedup windows and occurrence counters shared by every replica; the Redis implementation (SPEC §5.2).

    Implementations return `Unavailable` (claim) or do nothing (the other methods) when Redis cannot be reached,
    and never raise for it: a Redis outage costs Postgres writes, not alerts.
    """

    async def claim(self, key: str, window_s: int) -> Claim:
        """`SET key pending NX EX window_s`; `Held` or `Pending` from the current value when the key exists."""
        ...

    async def confirm(self, key: str, alert_id: uuid.UUID) -> None:
        """`SET key alert_id XX KEEPTTL`, after the alert is committed."""
        ...

    async def release(self, key: str) -> None:
        """`DEL key`, after the transaction that would have committed the alert failed."""
        ...

    async def increment(self, key: str) -> None:
        """`INCR` the key's occurrence counter and mark it for the next flush."""
        ...


def window_key(match: Match) -> str:
    """Redis key of the match's dedup window, `dedup:{rule_id}:{fingerprint}`."""
    return f"dedup:{match.rule.id}:{match.fingerprint}"


async def claim(match: Match, windows: WindowStore) -> Claim:
    """Try to claim the match's dedup window for `match.rule.dedup.window_s` seconds."""
    return await windows.claim(window_key(match), match.rule.dedup.window_s)


async def record(session: AsyncSession, match: Match, claim: Recordable) -> DedupOutcome:
    """Upsert the match's alert in Postgres; the partial unique index on the fingerprint keeps this idempotent.

    `Won` returns `Opened` for a new alert and `Renotified` for one that is still not resolved; `Pending` and
    `Unavailable` return `Opened` or `Repeated`.
    """
    raise NotImplementedYet("Alert upsert")


async def repeat(match: Match, claim: Held, windows: WindowStore) -> Repeated:
    """Count one more occurrence of the committed alert in Redis; no Postgres write."""
    raise NotImplementedYet("Occurrence counting")


async def confirm(claim: Claim, outcome: DedupOutcome, windows: WindowStore) -> None:
    """Store the committed alert's ID in a `Won` window, so later matches take the Redis-only path."""
    raise NotImplementedYet("Dedup window confirmation")


async def release(claim: Claim, windows: WindowStore) -> None:
    """Free a `Won` window whose alert was not committed, so the next match retries the upsert."""
    raise NotImplementedYet("Dedup window release")
