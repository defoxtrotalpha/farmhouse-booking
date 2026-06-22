# PRD: Private Farmhouse Booking Management Web App

## Status
Draft

## Problem Statement
A small farmhouse/event-venue operation coordinates bookings across a handful of locations through a trusted set of agents ("Bookies") and one or more Admins. Today there is no shared source of truth: availability is tracked informally (calls, messages, spreadsheets), which leads to double bookings, lost requests, no audit trail, and slow approvals. This tool gives ~20 authorized Bookies and multiple Admins a single, invite-only, responsive web app where Bookies request specific time slots and Admins approve exactly one request per slot — making confirmed double bookings physically impossible at the database level while preserving a competitive, admin-refereed request flow.

## Goals
- Zero confirmed double bookings (enforced by a PostgreSQL exclusion constraint on `Booked` status).
- Multi-farmhouse, arbitrary start/end time event bookings (can span midnight/days), all in Asia/Karachi time.
- Full booking lifecycle: Hold → Pending → Booked / Rejected, plus Canceled and Expired.
- Real-time-enough coordination via polling (no WebSockets), in-app notification center + email for critical events.
- Complete, immutable audit trail of all state-changing actions.
- Reports/analytics with Excel/PDF export.
- Invite-only access with role-based permissions (Admin, Bookie); deployable anywhere via Docker Compose.

## Non-Goals
- Real payment processing / online payments (pricing is an informational `quoted_price` only).
- WebSockets / true server push (polling is used instead).
- Redis caching and Celery task queue (in-process APScheduler is used for cleanup).
- SMS / WhatsApp notifications.
- Multi-language (i18n) UI.
- Section 18 future possibilities: client self-service portal, chatbot, dynamic pricing engine.
- Automated disaster recovery tooling (standard managed/host backups only).
- Per-user and per-farmhouse timezones (single fixed business timezone: Asia/Karachi).
- Public/unauthenticated access of any kind.

## User Stories
- As an **Admin**, I want to invite Bookies by email so that only authorized agents can access the system.
- As an **Admin**, I want to review competing requests for a time slot and approve exactly one so that the venue is never double-booked.
- As an **Admin**, I want overlapping pending requests to be flagged and auto-rejected on approval so that no request is left permanently un-actionable.
- As an **Admin**, I want to manage farmhouses, business rules, blackout dates, and policies so that the system reflects real operating constraints.
- As an **Admin**, I want reports and Excel/PDF exports so that I can track occupancy, bookie performance, and trends.
- As a **Bookie**, I want to view a shared multi-farmhouse calendar so that I can see availability in venue-local time.
- As a **Bookie**, I want to place a hold on an arbitrary time slot and submit client details for approval so that I can secure an event for my client.
- As a **Bookie**, I want to cancel/withdraw my own holds and pending requests, and request cancellation of my booked events, so that I can manage my pipeline.
- As **any user**, I want in-app and email notifications for key events so that I stay coordinated in real time.
- As **any user**, I want an audit log so that system history is traceable.

## Functional Requirements

### Authentication & User Management
- FR-1: Admin invites a Bookie by name + email; the system emails a one-time, expiring set-password link. No admin-chosen passwords.
- FR-2: Passwords are bcrypt-hashed; auth uses JWT access + refresh tokens.
- FR-3: Self-service password reset via expiring email token.
- FR-4: Multiple Admins are supported; Admins can also act as Bookies (place holds/submit bookings).
- FR-5: Admin can disable or remove a Bookie; disabled users cannot authenticate.
- FR-6: Role-based access control enforced server-side on every endpoint (Admin vs Bookie).

### Farmhouses & Configuration
- FR-7: Admin can create/edit/disable farmhouses (name, description, capacity, `buffer_minutes` default 0, optional operating hours).
- FR-8: Admin manages blackout dates/holidays (per-farmhouse or global) marking dates unavailable.
- FR-9: Admin manages system settings: hold duration (default 24h), minimum advance notice (default off), buffer defaults, operating hours.
- FR-10: Admin manages Policies/Terms (titled, versioned, editable text).

### Calendar & Availability
- FR-11: Shared calendar (FullCalendar time-grid, day/week views) with a farmhouse selector showing one farmhouse at a time.
- FR-12: Calendar renders Hold, Pending, Booked, (and reflects Canceled/Rejected/Expired removal) with distinct colors, all in Asia/Karachi time.
- FR-13: Availability endpoint returns occupied vs free ranges for a farmhouse over a queried window.
- FR-14: Calendar and notification data refresh via short polling (configurable interval).

