# Farmhouse CRUD

**Type:** AFK
**Source:** [issues/prd.md](prd.md)

## What to build

Admins manage the set of farmhouses end-to-end. An Admin can create, edit, and disable a farmhouse (name, description, capacity, buffer minutes default 0, optional operating hours). Farmhouses appear in a list and become selectable wherever a farmhouse is chosen (e.g., the calendar selector). Bookies have read-only access to the list.

## Acceptance criteria

- [ ] `farmhouses` table and model exist with name, description, capacity, buffer_minutes (default 0), optional operating_hours, status.
- [ ] Admin-only create/edit/disable endpoints; bookie read-only list/detail.
- [ ] React admin UI to create/edit/disable a farmhouse and view the list.
- [ ] Disabled farmhouses are excluded from selection for new bookings.
- [ ] Role guard prevents bookies from mutating farmhouses (403).
- [ ] Tests cover CRUD, role enforcement, and disable behavior.

## Blocked by

- #2 Login & session
