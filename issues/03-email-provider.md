# Email provider decision + transactional email service

**Type:** HITL
**Source:** [issues/prd.md](prd.md) (Open Question: email provider)

## What to build

Choose the transactional email provider (Resend vs AWS SES vs SendGrid) and wire a minimal sending service behind a single interface so the rest of the app depends on the abstraction, not the vendor. Deliver one tracer email (e.g., a test/diagnostic send) through the real provider. Until this lands, dependent slices may use a stub that logs the would-be email link instead of sending.

This is HITL because it requires a vendor/credentials decision by the project owner.

## Acceptance criteria

- [ ] Provider selected and documented, with credentials supplied via environment/secret config (never committed).
- [ ] A single email-sending interface exists; the chosen provider is one implementation, and a logging stub is another.
- [ ] One real email sends successfully through the provider in a non-production environment.
- [ ] Email send failures are non-blocking to the caller and are logged.
- [ ] Configuration documents how to swap providers without changing callers.

## Blocked by

- #1 Walking skeleton
