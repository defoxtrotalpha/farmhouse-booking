"""Reports & analytics service — pure computation, no HTTP.

All functions take a SQLAlchemy Session plus filters and return plain dicts/lists.
No side-effects; safe to call from tests without an HTTP layer.

Metric definitions (canonical):

booking_counts(db, *, start, end) -> dict
    Counts of bookings whose start_at is in the half-open interval [start, end),
    grouped by status. Also returns key 'total' = sum of all counts.
    "Confirmed" means status == 'booked'.

monthly_breakdown(db, *, start, end) -> list[dict]
    For each Asia/Karachi (year, month) bucket that contains at least one booking
    with start_at in [start, end), returns:
      {year: int, month: int, booked_count: int, total_count: int}
    Grouping key is the LOCAL calendar month of start_at after converting to
    Asia/Karachi (UTC+5). A booking at 2024-01-31 20:00 UTC falls in Karachi
    month February (2024-02-01 01:00 local). Sorted chronologically.

yearly_breakdown(db, *, start, end) -> list[dict]
    Same but grouped by local Karachi year:
      {year: int, booked_count: int, total_count: int}
    Sorted chronologically.

occupancy(db, *, start, end, farmhouse_id=None) -> list[dict]
    Per-farmhouse occupancy over the window [start, end):
      occupancy_percent = (
          sum over status=='booked' bookings of
          overlap_seconds(booking, window)
      ) / window_seconds * 100
    Capped at 100.0, rounded to 1 decimal place.
    Buffer minutes are NOT included in occupancy (only actual booked time).
    Returns:
      [{farmhouse_id, farmhouse_name, booked_seconds, window_seconds,
        occupancy_percent}]
    If farmhouse_id is given, only that farmhouse is returned.

bookie_performance(db, *, start, end) -> list[dict]
    Per-bookie metrics over bookings with start_at in [start, end):
      submitted    = count where status NOT IN ('hold', 'expired')
      approved     = count where status == 'booked'
      rejected     = count where status == 'rejected'
      canceled     = count where status == 'canceled'
      approval_rate = approved / (approved + rejected) rounded to 2 dp,
                      or None when (approved + rejected) == 0
    Returns:
      [{bookie_id, bookie_name, submitted, approved, rejected, canceled,
        approval_rate}]
    Sorted by bookie_id.

trends(db, *, start, end, granularity='month') -> list[dict]
    Time series of booked_count per local Karachi period:
      granularity='month' -> [{period: 'YYYY-MM', booked_count}]
      granularity='year'  -> [{period: 'YYYY',    booked_count}]
    Includes ALL buckets in [start, end) as empty (booked_count=0) if needed.
    Sorted chronologically.

search_bookings(db, *, farmhouse_id, status, start, end, bookie_id, client)
    -> list[Booking]
    Filter bookings; all params optional. client = case-insensitive substring
    match on client_name. Date range filters on start_at (half-open [start, end)).
    Returns newest-first (created_at DESC).
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.models.booking import Booking
from app.models.farmhouse import Farmhouse
from app.models.user import User

_KHI = ZoneInfo("Asia/Karachi")


def _to_local(dt: datetime) -> datetime:
    """Convert a UTC-aware datetime to Asia/Karachi local time."""
    return dt.astimezone(_KHI)


# ---------------------------------------------------------------------------
# booking_counts
# ---------------------------------------------------------------------------

def booking_counts(db: Session, *, start: datetime, end: datetime) -> dict:
    """Return status-grouped counts for bookings whose start_at is in [start, end).

    Returns a dict with each status as key plus 'total'.
    """
    rows = (
        db.query(Booking)
        .filter(Booking.start_at >= start, Booking.start_at < end)
        .all()
    )
    counts: dict[str, int] = defaultdict(int)
    for b in rows:
        counts[b.status] += 1
    result = dict(counts)
    result["total"] = len(rows)
    return result


# ---------------------------------------------------------------------------
# monthly_breakdown
# ---------------------------------------------------------------------------

def monthly_breakdown(db: Session, *, start: datetime, end: datetime) -> list[dict]:
    """Return per-Karachi-month summary of bookings with start_at in [start, end)."""
    rows = (
        db.query(Booking)
        .filter(Booking.start_at >= start, Booking.start_at < end)
        .all()
    )
    buckets: dict[tuple[int, int], dict] = defaultdict(
        lambda: {"booked_count": 0, "total_count": 0}
    )
    for b in rows:
        local_dt = _to_local(b.start_at)
        key = (local_dt.year, local_dt.month)
        buckets[key]["total_count"] += 1
        if b.status == "booked":
            buckets[key]["booked_count"] += 1

    return [
        {"year": k[0], "month": k[1], **v}
        for k, v in sorted(buckets.items())
    ]


# ---------------------------------------------------------------------------
# yearly_breakdown
# ---------------------------------------------------------------------------

def yearly_breakdown(db: Session, *, start: datetime, end: datetime) -> list[dict]:
    """Return per-Karachi-year summary of bookings with start_at in [start, end)."""
    rows = (
        db.query(Booking)
        .filter(Booking.start_at >= start, Booking.start_at < end)
        .all()
    )
    buckets: dict[int, dict] = defaultdict(lambda: {"booked_count": 0, "total_count": 0})
    for b in rows:
        local_dt = _to_local(b.start_at)
        key = local_dt.year
        buckets[key]["total_count"] += 1
        if b.status == "booked":
            buckets[key]["booked_count"] += 1

    return [{"year": k, **v} for k, v in sorted(buckets.items())]


# ---------------------------------------------------------------------------
# occupancy
# ---------------------------------------------------------------------------

def occupancy(
    db: Session,
    *,
    start: datetime,
    end: datetime,
    farmhouse_id: Optional[int] = None,
) -> list[dict]:
    """Return per-farmhouse occupancy over window [start, end).

    Only active farmhouses are included. If farmhouse_id is provided,
    restrict to that one farmhouse.
    """
    window_seconds = (end - start).total_seconds()

    fh_query = db.query(Farmhouse).filter(Farmhouse.status == "active")
    if farmhouse_id is not None:
        fh_query = fh_query.filter(Farmhouse.id == farmhouse_id)
    farmhouses = fh_query.all()

    result = []
    for fh in farmhouses:
        bookings = (
            db.query(Booking)
            .filter(
                Booking.farmhouse_id == fh.id,
                Booking.status == "booked",
                Booking.start_at < end,
                Booking.end_at > start,
            )
            .all()
        )

        booked_seconds = 0.0
        for b in bookings:
            overlap_start = max(b.start_at, start)
            overlap_end = min(b.end_at, end)
            if overlap_end > overlap_start:
                booked_seconds += (overlap_end - overlap_start).total_seconds()

        occupancy_pct = 0.0
        if window_seconds > 0:
            occupancy_pct = min(100.0, booked_seconds / window_seconds * 100)

        result.append({
            "farmhouse_id": fh.id,
            "farmhouse_name": fh.name,
            "booked_seconds": booked_seconds,
            "window_seconds": window_seconds,
            "occupancy_percent": round(occupancy_pct, 1),
        })
    return result


# ---------------------------------------------------------------------------
# bookie_performance
# ---------------------------------------------------------------------------

def bookie_performance(db: Session, *, start: datetime, end: datetime) -> list[dict]:
    """Return per-bookie performance for bookings with start_at in [start, end)."""
    rows = (
        db.query(Booking)
        .filter(Booking.start_at >= start, Booking.start_at < end)
        .all()
    )

    bookie_ids = {b.bookie_id for b in rows}
    users: dict[int, User] = {}
    if bookie_ids:
        users = {u.id: u for u in db.query(User).filter(User.id.in_(bookie_ids)).all()}

    perf: dict[int, dict] = {}
    for b in rows:
        bid = b.bookie_id
        if bid not in perf:
            u = users.get(bid)
            perf[bid] = {
                "bookie_id": bid,
                "bookie_name": u.name if u else str(bid),
                "submitted": 0,
                "approved": 0,
                "rejected": 0,
                "canceled": 0,
            }
        p = perf[bid]
        if b.status not in ("hold", "expired"):
            p["submitted"] += 1
        if b.status == "booked":
            p["approved"] += 1
        if b.status == "rejected":
            p["rejected"] += 1
        if b.status == "canceled":
            p["canceled"] += 1

    result = []
    for p in perf.values():
        denom = p["approved"] + p["rejected"]
        p["approval_rate"] = round(p["approved"] / denom, 2) if denom > 0 else None
        result.append(p)

    return sorted(result, key=lambda x: x["bookie_id"])


# ---------------------------------------------------------------------------
# trends
# ---------------------------------------------------------------------------

def trends(
    db: Session,
    *,
    start: datetime,
    end: datetime,
    granularity: str = "month",
) -> list[dict]:
    """Return time-series of booked_count per local Karachi period.

    granularity='month' -> periods like '2024-01'
    granularity='year'  -> periods like '2024'
    All buckets in the range are included (zeros for empty periods).
    """
    rows = (
        db.query(Booking)
        .filter(
            Booking.status == "booked",
            Booking.start_at >= start,
            Booking.start_at < end,
        )
        .all()
    )

    counts: dict[str, int] = defaultdict(int)
    for b in rows:
        local_dt = _to_local(b.start_at)
        if granularity == "year":
            key = f"{local_dt.year}"
        else:
            key = f"{local_dt.year}-{local_dt.month:02d}"
        counts[key] += 1

    buckets = _generate_buckets(start, end, granularity)
    return [{"period": p, "booked_count": counts.get(p, 0)} for p in buckets]


def _generate_buckets(start: datetime, end: datetime, granularity: str) -> list[str]:
    """Generate all period keys between start and end in Asia/Karachi calendar."""
    local_start = _to_local(start)
    local_end = _to_local(end)

    buckets: list[str] = []
    if granularity == "year":
        y = local_start.year
        while y <= local_end.year:
            buckets.append(f"{y}")
            y += 1
    else:
        y, m = local_start.year, local_start.month
        end_y, end_m = local_end.year, local_end.month
        while (y, m) <= (end_y, end_m):
            buckets.append(f"{y}-{m:02d}")
            m += 1
            if m > 12:
                m = 1
                y += 1
    return buckets


# ---------------------------------------------------------------------------
# search_bookings
# ---------------------------------------------------------------------------

def search_bookings(
    db: Session,
    *,
    farmhouse_id: Optional[int] = None,
    status: Optional[str] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    bookie_id: Optional[int] = None,
    client: Optional[str] = None,
) -> list[Booking]:
    """Filter bookings, return newest-first.

    client = case-insensitive substring match on client_name.
    Date range filters on start_at using half-open interval [start, end).
    """
    q = db.query(Booking)
    if farmhouse_id is not None:
        q = q.filter(Booking.farmhouse_id == farmhouse_id)
    if status is not None:
        q = q.filter(Booking.status == status)
    if start is not None:
        q = q.filter(Booking.start_at >= start)
    if end is not None:
        q = q.filter(Booking.start_at < end)
    if bookie_id is not None:
        q = q.filter(Booking.bookie_id == bookie_id)
    if client is not None:
        q = q.filter(Booking.client_name.ilike(f"%{client}%"))
    return q.order_by(Booking.created_at.desc()).all()
