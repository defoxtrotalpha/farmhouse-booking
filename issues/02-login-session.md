# Login & session (seeded admin)

**Type:** AFK
**Source:** [issues/prd.md](prd.md)

## What to build

End-to-end authentication for an existing user. A seeded Admin account can log in from the React login page; the backend issues JWT access + refresh tokens (passwords bcrypt-hashed), the SPA stores them and refreshes transparently, and a protected `/me` route returns the current user only when authenticated. Role information (admin/bookie) is carried in the token and enforced server-side, establishing the guard pattern all later slices reuse.

## Acceptance criteria

- [ ] A seed mechanism creates an initial Admin user with a bcrypt-hashed password.
- [ ] Login endpoint validates credentials and returns access + refresh tokens; invalid credentials return 401.
- [ ] Refresh endpoint exchanges a valid refresh token for a new access token.
- [ ] A protected `/me` endpoint returns the current user; unauthenticated requests are rejected.
- [ ] React login page authenticates, stores tokens, redirects to an authenticated shell, and auto-refreshes on expiry.
- [ ] Server-side role guard helper exists and is unit-tested (admin vs bookie).
- [ ] Disabled users cannot authenticate (403).
- [ ] Tests cover login success/failure, refresh, and guard enforcement.

## Blocked by

- #1 Walking skeleton
