# Hold expiry (lazy + APScheduler cleanup)

**Type:** AFK
**Source:** [issues/prd.md](prd.md)

## What to build

Abandoned holds (placed but never submitted to Pending) expire automatically. Expiry is **lazy**: a hold carries `expires_at`, and any read/availability query treats an expired hold as gone, so correctness never depends on a timer running on schedule. A lightweight in-process APScheduler job periodically marks/cleans expired holds to keep data tidy. Hold duration is configurable (default 24h).

## Acceptance criteria

- [ ] Holds are created with `expires_at` derived from the configurable hold duration (default 24h).
- [ ] Availability and listing queries exclude expired holds (treated as `expired`/gone) regardless of cleanup timing.
- [ ] An in-process APScheduler job runs on a schedule to mark/clean expired holds.
- [ ] Submitting a hold to Pending clears/ignores expiry (pendings never auto-expire).
- [ ] Attempting to submit an already-expired hold is handled gracefully (prompt to re-hold).
- [ ] Tests cover lazy exclusion of expired holds and the cleanup job.

## Blocked by

- #22 Hold a slot → submit Pending
