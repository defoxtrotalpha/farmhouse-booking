# Notifications (in-app center + critical emails)

**Type:** AFK
**Source:** [issues/prd.md](prd.md)

## What to build

Keep everyone coordinated. An in-app notification center (bell + list, polled like the calendar) surfaces all events: hold placed/requested, booking request received/submitted, approved/confirmed, rejected, canceled, and upcoming-booking reminders. For **critical** events — invite, password reset, booking request received, hold requested, booking approved/confirmed, booking rejected — email is also sent to **all Admins** and the **relevant Bookie**, via the email service. Email failures are non-blocking; the in-app notification still persists.

## Acceptance criteria

- [ ] `notifications` table/model with recipient, type, payload, read state, timestamp.
- [ ] Booking lifecycle events generate in-app notifications for the correct recipients (all admins + relevant bookie where applicable).
- [ ] In-app notification center UI lists notifications, shows unread count, and marks as read (polled).
- [ ] Critical events additionally send email through the email service to all admins + relevant bookie.
- [ ] Email send failure does not block the action and is logged; in-app notification still recorded.
- [ ] Upcoming-booking reminder notifications are generated.
- [ ] Tests cover recipient fan-out, critical-vs-non-critical routing, and read state.

## Blocked by

- #9 Conflict resolution: auto-detect & reject overlapping pendings
- #3 Email provider decision
