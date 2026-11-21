"""`WindowStore` on Redis: dedup window claims, per-alert occurrence counters and resolved markers (SPEC §5.2).

Every method is one Lua script, so one round trip covers all of an event's windows and each step is atomic. Scripts
build the counter and marker keys from the alert IDs they read, which a single Redis allows and Redis Cluster does
not; compose runs a single Redis.
"""

import math
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import TypeGuard

import structlog
from redis.asyncio import Redis
from redis.exceptions import RedisError

from pagercutie.core.redis import (
    RESOLVED_MARKER_PREFIX,
    RESOLVED_MARKER_TTL_S,
    dedup_window_key,
    resolved_marker_key,
)
from pagercutie.pipeline.dedup.stage import (
    PENDING,
    Claim,
    ClaimRequest,
    Confirmation,
    Counter,
    Held,
    Ownership,
    Pending,
    Unavailable,
    Won,
)

log = structlog.get_logger("dedup")

# Alert IDs whose counters changed since the last flush.
DIRTY_KEY = "count:dirty"
# Drained batches waiting for their flush to commit, scored by drain time in Redis seconds (ADR-0099).
BATCHES_KEY = "count:batches"

_COUNTER_PREFIX = "count:"
_BATCH_PREFIX = "count:batch:"
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)

# Adds `n` occurrences seen at `seen` (epoch microseconds) to the alert's counter and marks it dirty.
_ADD_FN = """
local function add(counter_prefix, dirty, id, n, seen)
  local key = counter_prefix .. id
  redis.call('HINCRBY', key, 'n', n)
  local old = redis.call('HGET', key, 'seen')
  if not old or tonumber(old) < tonumber(seen) then
    redis.call('HSET', key, 'seen', seen)
  end
  redis.call('SADD', dirty, id)
end
"""

# Moves a drained batch back into the counters and forgets it.
_RESTORE_FN = """
local function restore(counter_prefix, dirty, batches, batch)
  local fields = redis.call('HGETALL', batch)
  for i = 1, #fields, 2 do
    local sep = string.find(fields[i + 1], ':', 1, true)
    add(counter_prefix, dirty, fields[i], string.sub(fields[i + 1], 1, sep - 1), string.sub(fields[i + 1], sep + 1))
  end
  redis.call('DEL', batch)
  redis.call('ZREM', batches, batch)
end
"""

# KEYS: dirty set, then one window per claim. ARGV: marker prefix, counter prefix, then per claim the token,
# window_s and seen (epoch microseconds). Returns per claim a kind (won, held, pending) and the previous value.
# A window holding an alert ID counts the occurrence in the same step, unless the alert is marked resolved: then the
# claim takes the window over, so the match goes to Postgres (ADR-0098).
_CLAIM = (
    _ADD_FN
    + """
local uuid = '^' .. string.rep('%x', 8) .. '%-' .. string.rep('%x', 4) .. '%-' .. string.rep('%x', 4) .. '%-'
  .. string.rep('%x', 4) .. '%-' .. string.rep('%x', 12) .. '$'
local out = {}
for i = 2, #KEYS do
  local base = 3 + (i - 2) * 3
  local token, window_s, seen = ARGV[base], ARGV[base + 1], ARGV[base + 2]
  local previous = redis.call('GET', KEYS[i])
  local alert = previous and string.match(previous, uuid)
  if alert and redis.call('EXISTS', ARGV[1] .. alert) == 0 then
    add(ARGV[2], KEYS[1], alert, 1, seen)
    table.insert(out, 'held')
    table.insert(out, alert)
  elseif previous and not alert then
    table.insert(out, 'pending')
    table.insert(out, previous)
  else
    redis.call('SET', KEYS[i], token, 'EX', window_s)
    table.insert(out, 'won')
    table.insert(out, previous or '')
  end
end
return out
"""
)

# KEYS: one window per confirmation. ARGV: marker prefix, then per window the token, alert ID and TTL in ms ('' keeps
# the TTL). Only the claim's own token is replaced; a window whose alert is marked resolved is deleted instead.
_CONFIRM = """
for i = 1, #KEYS do
  local base = 2 + (i - 1) * 3
  local token, alert, ttl_ms = ARGV[base], ARGV[base + 1], ARGV[base + 2]
  if redis.call('GET', KEYS[i]) == token then
    if redis.call('EXISTS', ARGV[1] .. alert) == 1 then
      redis.call('DEL', KEYS[i])
    elseif ttl_ms == '' then
      redis.call('SET', KEYS[i], alert, 'KEEPTTL')
    else
      redis.call('SET', KEYS[i], alert, 'PX', ttl_ms)
    end
  end
end
"""

