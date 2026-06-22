# Farmhouse Booking

A private, invite-only web application for managing farmhouse / event-venue bookings. Authorized agents ("Bookies") request specific time slots on a shared calendar; Admins referee competing requests and approve exactly one per slot, making confirmed double bookings impossible.

> **Status:** v1 implemented. The product spec lives in [issues/prd.md](issues/prd.md) and the work was sliced into tracer-bullet issues under [issues/](issues/).

## Key Concepts

- **Roles:** Admins (manage bookies, farmhouses, settings; approve/reject/cancel) and Bookies (view calendar, hold slots, submit booking requests).
- **Competitive holds:** Many bookies may request the same slot. Holds and Pending requests do **not** reserve exclusively — only an approved **Booked** does.
- **Zero double bookings:** Enforced in the application layer — an overlap check guarded by a process-wide lock at approval time ensures only one `Booked` row can exist per overlapping slot (v1 uses SQLite, which has no range-exclusion constraint).
- **Booking lifecycle:** `Hold → Pending → Booked / Rejected`, plus `Canceled` and `Expired`.
- **Single business timezone:** All event times are Asia/Karachi; stored as UTC.

## Tech Stack

| Layer | Technology |
|-------|------------|
| Frontend | React (Vite) + FullCalendar |
| Backend | FastAPI (Python) + SQLAlchemy + Alembic |
| Database | SQLite (v1, local file `booking.db`) |
| Auth | JWT (access + refresh), bcrypt |
| Background jobs | APScheduler (in-process) |
| Email | Logging stub (v1) — links written to the app log |
| Real-time | Short polling (no WebSockets) |
| Deployment | Local (uvicorn + Vite); no Docker in v1 |

## Repository Structure

```
issues/      Product spec (prd.md) and tracer-bullet implementation issues
backend/     FastAPI app, models, services, routers, Alembic migrations, tests
frontend/    React (Vite) app
```

## Scope

In scope: multi-farmhouse booking, holds/approvals, notifications (in-app + email), activity log, reports/analytics with Excel/PDF export, settings & business rules, policies.

Out of scope: online payments, SMS/WhatsApp, multi-language UI, client self-service portal, chatbot, dynamic pricing.

## Getting Started

### Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
alembic upgrade head        # create / migrate booking.db (SQLite)
uvicorn app.main:app --reload
```

The API is served at http://localhost:8000 (docs at `/docs`).

### Frontend

```powershell
cd frontend
npm install
npm run dev                 # Vite dev server, proxies /api -> localhost:8000
```

### Tests

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q
```

## v1 Deviations & Operational Notes

- **Database:** v1 uses a local **SQLite** file (`booking.db`) instead of PostgreSQL. Because SQLite has no range-exclusion constraint, no-double-booking is enforced in the application layer (overlap check inside a `threading.Lock` at approval time).
- **Email:** v1 ships a logging email stub — invite and password-reset links are written to the application log rather than sent over SMTP.
- **Deployment:** No Docker in v1; run the backend (uvicorn) and frontend (Vite) directly as shown above.
- **Polling intervals** (short-polling, no WebSockets):
  - Calendar availability refresh: **15 s** (`POLL_INTERVAL_MS` in `frontend/src/CalendarPage.jsx`).
  - Notification unread-count: **30 s** (`POLL_MS` in `frontend/src/NotificationBell.jsx`).
- **Background jobs** (APScheduler, gated on `ENABLE_HOLD_SCHEDULER`): hold-expiry sweep and a 1-hour upcoming-booking reminder job.
- **Timezone:** all event times are Asia/Karachi (UTC+5), stored as UTC.
- **Secrets:** JWT secret and other config come from environment / `app/config.py`; no secrets are committed. Invite and reset tokens are single-use and expire.
