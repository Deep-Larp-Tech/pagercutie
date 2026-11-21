"""A `dedup.WindowStore` for tests that need no Redis."""

import uuid
from collections.abc import Mapping, Sequence

from pagercutie.pipeline.dedup import stage as dedup


class FakeWindows:
    """Answers each claim from `claims` by window key (`Won` when absent) and records every call."""

    def __init__(self, claims: Mapping[str, dedup.Claim] | None = None, claim_error: BaseException | None = None):
        self.claims = dict(claims or {})
        # Raised by `claim` after it recorded the requests.
        self.claim_error = claim_error
        self.claimed: list[list[dedup.ClaimRequest]] = []
        self.confirmed: list[dedup.Confirmation] = []
        self.released: list[dedup.Ownership] = []
        self.resolved: list[tuple[uuid.UUID, uuid.UUID, str]] = []

    async def claim(self, requests: Sequence[dedup.ClaimRequest]) -> list[dedup.Claim]:
        self.claimed.append(list(requests))
        if self.claim_error is not None:
            raise self.claim_error
        return [self.claims.get(r.key, dedup.Won(key=r.key)) for r in requests]

    async def confirm(self, confirmations: Sequence[dedup.Confirmation]) -> None:
        self.confirmed += confirmations

    async def release(self, owned: Sequence[dedup.Ownership]) -> None:
        self.released += owned

    async def mark_resolved(self, alert_id: uuid.UUID, rule_id: uuid.UUID, fingerprint: str) -> None:
        self.resolved.append((alert_id, rule_id, fingerprint))

    async def drain(self, batch: str, limit: int) -> list[dedup.Counter]:
        return []

    async def ack(self, batch: str) -> None:
        pass

    async def restore(self, batch: str) -> None:
        pass

    async def recover(self, older_than_s: int) -> int:
        return 0