# KEYS: one window per release. ARGV: the token per window. Deletes only windows that still hold the claim's token.
_RELEASE = """
for i = 1, #KEYS do
  if redis.call('GET', KEYS[i]) == ARGV[i] then
    redis.call('DEL', KEYS[i])
  end
end
"""

# KEYS: window, marker. ARGV: alert ID, marker TTL in seconds.
_MARK_RESOLVED = """
redis.call('SET', KEYS[2], '1', 'EX', ARGV[2])
if redis.call('GET', KEYS[1]) == ARGV[1] then
  redis.call('DEL', KEYS[1])
end
"""

# KEYS: dirty set, batch hash, batches set. ARGV: limit, counter prefix. Returns [alert_id, n, seen, ...].
# Pops up to `limit` dirty counters into the batch hash, which the caller deletes once its flush committed. An
# increment lands either in this batch or in a fresh counter for the next one.
_DRAIN = """
local out = {}
for _, id in ipairs(redis.call('SPOP', KEYS[1], ARGV[1])) do
  local key = ARGV[2] .. id
  local counter = redis.call('HMGET', key, 'n', 'seen')
  redis.call('DEL', key)
  if counter[1] and counter[2] then
    redis.call('HSET', KEYS[2], id, counter[1] .. ':' .. counter[2])
    table.insert(out, id)
    table.insert(out, counter[1])
    table.insert(out, counter[2])
  end
end
if #out > 0 then
  redis.call('ZADD', KEYS[3], redis.call('TIME')[1], KEYS[2])
end
return out
"""

# KEYS: batch hash, batches set.
_ACK = """
redis.call('DEL', KEYS[1])
redis.call('ZREM', KEYS[2], KEYS[1])
"""

# KEYS: dirty set, batches set, batch hash. ARGV: counter prefix.
_RESTORE = (
    _ADD_FN
    + _RESTORE_FN
    + """
restore(ARGV[1], KEYS[1], KEYS[2], KEYS[3])
"""
)

# KEYS: dirty set, batches set. ARGV: counter prefix, age in seconds. Restores every batch drained at least `age`
# seconds ago (by the Redis clock) and returns how many.
_RECOVER = (
    _ADD_FN
    + _RESTORE_FN
    + """
local cutoff = tonumber(redis.call('TIME')[1]) - tonumber(ARGV[2])
local stale = redis.call('ZRANGEBYSCORE', KEYS[2], '-inf', cutoff)
for _, batch in ipairs(stale) do
  restore(ARGV[1], KEYS[1], KEYS[2], batch)
end
return #stale
"""
)


def counter_key(alert_id: uuid.UUID) -> str:
    """Redis hash of the alert's unflushed occurrences: `n` (count) and `seen` (newest, epoch microseconds)."""
    return f"{_COUNTER_PREFIX}{alert_id}"


def batch_key(batch: str) -> str:
    """Redis hash of a drained batch: alert ID to `n:seen`, until the flush that took it commits."""
    return f"{_BATCH_PREFIX}{batch}"


def _epoch_us(at: datetime) -> int:
    return (at - _EPOCH) // timedelta(microseconds=1)