### Booking Lifecycle (Core Engine)
- FR-15: A booking occupies an arbitrary `start_at`→`end_at` timestamp range; it may cross midnight / span multiple days.
- FR-16: **Soft, competitive holds** — multiple Bookies may place overlapping Holds and submit overlapping Pending requests for the same slot. Holds/Pendings do NOT exclusively reserve.
- FR-17: A Bookie places a **Hold** (intent) on a slot; holds not yet submitted auto-expire after the configured duration (`expires_at`).
- FR-18: A Bookie **submits** a Hold to **Pending** by attaching booking details (client name, contact, event type/info, notes, optional `quoted_price`); Pending requests do not auto-expire.
- FR-19: An Admin **approves** one request → status becomes **Booked**; this is the only status with exclusive reservation.
- FR-20: On approval, the system **auto-detects overlapping Pending/Hold requests** for that farmhouse+range and prompts the Admin to reject them (with reason), notifying affected Bookies.
- FR-21: An Admin **rejects** a request (with reason) → slot freed for that request; the Bookie is notified.
- FR-22: Confirmed overlap is impossible: a PostgreSQL `EXCLUDE USING gist` constraint over `tstzrange(start_at - buffer, end_at + buffer)` per farmhouse, applied only `WHERE status = 'booked'`, rejects a second conflicting Booked.
- FR-23: Only future-dated bookings are allowed; minimum advance notice enforced if configured.
- FR-24: Buffer/turnover minutes (per farmhouse, snapshotted onto the booking) pad the occupied range for overlap calculation.

### Cancellation
- FR-25: Admin can cancel any Pending or Booked booking at any time with a reason; the slot is freed.
- FR-26: Bookie can cancel/withdraw their own Hold or Pending at any time.
- FR-27: Bookie can request cancellation of their own Booked event; Admin confirms to finalize.

### Notifications
- FR-28: In-app notification center (bell + list, polled) for all events: hold placed/requested, booking request received/submitted, approved/confirmed, rejected, canceled, upcoming-booking reminders.
- FR-29: Email is sent for critical events — invite, password reset, booking request received, hold requested, booking approved/confirmed, booking rejected — to **all Admins** and the **relevant Bookie**.
- FR-30: Email delivered via a configurable SMTP provider (e.g., SES / SendGrid / Resend).

### Activity Log / Audit
- FR-31: Append-only, immutable log of all state-changing actions (login, invite, hold created, request submitted, approved, rejected, canceled, farmhouse/settings/policy changes).
- FR-32: Each entry records actor, action, target type/id, UTC timestamp, optional note.
- FR-33: Visibility is role-filtered: Bookies see their own + booking-related entries; Admins see everything. No edits/deletes.

### Reports & Analytics
- FR-34: Reports for monthly/yearly bookings, occupancy tracking, bookie performance, and booking trends.
- FR-35: Search and filtering across bookings (by farmhouse, status, date range, bookie, client).
- FR-36: Export of reports/booking lists to Excel (.xlsx) and PDF.

## Non-Functional Requirements
- Performance: Calendar/availability queries return < 300ms at p95 for the expected scale (~10 farmhouses, ~20 bookies, < 500 bookings/month); polling interval tuned to avoid load.
- Security: All endpoints authenticated (JWT) and role-guarded; bcrypt password hashing; one-time expiring invite/reset tokens; no payment/PCI data; input validation on all write paths.
- Usability: Responsive design working on both mobile and desktop; all times shown in Asia/Karachi.
- Reliability: Confirmed double bookings impossible (DB-enforced); hold expiry is lazy so correctness never depends on a timer running on schedule.
- Scalability: Stateless API (horizontally scalable behind a load balancer); single PostgreSQL instance sufficient for target scale.
- Availability: Cloud-deployable; portable via Docker Compose (PostgreSQL + API + web).
- Auditability: Immutable, append-only activity log for full traceability.

## Technical Design

### Architecture
```
[Browser (mobile/desktop)]
        ↓ HTTPS (polling)
[React (Vite) + FullCalendar]  ── static build served by nginx
        ↓ REST (JSON, JWT)
[FastAPI + SQLAlchemy + Alembic]  ── APScheduler (in-process hold cleanup)
        ↓
[PostgreSQL]  ── tstzrange EXCLUDE constraint on Booked
        ↘ SMTP provider (transactional email)
```

