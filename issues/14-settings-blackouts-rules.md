# Settings, blackout dates & business rules

**Type:** AFK
**Source:** [issues/prd.md](prd.md)

## What to build

Make the operating constraints configurable and enforced. Admins manage system settings (hold duration, minimum advance notice, buffer defaults, operating hours) and blackout dates/holidays (per-farmhouse or global) that mark dates unavailable. The booking flow enforces these rules: future-only and no-Booked-overlap are always on; minimum advance notice, operating hours, and blackout dates block conflicting holds/submissions when configured.

## Acceptance criteria

- [ ] `settings` (singleton) and `blackout_dates` models exist; admin endpoints to read/update settings and CRUD blackout dates.
- [ ] Hold duration setting drives `expires_at` on new holds.
- [ ] Minimum advance notice (when set) blocks holds/submissions that are too soon.
- [ ] Blackout dates (global or per-farmhouse) block holds/submissions overlapping those dates with a clear message.
- [ ] Operating-hours constraint (when set) is enforced on booking ranges.
- [ ] React admin UI for settings and blackout dates.
- [ ] Tests cover each rule's enforcement and the disabled/off defaults.

## Blocked by

- #5 Farmhouse CRUD
