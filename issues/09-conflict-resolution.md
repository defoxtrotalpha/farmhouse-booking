# Conflict resolution: auto-detect & reject overlapping pendings

**Type:** AFK
**Source:** [issues/prd.md](prd.md)

## What to build

Complete the competitive-hold workflow. When an Admin approves one request for a slot, the system detects all other Pending (and Hold) requests whose range overlaps the same farmhouse window and prompts the Admin to reject the losers with a reason (e.g., "slot taken"), then notifies the affected bookies. No request is left permanently un-actionable (dangling pending that can never be approved).

## Acceptance criteria

- [ ] On approval, the system returns the set of overlapping pending/hold requests for the same farmhouse+range.
- [ ] Admin is prompted to reject the overlapping losers (with reason); confirming transitions them to `rejected`.
- [ ] Rejected bookies are notified (hook into the notification slice when present; otherwise record the intent).
- [ ] Rejecting frees those requests' claim; the approved Booked remains.
- [ ] Edge case handled: approving a request whose slot was just Booked elsewhere returns a conflict and offers to reject the now-conflicting request.
- [ ] Tests cover overlap detection, batch rejection, and the just-booked-elsewhere edge case.

## Blocked by

- #23 Approve → Booked + overlap exclusion constraint