### Modules Affected
| Module | Change Type | Notes |
|--------|-------------|-------|
| `infra/docker-compose` | New | postgres + api + web (nginx) services; portable deploy |
| `backend/app/main` | New | FastAPI app bootstrap, CORS, router registration, APScheduler startup |
| `backend/app/db` | New | SQLAlchemy engine/session, Alembic migrations |
| `backend/app/models` | New | users, auth_tokens, farmhouses, bookings, blackout_dates, settings, notifications, activity_logs, policies |
| `backend/app/auth` | New | JWT issue/verify, bcrypt, invite/reset token flows, role guards, multi-admin |
| `backend/app/routers/users` | New | Admin: list/invite/disable/delete bookies |
| `backend/app/routers/farmhouses` | New | CRUD (admin write, bookie read) |
| `backend/app/routers/availability` | New | Free/occupied ranges per farmhouse+window |
| `backend/app/routers/bookings` | New | Hold, submit→pending, approve, reject, cancel, withdraw; overlap auto-detect |
| `backend/app/routers/notifications` | New | List + mark-read (in-app center) |
| `backend/app/routers/activity_logs` | New | Role-filtered, read-only |
| `backend/app/routers/settings` | New | Admin get/update business rules |
| `backend/app/routers/blackouts` | New | Admin CRUD |
| `backend/app/routers/reports` | New | Occupancy, bookie performance, trends; xlsx/pdf export |
| `backend/app/routers/policies` | New | Read all; admin write |
| `backend/app/services/email` | New | SMTP transactional email for critical events |
| `backend/app/services/scheduler` | New | APScheduler job: lazy-expire/cleanup abandoned holds |
| `frontend/src/auth` | New | Login, set-password, reset, token storage/refresh, route guards |
| `frontend/src/pages/Calendar` | New | FullCalendar time-grid + farmhouse selector + status colors |
| `frontend/src/pages/Booking` | New | Create/hold/submit modal + detail view |
| `frontend/src/pages/admin/*` | New | Approval queue, bookies, farmhouses, settings, blackouts, policies, reports, audit |
| `frontend/src/pages/bookie/*` | New | My bookings, own activity log |
| `frontend/src/lib/api` | New | Typed REST client + polling hooks |

### Data Model Changes
New PostgreSQL schema (greenfield):
- `users(id, name, email UNIQUE, password_hash, role[admin|bookie], status[invited|active|disabled], created_at)`
- `auth_tokens(id, user_id FK, type[invite|reset], token_hash, expires_at, used_at)`
- `farmhouses(id, name, description, capacity, buffer_minutes DEFAULT 0, operating_hours jsonb NULL, status, created_at)`
- `bookings(id, farmhouse_id FK, created_by FK, client_name, client_contact, event_type, notes, start_at timestamptz, end_at timestamptz, buffer_minutes_snapshot, status[hold|pending|booked|rejected|canceled|expired], quoted_price numeric NULL, expires_at NULL, approved_by NULL, approved_at NULL, reject_reason NULL, cancel_reason NULL, created_at, updated_at)`
  - Occupied range = `tstzrange(start_at - (buffer_minutes_snapshot * interval), end_at + (buffer_minutes_snapshot * interval))`
  - `EXCLUDE USING gist (farmhouse_id WITH =, occupied WITH &&) WHERE (status = 'booked')` (requires `btree_gist`)
- `blackout_dates(id, farmhouse_id NULL=global, start_date, end_date, reason)`
- `settings(singleton: hold_duration_hours, min_advance_notice_minutes, ...)`
- `notifications(id, user_id FK, type, payload jsonb, read_at, created_at)`
- `activity_logs(id, actor_id FK, action, target_type, target_id, note, created_at)` — append-only
- `policies(id, title, body, version, updated_at)`

Migration concerns: greenfield, so all created via initial Alembic migration. Requires enabling `btree_gist` extension before the exclusion constraint.

### API Changes
New REST surface (JSON, JWT-protected unless noted):
- `/auth`: `POST login`, `POST refresh`, `POST accept-invite`, `POST set-password`, `POST forgot-password`, `POST reset-password`, `GET me`
- `/users` [admin]: `GET`, `POST invite`, `PATCH {id}/disable`, `DELETE {id}`
- `/farmhouses`: `GET`, `GET {id}`; [admin] `POST`, `PATCH {id}`, `DELETE {id}`
- `/availability`: `GET ?farmhouse_id&from&to`
- `/bookings`: `GET (filters)`, `POST hold`, `POST {id}/submit`, `POST {id}/approve`, `POST {id}/reject`, `POST {id}/cancel`, `POST {id}/withdraw`
- `/notifications`: `GET`, `POST {id}/read`
- `/activity-logs`: `GET (role-filtered)`
- `/settings` [admin]: `GET`, `PUT`
- `/blackouts` [admin]: `GET`, `POST`, `PATCH {id}`, `DELETE {id}`
- `/reports`: `GET occupancy`, `GET bookie-performance`, `GET trends`, `GET export?format=xlsx|pdf`
- `/policies`: `GET`; [admin] `POST`, `PATCH {id}`

