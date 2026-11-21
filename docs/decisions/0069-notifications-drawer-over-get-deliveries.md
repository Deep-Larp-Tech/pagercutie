# ADR-0069: Notifications drawer over GET /deliveries

- **ID:** ADR-0069
- **Timestamp:** 2026-11-21T13:00+01:00
- **Status:** Accepted
- **See:** ADR-0013, DOMAIN.md §4 and §7, DESIGN.md §9, `frontend/src/components/notifications/`

## Decision

The simulated phone page (`/me/phone`) is replaced by a notifications drawer on every signed-in screen: a non-modal
panel on the right, opened from the header, that lists deliveries on every channel (email, SMS, phone, UI) newest
first, with a channel filter. It reads a new endpoint, `GET /deliveries?channel=&status=&limit=&offset=` in the
`alerts` module, which returns `DeliveryRead` for alerts the current user can see (their teams', escalated and
personal-rule alerts); admins see all. The route is a `501` stub until the delivery service lands. `GET
/me/messages` stays in the contract.

## Rationale

- The demo needs to show what every simulated channel sent (`DEL-4`, `DEL-6`), not only one user's SMS and calls.
- One query covers every channel and recipient. Calling `GET /alerts/{id}/deliveries` per alert would mean one
  request per alert and would miss alerts outside the loaded feed.
- Scoping to visible alerts keeps other teams' alert text private while judges switch personas; admins debug
  everything.
- Non-modal, so a user can acknowledge an alert and watch the messages go out in the same view.
- Adding a route is an additive contract change (SPEC §4.1).
