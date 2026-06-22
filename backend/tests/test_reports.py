"""Reports & analytics — TDD vertical slice (#30).

TDD order:
  RED-1  : booking_counts groups by status correctly + total
  RED-2  : booking_counts ignores bookings outside date range
  RED-3  : monthly_breakdown buckets by LOCAL Asia/Karachi month (UTC/Karachi boundary)
  RED-4  : yearly_breakdown buckets by LOCAL Asia/Karachi year
  RED-5  : occupancy_percent math: 2h booked in 24h window == 8.3%
  RED-6  : occupancy partial-overlap booking clipped to window
  RED-7  : occupancy non-booked statuses excluded
  RED-8  : occupancy capped at 100 (two inserted booked bookings covering >window)
  RED-9  : occupancy farmhouse_id filter returns only requested farmhouse
  RED-10 : bookie_performance counts approved/rejected/canceled + approval_rate
  RED-11 : bookie_performance approval_rate null when no approved+rejected
  RED-12 : trends returns chronological buckets incl zeros (monthly granularity)
  RED-13 : search_bookings by status
  RED-14 : search_bookings by farmhouse_id
  RED-15 : search_bookings by date range (start/end)
  RED-16 : search_bookings by client_name case-insensitive substring
  RED-17 : search_bookings combined filters
  RED-18 : bookings_to_xlsx returns bytes starting with PK zip magic bytes
  RED-19 : bookings_to_pdf returns bytes starting with %PDF
  RED-20 : endpoint auth: bookie GET /api/reports/summary -> 403
  RED-21 : endpoint auth: admin GET /api/reports/summary -> 200
  RED-22 : GET /api/reports/export?report=bookings&format=xlsx -> 200 + xlsx content-type + PK bytes
  RED-23 : GET /api/reports/export?report=bookings&format=pdf -> 200 + pdf bytes
  RED-24 : GET /api/reports/export?report=bookings&format=bad -> 400
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


# ---------------------------------------------------------------------------
# Helpers: isolated in-memory SQLite DB + optional HTTP client
# ---------------------------------------------------------------------------

def _make_db():
    """Return (SessionFactory, bare_session) on a fresh in-memory SQLite."""
    from app.db import Base
    import app.models  # noqa — populates Base.metadata

    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng)
    TestSession = sessionmaker(bind=eng, autoflush=False, autocommit=False)
    return TestSession, TestSession()


def _make_client():
    """Fresh isolated in-memory SQLite TestClient for endpoint tests."""
    from app.db import Base, get_db
    from app.main import create_app
    import app.models  # noqa

    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng)
    TestSession = sessionmaker(bind=eng, autoflush=False, autocommit=False)

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    application = create_app()
    application.dependency_overrides[get_db] = override_get_db
    c = TestClient(application)
    c._TestSession = TestSession  # type: ignore[attr-defined]
    return c


def _T(y, mo, d, h, mi=0):
    """Shorthand: UTC-aware datetime."""
    return datetime(y, mo, d, h, mi, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------

def _seed_farmhouses(db):
    from app.models.farmhouse import Farmhouse
    f1 = Farmhouse(name="Villa Alpha", status="active", buffer_minutes=0)
    f2 = Farmhouse(name="Garden Bungalow", status="active", buffer_minutes=0)
    db.add_all([f1, f2])
    db.commit()
    db.refresh(f1)
    db.refresh(f2)
    return f1, f2


def _seed_users(db):
    from app.models.user import User
    from app.security import hash_password
    admin = User(email="admin@rep.test", name="Admin", password_hash=hash_password("p"),
                 role="admin", is_active=True)
    bk1 = User(email="bk1@rep.test", name="BookieOne", password_hash=hash_password("p"),
               role="bookie", is_active=True)
    bk2 = User(email="bk2@rep.test", name="BookieTwo", password_hash=hash_password("p"),
               role="bookie", is_active=True)
    db.add_all([admin, bk1, bk2])
    db.commit()
    for u in (admin, bk1, bk2):
        db.refresh(u)
    return admin, bk1, bk2


def _make_booking(db, *, farmhouse_id, bookie_id, status,
                  start_at, end_at=None, client_name=None):
    from app.models.booking import Booking
    if end_at is None:
        end_at = start_at + timedelta(hours=2)
    b = Booking(
        farmhouse_id=farmhouse_id,
        bookie_id=bookie_id,
        status=status,
        start_at=start_at,
        end_at=end_at,
        buffer_minutes_snapshot=0,
        client_name=client_name,
    )
    db.add(b)
    db.commit()
    db.refresh(b)
    return b


# ===========================================================================
# RED-1 : booking_counts groups by status correctly + total
# ===========================================================================

def test_booking_counts_groups_by_status():
    from app.services.reports import booking_counts
    _, db = _make_db()
    f1, _ = _seed_farmhouses(db)
    _, bk1, _ = _seed_users(db)

    _make_booking(db, farmhouse_id=f1.id, bookie_id=bk1.id, status="booked",   start_at=_T(2024, 1, 10, 8))
    _make_booking(db, farmhouse_id=f1.id, bookie_id=bk1.id, status="booked",   start_at=_T(2024, 1, 11, 8))
    _make_booking(db, farmhouse_id=f1.id, bookie_id=bk1.id, status="pending",  start_at=_T(2024, 1, 12, 8))
    _make_booking(db, farmhouse_id=f1.id, bookie_id=bk1.id, status="rejected", start_at=_T(2024, 1, 13, 8))
    _make_booking(db, farmhouse_id=f1.id, bookie_id=bk1.id, status="hold",     start_at=_T(2024, 1, 14, 8))

    result = booking_counts(db, start=_T(2024, 1, 1, 0), end=_T(2024, 2, 1, 0))

    assert result["booked"] == 2
    assert result["pending"] == 1
    assert result["rejected"] == 1
    assert result["hold"] == 1
    assert result["total"] == 5


# ===========================================================================
# RED-2 : booking_counts ignores bookings outside date range
# ===========================================================================

def test_booking_counts_excludes_out_of_range():
    from app.services.reports import booking_counts
    _, db = _make_db()
    f1, _ = _seed_farmhouses(db)
    _, bk1, _ = _seed_users(db)

    # Inside range
    _make_booking(db, farmhouse_id=f1.id, bookie_id=bk1.id, status="booked", start_at=_T(2024, 1, 15, 8))
    # Outside (before start)
    _make_booking(db, farmhouse_id=f1.id, bookie_id=bk1.id, status="booked", start_at=_T(2023, 12, 31, 8))
    # Outside (at end boundary — half-open, excluded)
    _make_booking(db, farmhouse_id=f1.id, bookie_id=bk1.id, status="booked", start_at=_T(2024, 2, 1, 0))

    result = booking_counts(db, start=_T(2024, 1, 1, 0), end=_T(2024, 2, 1, 0))

    assert result["total"] == 1
    assert result["booked"] == 1


# ===========================================================================
# RED-3 : monthly_breakdown buckets by LOCAL Asia/Karachi month
#         UTC/Karachi boundary proof: 2024-01-31 20:00 UTC = 2024-02-01 01:00 Karachi
# ===========================================================================

def test_monthly_breakdown_uses_karachi_local_month():
    from app.services.reports import monthly_breakdown
    _, db = _make_db()
    f1, _ = _seed_farmhouses(db)
    _, bk1, _ = _seed_users(db)

    # In UTC this is January, but in Karachi (UTC+5) it is February
    _make_booking(db, farmhouse_id=f1.id, bookie_id=bk1.id, status="booked",
                  start_at=_T(2024, 1, 31, 20))  # Karachi: 2024-02-01 01:00

    # Genuine January booking
    _make_booking(db, farmhouse_id=f1.id, bookie_id=bk1.id, status="pending",
                  start_at=_T(2024, 1, 15, 8))

    result = monthly_breakdown(db, start=_T(2024, 1, 1, 0), end=_T(2024, 3, 1, 0))

    # Jan should have 1 (the pending)
    jan = next((r for r in result if r["year"] == 2024 and r["month"] == 1), None)
    # Feb should have 1 (the boundary booking counted in local Feb)
    feb = next((r for r in result if r["year"] == 2024 and r["month"] == 2), None)

    assert jan is not None, f"No Jan bucket; result={result}"
    assert jan["total_count"] == 1
    assert jan["booked_count"] == 0  # it's pending

    assert feb is not None, f"No Feb bucket; result={result}"
    assert feb["total_count"] == 1
    assert feb["booked_count"] == 1  # it's booked, in local Feb


# ===========================================================================
# RED-4 : yearly_breakdown buckets by LOCAL Asia/Karachi year
# ===========================================================================

def test_yearly_breakdown_uses_karachi_local_year():
    from app.services.reports import yearly_breakdown
    _, db = _make_db()
    f1, _ = _seed_farmhouses(db)
    _, bk1, _ = _seed_users(db)

    # 2023-12-31 20:00 UTC = 2024-01-01 01:00 Karachi -> local year 2024
    _make_booking(db, farmhouse_id=f1.id, bookie_id=bk1.id, status="booked",
                  start_at=_T(2023, 12, 31, 20))

    # Genuine 2023 booking
    _make_booking(db, farmhouse_id=f1.id, bookie_id=bk1.id, status="booked",
                  start_at=_T(2023, 6, 15, 8))

    result = yearly_breakdown(db, start=_T(2023, 1, 1, 0), end=_T(2025, 1, 1, 0))

    y2023 = next((r for r in result if r["year"] == 2023), None)
    y2024 = next((r for r in result if r["year"] == 2024), None)

    assert y2023 is not None
    assert y2023["booked_count"] == 1  # June 2023 booking stays in 2023

    assert y2024 is not None
    assert y2024["booked_count"] == 1  # UTC Dec-31 20:00 rolls into Karachi 2024


# ===========================================================================
# RED-5 : occupancy_percent math: 2h booked in 24h window == 8.3%
# ===========================================================================

def test_occupancy_2h_in_24h_window():
    from app.services.reports import occupancy
    _, db = _make_db()
    f1, _ = _seed_farmhouses(db)
    _, bk1, _ = _seed_users(db)

    win_start = _T(2024, 3, 1, 0)
    win_end   = _T(2024, 3, 2, 0)   # 24h window

    _make_booking(db, farmhouse_id=f1.id, bookie_id=bk1.id, status="booked",
                  start_at=_T(2024, 3, 1, 8), end_at=_T(2024, 3, 1, 10))  # 2h

    result = occupancy(db, start=win_start, end=win_end, farmhouse_id=f1.id)

    assert len(result) == 1
    r = result[0]
    assert r["farmhouse_id"] == f1.id
    assert r["booked_seconds"] == 2 * 3600
    assert r["window_seconds"] == 24 * 3600
    assert r["occupancy_percent"] == round(2 / 24 * 100, 1)  # 8.3


# ===========================================================================
# RED-6 : occupancy partial-overlap booking clipped to window
# ===========================================================================

def test_occupancy_partial_overlap_clipped():
    from app.services.reports import occupancy
    _, db = _make_db()
    f1, _ = _seed_farmhouses(db)
    _, bk1, _ = _seed_users(db)

    win_start = _T(2024, 3, 1, 0)
    win_end   = _T(2024, 3, 2, 0)   # 24h

    # Starts 3h before window start, ends 1h into window -> 1h overlap
    _make_booking(db, farmhouse_id=f1.id, bookie_id=bk1.id, status="booked",
                  start_at=_T(2024, 2, 29, 21), end_at=_T(2024, 3, 1, 1))

    result = occupancy(db, start=win_start, end=win_end, farmhouse_id=f1.id)
    r = result[0]
    assert r["booked_seconds"] == 1 * 3600  # only the 1h inside the window


# ===========================================================================
# RED-7 : occupancy non-booked statuses excluded
# ===========================================================================

def test_occupancy_excludes_non_booked_statuses():
    from app.services.reports import occupancy
    _, db = _make_db()
    f1, _ = _seed_farmhouses(db)
    _, bk1, _ = _seed_users(db)

    win_start = _T(2024, 3, 1, 0)
    win_end   = _T(2024, 3, 2, 0)

    for st in ("pending", "hold", "rejected", "canceled", "expired"):
        _make_booking(db, farmhouse_id=f1.id, bookie_id=bk1.id, status=st,
                      start_at=_T(2024, 3, 1, 4), end_at=_T(2024, 3, 1, 6))

    result = occupancy(db, start=win_start, end=win_end, farmhouse_id=f1.id)
    r = result[0]
    assert r["booked_seconds"] == 0
    assert r["occupancy_percent"] == 0.0


# ===========================================================================
# RED-8 : occupancy capped at 100
# ===========================================================================

def test_occupancy_capped_at_100():
    """Insert two 20h booked bookings (directly bypassing business logic) covering
    nearly the entire 24h window each — total would be 40h > 24h. Must be capped."""
    from app.services.reports import occupancy
    _, db = _make_db()
    f1, _ = _seed_farmhouses(db)
    _, bk1, _ = _seed_users(db)

    win_start = _T(2024, 3, 1, 0)
    win_end   = _T(2024, 3, 2, 0)

    # Booking 1: 20h fully inside window
    _make_booking(db, farmhouse_id=f1.id, bookie_id=bk1.id, status="booked",
                  start_at=_T(2024, 3, 1, 0), end_at=_T(2024, 3, 1, 20))
    # Booking 2: another 20h fully inside window (overlaps — only possible via direct DB insert)
    _make_booking(db, farmhouse_id=f1.id, bookie_id=bk1.id, status="booked",
                  start_at=_T(2024, 3, 1, 2), end_at=_T(2024, 3, 1, 22))

    result = occupancy(db, start=win_start, end=win_end, farmhouse_id=f1.id)
    r = result[0]
    assert r["occupancy_percent"] == 100.0


# ===========================================================================
# RED-9 : occupancy farmhouse_id filter
# ===========================================================================

def test_occupancy_farmhouse_id_filter():
    from app.services.reports import occupancy
    _, db = _make_db()
    f1, f2 = _seed_farmhouses(db)
    _, bk1, _ = _seed_users(db)

    win_start = _T(2024, 3, 1, 0)
    win_end   = _T(2024, 3, 2, 0)

    _make_booking(db, farmhouse_id=f1.id, bookie_id=bk1.id, status="booked",
                  start_at=_T(2024, 3, 1, 8), end_at=_T(2024, 3, 1, 10))
    _make_booking(db, farmhouse_id=f2.id, bookie_id=bk1.id, status="booked",
                  start_at=_T(2024, 3, 1, 8), end_at=_T(2024, 3, 1, 10))

    result = occupancy(db, start=win_start, end=win_end, farmhouse_id=f1.id)
    assert len(result) == 1
    assert result[0]["farmhouse_id"] == f1.id


# ===========================================================================
# RED-10 : bookie_performance counts approved/rejected/canceled + approval_rate
# ===========================================================================

def test_bookie_performance_counts_and_approval_rate():
    from app.services.reports import bookie_performance
    _, db = _make_db()
    f1, _ = _seed_farmhouses(db)
    _, bk1, _ = _seed_users(db)

    _make_booking(db, farmhouse_id=f1.id, bookie_id=bk1.id, status="booked",   start_at=_T(2024, 1, 5, 8))
    _make_booking(db, farmhouse_id=f1.id, bookie_id=bk1.id, status="booked",   start_at=_T(2024, 1, 6, 8))
    _make_booking(db, farmhouse_id=f1.id, bookie_id=bk1.id, status="rejected", start_at=_T(2024, 1, 7, 8))
    _make_booking(db, farmhouse_id=f1.id, bookie_id=bk1.id, status="canceled", start_at=_T(2024, 1, 8, 8))
    _make_booking(db, farmhouse_id=f1.id, bookie_id=bk1.id, status="pending",  start_at=_T(2024, 1, 9, 8))
    _make_booking(db, farmhouse_id=f1.id, bookie_id=bk1.id, status="hold",     start_at=_T(2024, 1, 10, 8))
    _make_booking(db, farmhouse_id=f1.id, bookie_id=bk1.id, status="expired",  start_at=_T(2024, 1, 11, 8))

    result = bookie_performance(db, start=_T(2024, 1, 1, 0), end=_T(2024, 2, 1, 0))

    assert len(result) == 1
    p = result[0]
    assert p["bookie_id"] == bk1.id
    # submitted = NOT hold AND NOT expired: booked(2)+rejected+canceled+pending = 5
    assert p["submitted"] == 5
    assert p["approved"] == 2
    assert p["rejected"] == 1
    assert p["canceled"] == 1
    # approval_rate = 2/(2+1) = 0.67
    assert p["approval_rate"] == round(2 / 3, 2)


# ===========================================================================
# RED-11 : bookie_performance approval_rate null when no approved+rejected
# ===========================================================================

def test_bookie_performance_approval_rate_null():
    from app.services.reports import bookie_performance
    _, db = _make_db()
    f1, _ = _seed_farmhouses(db)
    _, bk1, _ = _seed_users(db)

    # Only pending + canceled — no approved, no rejected
    _make_booking(db, farmhouse_id=f1.id, bookie_id=bk1.id, status="pending",  start_at=_T(2024, 1, 5, 8))
    _make_booking(db, farmhouse_id=f1.id, bookie_id=bk1.id, status="canceled", start_at=_T(2024, 1, 6, 8))

    result = bookie_performance(db, start=_T(2024, 1, 1, 0), end=_T(2024, 2, 1, 0))
    assert result[0]["approval_rate"] is None


# ===========================================================================
# RED-12 : trends returns chronological buckets incl zeros (monthly)
# ===========================================================================

def test_trends_monthly_with_zero_buckets():
    from app.services.reports import trends
    _, db = _make_db()
    f1, _ = _seed_farmhouses(db)
    _, bk1, _ = _seed_users(db)

    # Bookings in Jan 2024 and Apr 2024, nothing in Feb/Mar
    _make_booking(db, farmhouse_id=f1.id, bookie_id=bk1.id, status="booked", start_at=_T(2024, 1, 10, 8))
    _make_booking(db, farmhouse_id=f1.id, bookie_id=bk1.id, status="booked", start_at=_T(2024, 4, 5, 8))

    result = trends(db, start=_T(2024, 1, 1, 0), end=_T(2024, 5, 1, 0))

    periods = [r["period"] for r in result]
    assert "2024-01" in periods
    assert "2024-02" in periods  # zero bucket
    assert "2024-03" in periods  # zero bucket
    assert "2024-04" in periods

    jan = next(r for r in result if r["period"] == "2024-01")
    feb = next(r for r in result if r["period"] == "2024-02")
    apr = next(r for r in result if r["period"] == "2024-04")

    assert jan["booked_count"] == 1
    assert feb["booked_count"] == 0
    assert apr["booked_count"] == 1

    # Must be sorted chronologically
    assert periods == sorted(periods)


# ===========================================================================
# RED-13 : search_bookings by status
# ===========================================================================

def test_search_bookings_by_status():
    from app.services.reports import search_bookings
    _, db = _make_db()
    f1, _ = _seed_farmhouses(db)
    _, bk1, _ = _seed_users(db)

    _make_booking(db, farmhouse_id=f1.id, bookie_id=bk1.id, status="booked",  start_at=_T(2024, 1, 5, 8))
    _make_booking(db, farmhouse_id=f1.id, bookie_id=bk1.id, status="pending", start_at=_T(2024, 1, 6, 8))
    _make_booking(db, farmhouse_id=f1.id, bookie_id=bk1.id, status="hold",    start_at=_T(2024, 1, 7, 8))

    booked = search_bookings(db, status="booked")
    assert all(b.status == "booked" for b in booked)
    assert len(booked) == 1


# ===========================================================================
# RED-14 : search_bookings by farmhouse_id
# ===========================================================================

def test_search_bookings_by_farmhouse_id():
    from app.services.reports import search_bookings
    _, db = _make_db()
    f1, f2 = _seed_farmhouses(db)
    _, bk1, _ = _seed_users(db)

    _make_booking(db, farmhouse_id=f1.id, bookie_id=bk1.id, status="booked", start_at=_T(2024, 1, 5, 8))
    _make_booking(db, farmhouse_id=f2.id, bookie_id=bk1.id, status="booked", start_at=_T(2024, 1, 6, 8))

    result = search_bookings(db, farmhouse_id=f1.id)
    assert all(b.farmhouse_id == f1.id for b in result)
    assert len(result) == 1


# ===========================================================================
# RED-15 : search_bookings by date range (start/end)
# ===========================================================================

def test_search_bookings_by_date_range():
    from app.services.reports import search_bookings
    _, db = _make_db()
    f1, _ = _seed_farmhouses(db)
    _, bk1, _ = _seed_users(db)

    _make_booking(db, farmhouse_id=f1.id, bookie_id=bk1.id, status="booked", start_at=_T(2024, 1, 5, 8))
    _make_booking(db, farmhouse_id=f1.id, bookie_id=bk1.id, status="booked", start_at=_T(2024, 2, 5, 8))
    _make_booking(db, farmhouse_id=f1.id, bookie_id=bk1.id, status="booked", start_at=_T(2024, 3, 5, 8))

    result = search_bookings(db, start=_T(2024, 1, 1, 0), end=_T(2024, 3, 1, 0))
    assert len(result) == 2
    for b in result:
        assert b.start_at >= _T(2024, 1, 1, 0)
        assert b.start_at < _T(2024, 3, 1, 0)


# ===========================================================================
# RED-16 : search_bookings by client_name case-insensitive substring
# ===========================================================================

def test_search_bookings_by_client_name():
    from app.services.reports import search_bookings
    _, db = _make_db()
    f1, _ = _seed_farmhouses(db)
    _, bk1, _ = _seed_users(db)

    _make_booking(db, farmhouse_id=f1.id, bookie_id=bk1.id, status="booked",
                  start_at=_T(2024, 1, 5, 8), client_name="John Doe")
    _make_booking(db, farmhouse_id=f1.id, bookie_id=bk1.id, status="booked",
                  start_at=_T(2024, 1, 6, 8), client_name="Jane Smith")

    result_lower = search_bookings(db, client="john")
    assert len(result_lower) == 1
    assert result_lower[0].client_name == "John Doe"

    result_upper = search_bookings(db, client="JANE")
    assert len(result_upper) == 1
    assert result_upper[0].client_name == "Jane Smith"

    result_partial = search_bookings(db, client="doe")
    assert len(result_partial) == 1


# ===========================================================================
# RED-17 : search_bookings combined filters
# ===========================================================================

def test_search_bookings_combined_filters():
    from app.services.reports import search_bookings
    _, db = _make_db()
    f1, f2 = _seed_farmhouses(db)
    _, bk1, bk2 = _seed_users(db)

    # Matches all filters
    target = _make_booking(db, farmhouse_id=f1.id, bookie_id=bk1.id, status="booked",
                           start_at=_T(2024, 1, 15, 8), client_name="Alice")
    # Wrong farmhouse
    _make_booking(db, farmhouse_id=f2.id, bookie_id=bk1.id, status="booked",
                  start_at=_T(2024, 1, 15, 8), client_name="Alice")
    # Wrong status
    _make_booking(db, farmhouse_id=f1.id, bookie_id=bk1.id, status="pending",
                  start_at=_T(2024, 1, 15, 8), client_name="Alice")
    # Wrong client
    _make_booking(db, farmhouse_id=f1.id, bookie_id=bk1.id, status="booked",
                  start_at=_T(2024, 1, 15, 8), client_name="Bob")

    result = search_bookings(db, farmhouse_id=f1.id, status="booked", client="alice")
    assert len(result) == 1
    assert result[0].id == target.id


# ===========================================================================
# RED-18 : bookings_to_xlsx returns bytes starting with PK (zip magic bytes)
# ===========================================================================

def test_bookings_to_xlsx_magic_bytes():
    from app.services.exporters import bookings_to_xlsx
    rows = [{"id": 1, "status": "booked", "client_name": "Test"}]
    data = bookings_to_xlsx(rows)
    assert isinstance(data, bytes)
    assert len(data) > 0
    assert data[:2] == b"PK", f"Expected PK, got {data[:4]!r}"


# ===========================================================================
# RED-19 : bookings_to_pdf returns bytes starting with %PDF
# ===========================================================================

def test_bookings_to_pdf_magic_bytes():
    from app.services.exporters import bookings_to_pdf
    rows = [{"id": 1, "status": "booked", "client_name": "Test"}]
    data = bookings_to_pdf(rows)
    assert isinstance(data, bytes)
    assert len(data) > 0
    assert data[:4] == b"%PDF", f"Expected %PDF, got {data[:8]!r}"


# ===========================================================================
# RED-20 : endpoint auth: bookie GET /api/reports/summary -> 403
# ===========================================================================

def test_summary_bookie_gets_403():
    from app.security import create_access_token
    c = _make_client()
    _, bk1, _ = _seed_users(c._TestSession())

    tok = create_access_token(user_id=bk1.id, role="bookie")
    resp = c.get("/api/reports/summary", headers={"Authorization": f"Bearer {tok}"})
    assert resp.status_code == 403


# ===========================================================================
# RED-21 : endpoint auth: admin GET /api/reports/summary -> 200
# ===========================================================================

def test_summary_admin_gets_200():
    from app.security import create_access_token
    c = _make_client()
    admin, _, _ = _seed_users(c._TestSession())

    tok = create_access_token(user_id=admin.id, role="admin")
    resp = c.get("/api/reports/summary", headers={"Authorization": f"Bearer {tok}"})
    assert resp.status_code == 200
    body = resp.json()
    assert "counts" in body
    assert "monthly" in body
    assert "yearly" in body


# ===========================================================================
# RED-22 : GET /api/reports/export?report=bookings&format=xlsx -> 200 + xlsx media type + PK bytes
# ===========================================================================

def test_export_bookings_xlsx():
    from app.security import create_access_token
    c = _make_client()
    admin, _, _ = _seed_users(c._TestSession())

    tok = create_access_token(user_id=admin.id, role="admin")
    resp = c.get("/api/reports/export?report=bookings&format=xlsx",
                 headers={"Authorization": f"Bearer {tok}"})
    assert resp.status_code == 200
    assert "spreadsheetml" in resp.headers["content-type"]
    assert resp.content[:2] == b"PK"


# ===========================================================================
# RED-23 : GET /api/reports/export?report=bookings&format=pdf -> 200 + pdf bytes
# ===========================================================================

def test_export_bookings_pdf():
    from app.security import create_access_token
    c = _make_client()
    admin, _, _ = _seed_users(c._TestSession())

    tok = create_access_token(user_id=admin.id, role="admin")
    resp = c.get("/api/reports/export?report=bookings&format=pdf",
                 headers={"Authorization": f"Bearer {tok}"})
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content[:4] == b"%PDF"


# ===========================================================================
# RED-24 : GET /api/reports/export?report=bookings&format=bad -> 400
# ===========================================================================

def test_export_bad_format_returns_400():
    from app.security import create_access_token
    c = _make_client()
    admin, _, _ = _seed_users(c._TestSession())

    tok = create_access_token(user_id=admin.id, role="admin")
    resp = c.get("/api/reports/export?report=bookings&format=csv",
                 headers={"Authorization": f"Bearer {tok}"})
    assert resp.status_code == 400

    resp2 = c.get("/api/reports/export?report=unknown&format=xlsx",
                  headers={"Authorization": f"Bearer {tok}"})
    assert resp2.status_code == 400
