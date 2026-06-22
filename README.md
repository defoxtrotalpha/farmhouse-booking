# Farmhouse Booking

A private, invite-only web application for managing farmhouse / event-venue bookings. Authorized agents ("Bookies") request specific time slots on a shared calendar; Admins referee competing requests and approve exactly one per slot, making confirmed double bookings impossible.

> **Status:** Planning / pre-implementation. The product spec lives in [issues/prd.md](issues/prd.md) and the work is sliced into tracer-bullet issues under [issues/](issues/).

## Key Concepts

- **Roles:** Admins (manage bookies, farmhouses, settings; approve/reject/cancel) and Bookies (view calendar, hold slots, submit booking requests).
- **Competitive holds:** Many bookies may request the same slot. Holds and Pending requests do **not** reserve exclusively — only an approved **Booked** does.
- **Zero double bookings:** Enforced at the database level via a PostgreSQL range-exclusion constraint on confirmed bookings.
- **Booking lifecycle:** `Hold → Pending → Booked / Rejected`, plus `Canceled` and `Expired`.
- **Single business timezone:** All event times are Asia/Karachi; stored as UTC.

## Tech Stack

| Layer | Technology |
|-------|------------|
| Frontend | React (Vite) + FullCalendar |
| Backend | FastAPI (Python) + SQLAlchemy + Alembic |
| Database | PostgreSQL (`tstzrange` exclusion constraint) |
| Auth | JWT (access + refresh), bcrypt |
| Background jobs | APScheduler (in-process) |
| Email | SMTP provider (transactional) |
| Real-time | Short polling (no WebSockets) |
| Deployment | Docker Compose (portable) |

## Repository Structure

```
issues/                 Product spec (prd.md) and tracer-bullet implementation issues
backend/   (planned)    FastAPI app, models, migrations
frontend/  (planned)    React (Vite) app
docker-compose.yml (planned)
```

## Scope

In scope: multi-farmhouse booking, holds/approvals, notifications (in-app + email), activity log, reports/analytics with Excel/PDF export, settings & business rules, policies.

Out of scope: online payments, SMS/WhatsApp, multi-language UI, client self-service portal, chatbot, dynamic pricing.

## Getting Started

Implementation has not started yet. See [issues/01-walking-skeleton.md](issues/01-walking-skeleton.md) for the first slice (Docker Compose + FastAPI + React skeleton).
