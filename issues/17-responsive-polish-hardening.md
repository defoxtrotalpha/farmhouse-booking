# Responsive polish & hardening

**Type:** AFK
**Source:** [issues/prd.md](prd.md)

## What to build

Final pass to meet the non-functional requirements. Verify and fix the UI for both mobile and desktop viewports, tune polling intervals, and run a security/hardening pass (auth on every endpoint, role guards, input validation at boundaries, token/secret handling, expiring tokens). Confirm the full stack builds and runs cleanly end-to-end.

## Acceptance criteria

- [ ] All primary screens (login, calendar, booking, admin panels) are usable on mobile and desktop viewports.
- [ ] Every API endpoint is authenticated and role-guarded; verified by tests.
- [ ] Input validation exists at all write boundaries; invalid input returns clear errors.
- [ ] Secrets/tokens are sourced from config, never committed; invite/reset tokens expire.
- [ ] Polling intervals for calendar and notifications are tuned and documented.
- [ ] `alembic upgrade head` is clean and `docker compose up` brings up the full stack end-to-end.
- [ ] A short end-to-end smoke test covers the core journey (invite → login → hold → submit → approve → notify → cancel).

## Blocked by

- #8 Approve → Booked + overlap exclusion constraint
- #12 Notifications
- #14 Settings, blackout dates & business rules
