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

    return app


app = create_app()
