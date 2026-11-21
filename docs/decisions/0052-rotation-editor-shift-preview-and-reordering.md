# ADR-0052: Rotation editor: shift preview from the on-call answer, reordering with motion

- **ID:** ADR-0052
- **Timestamp:** 2026-11-21T03:18+01:00
- **Status:** Accepted
- **See:** docs/plans/frontend.md chunk 5, DOMAIN.md §5, ADR-0027, `frontend/src/lib/rotation.ts`,
  `frontend/src/components/team-settings/rotation-settings.tsx`

## Decision

**Shift preview.** The rotation page lists the next four shifts, computed in the browser by `upcomingShifts` with
the DOMAIN.md §5 rule: the next person takes over at every `handoff_day` + `handoff_time` in the rotation's time
zone, wrapping around. Each handoff is the next local weekday and time, so a DST change moves the UTC instant and
keeps the wall-clock time.

`Rotation` carries no start date, so the preview needs an anchor:

- While the form matches the saved rotation, the preview starts from `GET /teams/{id}/on-call`: that person until
  `until`, then the people after them in order.
- Once the form has unsaved changes (or the team has no rotation yet), the preview shows what saving would do. A
  `PUT` replaces the rotation and restarts it with `user_ids[0]` (`teams/models.py`), so the first person is on
  call from now until the next handoff. The heading changes to "Next four shifts after you save".

**Reordering.** Rows reorder by dragging a handle (motion's `Reorder.Group` and `useDragControls`) or with
**Move up** and **Move down** buttons, which are the keyboard and screen-reader path. The tests drive the buttons.

## Options for reordering

| | Move buttons only | motion `Reorder` + move buttons (chosen) | `@dnd-kit` |
|---|---|---|---|
| New dependency | None | None (`motion` is already in DESIGN.md §2) | `@dnd-kit/core`, `@dnd-kit/sortable` |
| Pointer drag | No | Yes, by a handle | Yes |
| Keyboard | Buttons | Buttons | Built-in sensor plus live announcements |
| Motion | None | `layout` transforms, DESIGN.md §8 spring | Its own transforms |
| Effort | Least | Small | Most |

## Rationale

- The API exposes no rotation start, and asking for one is a contract change; the on-call answer already says who
  is on call and until when, which is all the preview needs for the saved rotation.
- Showing "after you save" makes the restart on `PUT` visible before a lead triggers it.
- motion covers drag without a new package, and the buttons give a keyboard path that needs no drag at all.
