# Policies / Terms management

**Type:** AFK
**Source:** [issues/prd.md](prd.md)

## What to build

Admins manage policy/terms content shown in the app. Each policy has a title, body, and version; Admins create and edit policies (producing new versions), and all authenticated users can read the current policies.

## Acceptance criteria

- [ ] `policies` model: title, body, version, updated_at.
- [ ] Admin-only create/edit endpoints; editing produces an updated version.
- [ ] All authenticated users can read current policies.
- [ ] React UI: admin editor and a read view for all users.
- [ ] Role guard prevents bookies from editing policies (403).
- [ ] Tests cover versioning and role enforcement.

## Blocked by

- #17 Login & session
