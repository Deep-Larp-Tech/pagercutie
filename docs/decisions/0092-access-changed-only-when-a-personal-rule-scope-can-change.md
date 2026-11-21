# ADR-0092: `access_changed` is sent only when a personal rule's source scope can change

- **ID:** ADR-0092
- **Timestamp:** 2026-11-21T08:05+01:00
- **Status:** Accepted
- **See:** SPEC §5.3, §8.1, DOMAIN.md §4, ADR-0057, ADR-0091

## Decision

`NotifyChannel.ACCESS_CHANGED` is sent in the transaction of:

- `teams.service.set_member` when it adds a membership, and `remove_member`;
- `users.service.update_user` when the global role changes, and `delete_user` (soft delete).

A team role change (`viewer` to `member`, …), a profile change and a team deletion do not send it.

## Rationale

- A personal rule sees the sources of its owner's teams in any role, every source for an admin, none once the owner
  is soft-deleted (DOMAIN.md §4). Only the four writes above change that scope.
- A team can only be deleted once it owns no sources, so its ID left in a scope matches no event.
