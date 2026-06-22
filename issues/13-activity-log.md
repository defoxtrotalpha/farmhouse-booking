# Activity log (append-only, role-filtered)

**Type:** AFK
**Source:** [issues/prd.md](prd.md)

## What to build

A traceable, immutable audit trail. Every state-changing action (login, invite, hold created, request submitted, approved, rejected, canceled, farmhouse/settings/policy changes) appends an entry recording actor, action, target type/id, UTC timestamp, and an optional note. The log is append-only — no edit/delete endpoints exist. A viewer shows entries with role-filtered visibility: Bookies see their own + booking-related entries; Admins see everything. As later slices add actions, they hook into the same logging mechanism.

## Acceptance criteria

- [ ] `activity_logs` table/model: actor_id, action, target_type, target_id, note, created_at (UTC).
- [ ] A logging helper records entries; existing actions (auth, invites) emit logs.
- [ ] No API path can edit or delete log entries (verified by absence + test).
- [ ] Viewer endpoint returns role-filtered entries (bookie: own + booking-related; admin: all).
- [ ] React activity-log views for admin (all) and bookie (own).
- [ ] Tests cover append-only behavior and role-filtered visibility.

## Blocked by

- #2 Login & session