class RedisWindowStore:
    """Needs a client created with `decode_responses=True` (`core.redis.create_redis`).

    Every Redis error degrades instead of raising (SPEC §5.2): a connection or timeout error, and a `ResponseError`
    such as `READONLY` or `OOM`.
    """

    def __init__(self, redis: Redis) -> None:
        self._claim = redis.register_script(_CLAIM)
        self._confirm = redis.register_script(_CONFIRM)
        self._release = redis.register_script(_RELEASE)
        self._mark_resolved = redis.register_script(_MARK_RESOLVED)
        self._drain = redis.register_script(_DRAIN)
        self._ack = redis.register_script(_ACK)
        self._restore = redis.register_script(_RESTORE)
        self._recover = redis.register_script(_RECOVER)

    async def claim(self, requests: Sequence[ClaimRequest]) -> list[Claim]:
        if not requests:
            return []
        args: list[str | int] = [RESOLVED_MARKER_PREFIX, _COUNTER_PREFIX]
        for request in requests:
            args += [request.token, request.window_s, _epoch_us(request.seen_at)]
        try:
            reply = await self._claim(keys=[DIRTY_KEY, *(r.key for r in requests)], args=args)
        except RedisError:
            log.warning("dedup.redis_unavailable", operation="claim", exc_info=True)
            return [Unavailable(key=request.key) for request in requests]
        if not _strings(reply) or len(reply) != 2 * len(requests):
            raise TypeError(f"claim script returned {reply!r}")
        return [
            _claim(request.key, kind, value)
            for request, kind, value in zip(requests, reply[0::2], reply[1::2], strict=True)
        ]

    async def confirm(self, confirmations: Sequence[Confirmation]) -> None:
        if not confirmations:
            return
        args: list[str | int] = [RESOLVED_MARKER_PREFIX]
        for c in confirmations:
            args += [
                c.token,
                str(c.alert_id),
                "" if c.ttl is None else max(1, math.ceil(c.ttl / timedelta(milliseconds=1))),
            ]
        try:
            await self._confirm(keys=[c.key for c in confirmations], args=args)
        except RedisError:
            log.warning("dedup.redis_unavailable", operation="confirm", exc_info=True)

    async def release(self, owned: Sequence[Ownership]) -> None:
        if not owned:
            return
        try:
            await self._release(keys=[o.key for o in owned], args=[o.token for o in owned])
        except RedisError:
            log.warning("dedup.redis_unavailable", operation="release", exc_info=True)

    async def mark_resolved(self, alert_id: uuid.UUID, rule_id: uuid.UUID, fingerprint: str) -> None:
        keys = [dedup_window_key(rule_id, fingerprint), resolved_marker_key(alert_id)]
        try:
            await self._mark_resolved(keys=keys, args=[str(alert_id), RESOLVED_MARKER_TTL_S])
        except RedisError:
            log.warning("dedup.redis_unavailable", operation="mark_resolved", alert_id=str(alert_id), exc_info=True)

    async def drain(self, batch: str, limit: int) -> list[Counter]:
        try:
            reply = await self._drain(keys=[DIRTY_KEY, batch_key(batch), BATCHES_KEY], args=[limit, _COUNTER_PREFIX])
        except RedisError:
            # The script may have run: a batch it moved is recovered once it is old enough.
            log.warning("dedup.redis_unavailable", operation="drain", batch=batch, exc_info=True)
            return []
        if not _strings(reply) or len(reply) % 3:
            raise TypeError(f"drain script returned {reply!r}")
        return [
            Counter(
                alert_id=uuid.UUID(alert_id),
                occurrences=int(n),
                last_seen_at=_EPOCH + timedelta(microseconds=int(seen)),
            )
            for alert_id, n, seen in zip(reply[0::3], reply[1::3], reply[2::3], strict=True)
        ]

    async def ack(self, batch: str) -> None:
        try:
            await self._ack(keys=[batch_key(batch), BATCHES_KEY])
        except RedisError:
            log.warning("dedup.batch_not_acked", batch=batch, message="Recovery will count this batch twice")

    async def restore(self, batch: str) -> None:
        try:
            await self._restore(keys=[DIRTY_KEY, BATCHES_KEY, batch_key(batch)], args=[_COUNTER_PREFIX])
        except RedisError:
            log.warning("dedup.redis_unavailable", operation="restore", batch=batch, exc_info=True)

    async def recover(self, older_than_s: int) -> int:
        try:
            reply = await self._recover(keys=[DIRTY_KEY, BATCHES_KEY], args=[_COUNTER_PREFIX, older_than_s])
        except RedisError:
            log.warning("dedup.redis_unavailable", operation="recover", exc_info=True)
            return 0
        if not isinstance(reply, int):
            raise TypeError(f"recover script returned {reply!r}")
        return reply


def _strings(reply: object) -> TypeGuard[list[str]]:
    return isinstance(reply, list) and all(isinstance(item, str) for item in reply)


def _claim(key: str, kind: str, value: str) -> Claim:
    match kind:
        case "won":
            return Won(key=key)
        case "held":
            return Held(key=key, alert_id=uuid.UUID(value))
        case "pending":
            if not value.startswith(PENDING):
                # Postgres decides whatever the key holds (SPEC §5.2).
                log.warning("dedup.window_value_invalid", key=key, value=value)
            return Pending(key=key)
        case _:
            raise TypeError(f"claim script returned kind {kind!r}")
