"""FastAPI application entrypoint."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import health
from app.routers import auth
from app.routers import farmhouse
from app.routers import invite
from app.routers import activity
from app.routers import policy
from app.routers import availability
from app.routers import booking

settings = get_settings()

# Idempotency guard — prevents starting a second scheduler if create_app() is
# called more than once (e.g. in test helpers that build isolated apps).
_scheduler_started = False


def _start_hold_scheduler(s) -> None:  # pragma: no cover
    """Start the APScheduler background job that sweeps stale holds.

    Opens its own DB session (not shared with request handlers) and closes it
    after each run.  Only called when settings.enable_hold_scheduler is True.
    """
    from apscheduler.schedulers.background import BackgroundScheduler
    from app.db import SessionLocal
    from app.services.hold_expiry import expire_stale_holds

    def _job() -> None:
        db = SessionLocal()
        try:
            expire_stale_holds(db)
        finally:
            db.close()

    scheduler = BackgroundScheduler()
    scheduler.add_job(_job, "interval", minutes=s.hold_sweep_minutes)
    scheduler.start()


def create_app() -> FastAPI:
    app = FastAPI(title="Farmhouse Booking API", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(farmhouse.router)
    app.include_router(invite.router)
    app.include_router(activity.router)
    app.include_router(policy.router)
    app.include_router(availability.router)
    app.include_router(booking.router)

    # Start the hold-expiry sweep scheduler only in production deployments.
    # Gated by settings.enable_hold_scheduler so the test suite (which sets
    # ENABLE_HOLD_SCHEDULER=false before importing the app) never spins up a
    # background thread.
    global _scheduler_started
    if settings.enable_hold_scheduler and not _scheduler_started:
        _start_hold_scheduler(settings)  # pragma: no cover
        _scheduler_started = True  # pragma: no cover

    return app


app = create_app()