### Key Implementation Decisions
| Decision | Choice | Rationale |
|----------|--------|-----------|
| Database | PostgreSQL (not MySQL) | Native `tstzrange` + `EXCLUDE USING gist` makes confirmed double-booking physically impossible |
| Concurrency model | Soft competitive holds; exclusion only on `Booked` | Matches "many requests per slot, admin approves one" business reality |
| Conflict resolution | Auto-detect overlapping pendings on approval; prompt admin to reject | Prevents dangling, un-actionable requests |
| Hold expiry | Lazy (`expires_at` ignored on read) + APScheduler cleanup | Correctness independent of timer; no Celery/Redis needed |
| Real-time | Short polling for calendar + notifications | Sufficient for scale; avoids WebSocket complexity |
| Auth | JWT access+refresh, bcrypt, email invite/reset | Clean SPA + FastAPI fit; no admin-chosen passwords |
| Timezone | Store UTC (`timestamptz`), display/input Asia/Karachi | Single-location business; avoids per-user TZ complexity |
| Calendar UI | FullCalendar free time-grid + farmhouse selector | Day/week time slots out of the box; avoids paid resource view |
| Pricing | Informational `quoted_price` only | No payments → no PCI/gateway complexity |
| Deployment | Docker Compose (postgres + api + web) | Cloud-portable, deploy anywhere |
| Background jobs | In-process APScheduler | Only need lightweight hold cleanup |

## Edge Cases & Error Handling
- Two Admins approve overlapping Pendings near-simultaneously: DB exclusion constraint rejects the second `Booked`; API returns a 409 conflict and surfaces a clear "slot just booked" message; the losing request remains Pending for the Admin to reject.
- Bookie submits details for a Hold that already expired: server re-validates; if expired, prompts re-hold or shows current availability.
- Approving a request whose slot was Booked by another path: 409 with auto-suggest to reject the now-conflicting request.
- Booking crossing midnight / spanning days: stored as a single `tstzrange`; calendar renders across day boundaries.
- Buffer collisions: occupied range padded by `buffer_minutes_snapshot`; back-to-back bookings within buffer are rejected.
- Blackout date overlaps requested range: submission blocked with a "venue unavailable on these dates" message.
- Past-dated or below-minimum-advance-notice request: rejected with a validation message.
- Expired or reused invite/reset token: rejected with "link expired — request a new one."
- Disabled Bookie attempts login: 403 with "account disabled."
- Email provider failure: action still succeeds (in-app notification persists); email send is retried/logged and surfaced as a non-blocking warning.
- Concurrent cancellation + approval of the same booking: last-write guarded by status checks; stale action returns a conflict.

## Testing Plan
- Unit:
  - Booking state-machine transitions (Hold→Pending→Booked/Rejected, Canceled, Expired) and illegal-transition rejection.
  - Overlap/occupied-range computation including buffer and midnight-spanning ranges.
  - Token issuance/expiry (invite, reset), JWT verify, role guards.
  - Hold lazy-expiry logic and cleanup job behavior.
- Integration:
  - Exclusion constraint blocks a second `Booked` for an overlapping range; allows non-overlapping.
  - Approval auto-detects and rejects overlapping Pendings, emits notifications/emails.
  - Availability endpoint returns correct free/occupied sets.
  - Email service invoked for each critical event to all admins + relevant bookie.
  - Role-filtered activity-log visibility.
- E2E (critical journeys):
  - Admin invites → Bookie sets password → logs in.
  - Bookie holds → submits details → Admin approves → calendar shows Booked → notifications/emails delivered.
  - Two Bookies request the same slot → Admin approves one → other auto-rejected.
  - Cancellation frees the slot and re-opens availability.
- Acceptance Criteria:
  - [ ] No two `Booked` bookings can overlap for the same farmhouse (DB-enforced; proven by parallel stress test).
  - [ ] Invite-only access: unauthenticated/non-invited users cannot reach any data.
  - [ ] Approving one of several overlapping requests auto-prompts rejection of the rest, and they are notified.
  - [ ] All times display in Asia/Karachi regardless of device.
  - [ ] Critical events generate in-app notifications and emails to all admins + the relevant bookie.
  - [ ] Activity log is append-only and role-filtered (verified no edit/delete endpoints exist).
  - [ ] Reports export valid `.xlsx` and `.pdf`.
  - [ ] `alembic upgrade head` runs clean and `docker compose up` brings up the full stack.
  - [ ] UI is usable on both mobile and desktop viewports.

## Open Questions
- [ ] Email provider selection (Resend vs AWS SES vs SendGrid) — owner: project owner.
- [ ] Whether Admins should appear as assignable Bookies in the booking creation UI by default — owner: project owner.
- [ ] Exact polling interval(s) for calendar vs notifications — to be tuned during P4/P5.
- [ ] Reminder lead time(s) for "upcoming booking" notifications — owner: project owner.

## References
- Source spec: original "Private Farmhouse Booking Management" requirements (Sections 1–18).
- Grill-me session decisions: captured in session memory (`/memories/session/plan.md`).
- Build phases P0–P7 (foundation → auth → farmhouses/settings → booking engine → calendar → notifications/audit → reports → polish).
