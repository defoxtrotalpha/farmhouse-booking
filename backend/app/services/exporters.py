"""Exporters: convert report data to xlsx or pdf bytes.

Functions:
    bookings_to_xlsx(rows: list[dict]) -> bytes
        Convert a list of booking dicts to an Excel workbook (xlsx) byte string.

    report_to_xlsx(title: str, headers: list[str], rows: list[list]) -> bytes
        Generic tabular data -> xlsx bytes. One sheet named after title.

    bookings_to_pdf(rows: list[dict]) -> bytes
        Convert a list of booking dicts to a PDF byte string.

    report_to_pdf(title: str, headers: list[str], rows: list[list]) -> bytes
        Generic tabular data -> pdf bytes using reportlab SimpleDocTemplate + Table.
"""
from __future__ import annotations

from io import BytesIO
from typing import Any

import openpyxl
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

_BOOKING_HEADERS = [
    "ID",
    "Farmhouse ID",
    "Farmhouse Name",
    "Status",
    "Start At",
    "End At",
    "Client Name",
    "Client Contact",
    "Event Type",
    "Quoted Price",
    "Bookie ID",
    "Bookie Name",
    "Created At",
]


def _booking_to_row(b: dict) -> list[str]:
    return [
        str(b.get("id", "")),
        str(b.get("farmhouse_id", "")),
        str(b.get("farmhouse_name", "")),
        str(b.get("status", "")),
        str(b.get("start_at", "")),
        str(b.get("end_at", "")),
        str(b.get("client_name", "")),
        str(b.get("client_contact", "")),
        str(b.get("event_type", "")),
        str(b.get("quoted_price", "")),
        str(b.get("bookie_id", "")),
        str(b.get("bookie_name", "")),
        str(b.get("created_at", "")),
    ]


# ---------------------------------------------------------------------------
# xlsx
# ---------------------------------------------------------------------------

def bookings_to_xlsx(rows: list[dict]) -> bytes:
    """Convert a list of booking dicts to xlsx bytes."""
    return report_to_xlsx(
        "Bookings",
        _BOOKING_HEADERS,
        [_booking_to_row(r) for r in rows],
    )


def report_to_xlsx(title: str, headers: list[str], rows: list[list[Any]]) -> bytes:
    """Produce an xlsx workbook with a title, headers row, and data rows."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = title[:31]  # Excel worksheet name max 31 chars
    ws.append(headers)
    for row in rows:
        ws.append([str(c) if c is not None else "" for c in row])
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# pdf
# ---------------------------------------------------------------------------

def bookings_to_pdf(rows: list[dict]) -> bytes:
    """Convert a list of booking dicts to PDF bytes."""
    return report_to_pdf(
        "Bookings",
        _BOOKING_HEADERS,
        [_booking_to_row(r) for r in rows],
    )


def report_to_pdf(title: str, headers: list[str], rows: list[list[Any]]) -> bytes:
    """Produce a PDF with a title, headers row, and data rows (reportlab)."""
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), rightMargin=1 * cm,
                            leftMargin=1 * cm, topMargin=1.5 * cm, bottomMargin=1 * cm)
    styles = getSampleStyleSheet()
    elements = []

    elements.append(Paragraph(title, styles["Title"]))
    elements.append(Spacer(1, 0.4 * cm))

    table_data = [headers] + [[str(c) if c is not None else "" for c in row] for row in rows]
    t = Table(table_data, repeatRows=1)
    t.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4472C4")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 7),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CCCCCC")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F2F2F2")]),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ])
    )
    elements.append(t)
    doc.build(elements)
    return buf.getvalue()
