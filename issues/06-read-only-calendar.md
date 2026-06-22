# Read-only calendar + availability

**Type:** AFK
**Source:** [issues/prd.md](prd.md)

## What to build

A shared, read-only calendar that shows existing bookings for a selected farmhouse. Uses FullCalendar's free time-grid (day/week) with a farmhouse selector showing one farmhouse at a time. All times render in Asia/Karachi while stored as UTC. A backend availability endpoint returns occupied vs free ranges for a farmhouse over a queried window, and the calendar reflects them with status-based colors. Data refreshes via short polling (no WebSockets).

## Acceptance criteria

- [ ] Availability endpoint returns occupied/free ranges for a given farmhouse and date window.
- [ ] FullCalendar time-grid renders bookings for the selected farmhouse in Asia/Karachi time.
- [ ] Farmhouse selector switches the calendar between farmhouses (one at a time).
- [ ] Bookings spanning midnight / multiple days render correctly across day boundaries.
- [ ] Calendar refreshes on a configurable polling interval.
- [ ] Statuses are visually distinguished by color.
- [ ] Tests cover the availability computation (including multi-day ranges).

## Blocked by

- #5 Farmhouse CRUD
