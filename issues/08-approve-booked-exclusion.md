# Approve → Booked + overlap exclusion constraint (happy path)

**Type:** HITL
**Source:** [issues/prd.md](prd.md)

## What to build

The core correctness slice. An Admin approves a Pending request and it becomes **Booked** — the only status that exclusively reserves a slot. Confirmed double-booking is made physically impossible by a PostgreSQL range-exclusion constraint: per farmhouse, the padded occupied range cannot overlap another `Booked` row. A second approval that would overlap an existing Booked is rejected at the database level and surfaced as a clear conflict to the Admin.

This is HITL: review the DB migration (exclusion constraint + `btree_gist`), the occupied-range definition with buffer, and the concurrency behavior before implementation. (Conflict auto-rejection of the *losing* pendings is the next slice, #9.)

Decision-encoding detail (from design):
- Occupied range = `tstzrange(start_at - buffer, end_at + buffer)` using a per-booking buffer snapshot.
- Constraint: `EXCLUDE USING gist (farmhouse_id WITH =, occupied WITH &&) WHERE (status = 'booked')`; requires the `btree_gist` extension.

## Acceptance criteria

- [ ] Migration enables `btree_gist` and adds the partial exclusion constraint scoped to `status = 'booked'`.
- [ ] Approve endpoint transitions `pending → booked` and records approver + timestamp.
- [ ] A second approval overlapping an existing Booked range (same farmhouse) is rejected; API returns a 409 conflict with a clear message.
- [ ] Buffer minutes pad the occupied range so back-to-back-within-buffer bookings conflict.
- [ ] Non-overlapping bookings for the same farmhouse are allowed.
- [ ] React admin approval action reflects success and conflict states.
- [ ] A concurrency/stress test approves two overlapping pendings in parallel and asserts exactly one Booked.

## Blocked by

- #7 Hold a slot → submit Pending
