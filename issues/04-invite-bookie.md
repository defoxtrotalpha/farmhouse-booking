# Invite a Bookie (email invite → set password → login)

**Type:** AFK
**Source:** [issues/prd.md](prd.md)

## What to build

The full onboarding path for a new Bookie. An Admin invites a Bookie by name + email; the system creates an `invited` user and emails a one-time, expiring set-password link. The Bookie opens the link, sets a password, the account becomes `active`, and they can log in as a bookie. Reuse the email service (real provider when available, logged-link stub otherwise).

## Acceptance criteria

- [ ] Admin-only invite endpoint creates an `invited` user and issues a single-use, expiring invite token.
- [ ] Invite email (or stubbed logged link) contains the set-password URL.
- [ ] Set-password endpoint validates the token, sets a bcrypt password, activates the user, and invalidates the token.
- [ ] Expired or reused tokens are rejected with a clear message.
- [ ] React pages exist for invite (admin) and set-password (invitee).
- [ ] Newly activated Bookie can log in and is scoped to the bookie role.
- [ ] Tests cover invite creation, token validation/expiry/reuse, and activation.

## Blocked by

- #17 Login & session
- #18 Email provider decision
