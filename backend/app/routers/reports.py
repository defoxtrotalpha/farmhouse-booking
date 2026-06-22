"""Reports & analytics API router — admin-only.

All endpoints require admin access (require_admin dependency).

Default date range (when start/end omitted): last 365 days ending at the
current UTC timestamp. Documented per endpoint.

Endpoints:
  GET /api/reports/summary?start=&end=
      -> {counts: dict, monthly: list[dict], yearly: list[dict]}

  GET /api/reports/occupancy?start=&end=&farmhouse_id=
      -> list[{farmhouse_id, farmhouse_name, booked_seconds,
               window_seconds, occupancy_percent}]

  GET /api/reports/bookie-performance?start=&end=
      -> list[{bookie_id, bookie_name, submitted, approved, rejected,
               canceled, approval_rate}]

  GET /api/reports/trends?start=&end=&granularity=month|year
      -> list[{period, booked_count}]

  GET /api/reports/bookings?farmhouse_id=&status=&start=&end=&bookie_id=&client=
      -> list of booking dicts enriched with farmhouse_name + bookie_name

  GET /api/reports/export?report=bookings|summary|occupancy|bookie-performance
                         &format=xlsx|pdf
                         [+ same filters as above]
      -> StreamingResponse
         xlsx: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet
         pdf:  application/pdf
         Content-Disposition: attachment; filename="<report>.<ext>"
         400 on unknown report or format.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from io import BytesIO
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import require_admin
from app.models.farmhouse import Farmhouse
from app.models.user import User
from app.services import reports as reports_svc
from app.services.exporters import (
    bookings_to_pdf,
    bookings_to_xlsx,
    report_to_pdf,
    report_to_xlsx,
)

router = APIRouter(prefix="/api", tags=["reports"])

_VALID_REPORTS = {"bookings", "summary", "occupancy", "bookie-performance"}
_VALID_FORMATS = {"xlsx", "pdf"}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _default_range() -> tuple[datetime, datetime]:
    """Default: last 365 days ending now (UTC)."""
    now = datetime.now(timezone.utc)
    return now - timedelta(days=365), now


def _parse_dt(s: str | None, default: datetime | None) -> datetime | None:
    """Parse ISO datetime string; attach UTC if naive; return default if None."""
    if s is None:
        return default
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid datetime: {s!r}") from exc


def _booking_to_dict(b, fh_map: dict[int, str], user_map: dict[int, str]) -> dict:
    return {
        "id": b.id,
        "farmhouse_id": b.farmhouse_id,
        "farmhouse_name": fh_map.get(b.farmhouse_id, ""),
        "bookie_id": b.bookie_id,
        "bookie_name": user_map.get(b.bookie_id, ""),
        "status": b.status,
        "start_at": b.start_at.isoformat() if b.start_at else None,
        "end_at": b.end_at.isoformat() if b.end_at else None,
        "client_name": b.client_name,
        "client_contact": b.client_contact,
        "event_type": b.event_type,
        "quoted_price": b.quoted_price,
        "created_at": b.created_at.isoformat() if b.created_at else None,
    }


def _enrich_bookings(bookings, db: Session) -> list[dict]:
    fh_map = {f.id: f.name for f in db.query(Farmhouse).all()}
    user_map = {u.id: u.name for u in db.query(User).all()}
    return [_booking_to_dict(b, fh_map, user_map) for b in bookings]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/reports/summary")
def get_summary(
    start: Optional[str] = Query(None, description="ISO datetime, default = now-365d"),
    end: Optional[str] = Query(None, description="ISO datetime, default = now"),
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
):
    """Summary report: booking counts by status + monthly + yearly breakdowns."""
    default_start, default_end = _default_range()
    s = _parse_dt(start, default_start)
    e = _parse_dt(end, default_end)
    return {
        "counts": reports_svc.booking_counts(db, start=s, end=e),
        "monthly": reports_svc.monthly_breakdown(db, start=s, end=e),
        "yearly": reports_svc.yearly_breakdown(db, start=s, end=e),
    }


@router.get("/reports/occupancy")
def get_occupancy(
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    farmhouse_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
):
    """Occupancy % per farmhouse for the given window."""
    default_start, default_end = _default_range()
    s = _parse_dt(start, default_start)
    e = _parse_dt(end, default_end)
    return reports_svc.occupancy(db, start=s, end=e, farmhouse_id=farmhouse_id)


@router.get("/reports/bookie-performance")
def get_bookie_performance(
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
):
    """Per-bookie submission / approval / rejection / cancellation metrics."""
    default_start, default_end = _default_range()
    s = _parse_dt(start, default_start)
    e = _parse_dt(end, default_end)
    return reports_svc.bookie_performance(db, start=s, end=e)


@router.get("/reports/trends")
def get_trends(
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    granularity: str = Query("month", description="'month' or 'year'"),
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
):
    """Time-series of confirmed (booked) bookings per local Karachi period."""
    default_start, default_end = _default_range()
    s = _parse_dt(start, default_start)
    e = _parse_dt(end, default_end)
    return reports_svc.trends(db, start=s, end=e, granularity=granularity)


@router.get("/reports/bookings")
def get_bookings_report(
    farmhouse_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    bookie_id: Optional[int] = Query(None),
    client: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
):
    """Filtered booking list (newest-first) enriched with farmhouse/bookie names."""
    bookings = reports_svc.search_bookings(
        db,
        farmhouse_id=farmhouse_id,
        status=status,
        start=_parse_dt(start, None),
        end=_parse_dt(end, None),
        bookie_id=bookie_id,
        client=client,
    )
    return _enrich_bookings(bookings, db)


@router.get("/reports/export")
def export_report(
    report: str = Query(..., description="bookings | summary | occupancy | bookie-performance"),
    format: str = Query(..., description="xlsx | pdf"),  # noqa: A002
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    farmhouse_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    bookie_id: Optional[int] = Query(None),
    client: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
):
    """Export a report as xlsx or pdf.

    Default date range (if start/end omitted): last 365 days ending now (UTC).
    Returns 400 for unknown report or format values.
    """
    if report not in _VALID_REPORTS:
        raise HTTPException(status_code=400, detail=f"Unknown report type: {report!r}")
    if format not in _VALID_FORMATS:
        raise HTTPException(status_code=400, detail=f"Unknown format: {format!r}")

    default_start, default_end = _default_range()
    s = _parse_dt(start, default_start)
    e = _parse_dt(end, default_end)

    if format == "xlsx":
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    else:
        media_type = "application/pdf"

    filename = f"{report}.{format}"

    # ── produce data bytes ────────────────────────────────────────────────────
    if report == "bookings":
        bookings = reports_svc.search_bookings(
            db,
            farmhouse_id=farmhouse_id,
            status=status,
            start=s,
            end=e,
            bookie_id=bookie_id,
            client=client,
        )
        rows = _enrich_bookings(bookings, db)
        data = bookings_to_xlsx(rows) if format == "xlsx" else bookings_to_pdf(rows)

    elif report == "summary":
        counts = reports_svc.booking_counts(db, start=s, end=e)
        hdrs = ["Metric", "Value"]
        tbl_rows = [[k, v] for k, v in counts.items()]
        data = (
            report_to_xlsx("Summary", hdrs, tbl_rows)
            if format == "xlsx"
            else report_to_pdf("Summary", hdrs, tbl_rows)
        )

    elif report == "occupancy":
        occ = reports_svc.occupancy(db, start=s, end=e, farmhouse_id=farmhouse_id)
        hdrs = ["Farmhouse ID", "Farmhouse Name", "Booked Seconds",
                "Window Seconds", "Occupancy %"]
        tbl_rows = [
            [r["farmhouse_id"], r["farmhouse_name"], r["booked_seconds"],
             r["window_seconds"], r["occupancy_percent"]]
            for r in occ
        ]
        data = (
            report_to_xlsx("Occupancy", hdrs, tbl_rows)
            if format == "xlsx"
            else report_to_pdf("Occupancy", hdrs, tbl_rows)
        )

    else:  # bookie-performance
        perf = reports_svc.bookie_performance(db, start=s, end=e)
        hdrs = ["Bookie ID", "Bookie Name", "Submitted", "Approved",
                "Rejected", "Canceled", "Approval Rate"]
        tbl_rows = [
            [p["bookie_id"], p["bookie_name"], p["submitted"], p["approved"],
             p["rejected"], p["canceled"], p["approval_rate"]]
            for p in perf
        ]
        data = (
            report_to_xlsx("Bookie Performance", hdrs, tbl_rows)
            if format == "xlsx"
            else report_to_pdf("Bookie Performance", hdrs, tbl_rows)
        )

    return StreamingResponse(
        BytesIO(data),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
