# Reports & analytics + Excel/PDF export

**Type:** AFK
**Source:** [issues/prd.md](prd.md)

## What to build

Give Admins visibility into the operation. Reports cover monthly/yearly bookings, occupancy tracking, bookie performance, and booking trends, plus search/filter across bookings (by farmhouse, status, date range, bookie, client). Report and booking-list data can be exported to Excel (.xlsx) and PDF.

## Acceptance criteria

- [ ] Report endpoints compute occupancy, bookie performance, trends, and monthly/yearly counts.
- [ ] Search/filter endpoint supports farmhouse, status, date range, bookie, and client filters.
- [ ] React reports UI renders the metrics and supports filtering.
- [ ] Export produces valid `.xlsx` and `.pdf` for reports/booking lists.
- [ ] Metric definitions (e.g., occupancy %, bookie performance) are documented.
- [ ] Tests cover report computations and export generation.

## Blocked by

- #9 Conflict resolution: auto-detect & reject overlapping pendings
