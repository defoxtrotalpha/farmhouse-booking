# Hold a slot → submit Pending

**Type:** AFK
**Source:** [issues/prd.md](prd.md)

## What to build

The Bookie request path through to Pending. A Bookie selects an arbitrary start→end time range on the calendar for a farmhouse and places a **Hold** (intent). They then attach booking details (client name, contact, event type/info, notes, optional quoted_price) to submit the Hold as **Pending**, awaiting admin approval. Holds and Pendings are **soft/competitive** — multiple bookies may create overlapping holds/pendings for the same slot; nothing is exclusively reserved yet (exclusivity arrives in the approval slice).

State machine (from design): `Hold → Pending` (Booked/Rejected handled in later slices). Holds carry `expires_at`; Pendings do not auto-expire.

## Acceptance criteria

- [ ] `bookings` table/model supports start_at/end_at (timestamptz), status, created_by, farmhouse_id, client fields, optional quoted_price, expires_at, buffer snapshot.
- [ ] Create-hold endpoint creates a `hold` for an arbitrary range (may cross midnight/span days) with future-date validation.
- [ ] Submit endpoint attaches details and transitions `hold → pending`.
- [ ] Overlapping holds/pendings from different bookies are permitted (no exclusivity at this stage).
- [ ] React flows: place hold from calendar, then a detail form to submit as pending.
- [ ] Holds and pendings appear on the calendar with distinct statuses.
- [ ] Tests cover hold creation, future-date rejection, hold→pending transition, and allowed overlap.

## Blocked by

- #6 Read-only calendar + availability
