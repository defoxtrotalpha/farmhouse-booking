# Cancellation & withdraw

**Type:** AFK
**Source:** [issues/prd.md](prd.md)

## What to build

The cancellation paths end-to-end. An Admin can cancel any Pending or Booked booking at any time with a reason, freeing the slot. A Bookie can cancel/withdraw their own Hold or Pending at any time, and can *request* cancellation of their own Booked event, which an Admin must confirm to finalize. All cancellations free the slot and are reflected on the calendar.

## Acceptance criteria

- [ ] Admin cancel endpoint cancels any pending/booked with a reason; slot becomes available.
- [ ] Bookie can cancel/withdraw their own hold or pending directly.
- [ ] Bookie can submit a cancellation request on their own booked event; status reflects "cancellation requested".
- [ ] Admin confirms a bookie's booked-cancellation request to finalize (`canceled`).
- [ ] Permission checks prevent bookies from canceling others' bookings (403).
- [ ] Canceling frees the slot for new holds/bookings and updates the calendar.
- [ ] Tests cover each path and permission boundaries.

## Blocked by

- #24 Conflict resolution: auto-detect & reject overlapping pendings
