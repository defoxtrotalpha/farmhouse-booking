import { useEffect, useState } from "react";
import {
  getReportSummary,
  getOccupancy,
  getBookiePerformance,
  getTrends,
  searchBookingsReport,
  downloadReportExport,
  listFarmhouses,
} from "./api.js";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const th = { padding: "0.4rem 0.6rem", textAlign: "left", borderBottom: "1px solid #e5e5e5", fontWeight: 600, background: "#f5f5f5" };
const td = { padding: "0.35rem 0.6rem", borderBottom: "1px solid #f0f0f0", fontSize: "0.85rem" };
const card = { border: "1px solid #e5e5e5", borderRadius: 8, padding: "1rem 1.25rem", marginBottom: "1.25rem" };
const row = { display: "flex", gap: "0.75rem", flexWrap: "wrap", alignItems: "flex-end", marginBottom: "0.75rem" };
const lbl = { display: "flex", flexDirection: "column", gap: "0.2rem", fontSize: "0.8rem", color: "#555" };
const inp = { padding: "0.35rem 0.5rem", border: "1px solid #ccc", borderRadius: 4, fontSize: "0.85rem" };
const btn = (variant = "primary") => ({
  padding: "0.4rem 0.9rem",
  cursor: "pointer",
  border: "none",
  borderRadius: 4,
  fontWeight: 600,
  fontSize: "0.8rem",
  background: variant === "primary" ? "#1a6b3a" : variant === "pdf" ? "#a63232" : "#2a5ca6",
  color: "#fff",
});

function isoToday() {
  return new Date().toISOString().slice(0, 10);
}
function iso365DaysAgo() {
  const d = new Date();
  d.setFullYear(d.getFullYear() - 1);
  return d.toISOString().slice(0, 10);
}

// ---------------------------------------------------------------------------
// Summary panel
// ---------------------------------------------------------------------------

function SummaryPanel({ start, end }) {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    setData(null); setErr(null);
    getReportSummary({ start, end })
      .then(setData)
      .catch((e) => setErr(e.message));
  }, [start, end]);

  if (err) return <p style={{ color: "#b00020" }}>{err}</p>;
  if (!data) return <p>Loading…</p>;

  const { counts } = data;
  const statuses = Object.entries(counts).filter(([k]) => k !== "total");

  return (
    <div>
      <div style={{ display: "flex", gap: "1rem", flexWrap: "wrap", marginBottom: "0.75rem" }}>
        {statuses.map(([k, v]) => (
          <div key={k} style={{ border: "1px solid #e5e5e5", borderRadius: 6, padding: "0.5rem 0.9rem", minWidth: 80, textAlign: "center" }}>
            <div style={{ fontSize: "1.4rem", fontWeight: 700 }}>{v}</div>
            <div style={{ fontSize: "0.75rem", color: "#666", textTransform: "capitalize" }}>{k}</div>
          </div>
        ))}
        <div style={{ border: "2px solid #1a6b3a", borderRadius: 6, padding: "0.5rem 0.9rem", minWidth: 80, textAlign: "center" }}>
          <div style={{ fontSize: "1.4rem", fontWeight: 700 }}>{counts.total}</div>
          <div style={{ fontSize: "0.75rem", color: "#1a6b3a", fontWeight: 600 }}>Total</div>
        </div>
      </div>

      <h4 style={{ margin: "0.5rem 0 0.4rem" }}>Monthly breakdown</h4>
      {data.monthly.length === 0 ? <p style={{ color: "#888", fontSize: "0.85rem" }}>No data</p> : (
        <table style={{ borderCollapse: "collapse", width: "100%", fontSize: "0.85rem" }}>
          <thead><tr><th style={th}>Year</th><th style={th}>Month</th><th style={th}>Confirmed</th><th style={th}>Total</th></tr></thead>
          <tbody>
            {data.monthly.map((r) => (
              <tr key={`${r.year}-${r.month}`}>
                <td style={td}>{r.year}</td>
                <td style={td}>{r.month}</td>
                <td style={td}>{r.booked_count}</td>
                <td style={td}>{r.total_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Occupancy panel
// ---------------------------------------------------------------------------

function OccupancyPanel({ start, end, farmhouseId }) {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    setData(null); setErr(null);
    getOccupancy({ start, end, farmhouse_id: farmhouseId || undefined })
      .then(setData)
      .catch((e) => setErr(e.message));
  }, [start, end, farmhouseId]);

  if (err) return <p style={{ color: "#b00020" }}>{err}</p>;
  if (!data) return <p>Loading…</p>;
  if (data.length === 0) return <p style={{ color: "#888", fontSize: "0.85rem" }}>No data</p>;

  return (
    <table style={{ borderCollapse: "collapse", width: "100%", fontSize: "0.85rem" }}>
      <thead>
        <tr>
          <th style={th}>Farmhouse</th>
          <th style={th}>Booked Seconds</th>
          <th style={th}>Window Seconds</th>
          <th style={th}>Occupancy %</th>
        </tr>
      </thead>
      <tbody>
        {data.map((r) => (
          <tr key={r.farmhouse_id}>
            <td style={td}>{r.farmhouse_name}</td>
            <td style={td}>{r.booked_seconds}</td>
            <td style={td}>{r.window_seconds}</td>
            <td style={td}>
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                <div style={{ flex: 1, height: 8, background: "#e5e5e5", borderRadius: 4 }}>
                  <div style={{ width: `${r.occupancy_percent}%`, height: "100%", background: r.occupancy_percent > 80 ? "#c0392b" : "#1a6b3a", borderRadius: 4 }} />
                </div>
                <span>{r.occupancy_percent}%</span>
              </div>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

// ---------------------------------------------------------------------------
// Bookie performance panel
// ---------------------------------------------------------------------------

function BookiePerformancePanel({ start, end }) {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    setData(null); setErr(null);
    getBookiePerformance({ start, end })
      .then(setData)
      .catch((e) => setErr(e.message));
  }, [start, end]);

  if (err) return <p style={{ color: "#b00020" }}>{err}</p>;
  if (!data) return <p>Loading…</p>;
  if (data.length === 0) return <p style={{ color: "#888", fontSize: "0.85rem" }}>No data</p>;

  return (
    <table style={{ borderCollapse: "collapse", width: "100%", fontSize: "0.85rem" }}>
      <thead>
        <tr>
          <th style={th}>Bookie</th>
          <th style={th}>Submitted</th>
          <th style={th}>Approved</th>
          <th style={th}>Rejected</th>
          <th style={th}>Canceled</th>
          <th style={th}>Approval Rate</th>
        </tr>
      </thead>
      <tbody>
        {data.map((r) => (
          <tr key={r.bookie_id}>
            <td style={td}>{r.bookie_name}</td>
            <td style={td}>{r.submitted}</td>
            <td style={td}>{r.approved}</td>
            <td style={td}>{r.rejected}</td>
            <td style={td}>{r.canceled}</td>
            <td style={td}>
              {r.approval_rate == null
                ? <span style={{ color: "#aaa" }}>—</span>
                : `${(r.approval_rate * 100).toFixed(0)}%`}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

// ---------------------------------------------------------------------------
// Bookings search panel
// ---------------------------------------------------------------------------

function BookingsSearchPanel({ farmhouses }) {
  const [filters, setFilters] = useState({ farmhouse_id: "", status: "", start: "", end: "", client: "" });
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const [loading, setLoading] = useState(false);

  function setF(k, v) { setFilters((f) => ({ ...f, [k]: v })); }

  async function handleSearch(e) {
    e.preventDefault();
    setErr(null); setLoading(true);
    try {
      const res = await searchBookingsReport({
        farmhouse_id: filters.farmhouse_id || undefined,
        status: filters.status || undefined,
        start: filters.start || undefined,
        end: filters.end || undefined,
        client: filters.client || undefined,
      });
      setData(res);
    } catch (ex) {
      setErr(ex.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <form onSubmit={handleSearch} style={row}>
        <label style={lbl}>
          Farmhouse
          <select style={inp} value={filters.farmhouse_id} onChange={(e) => setF("farmhouse_id", e.target.value)}>
            <option value="">All</option>
            {farmhouses.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
          </select>
        </label>
        <label style={lbl}>
          Status
          <select style={inp} value={filters.status} onChange={(e) => setF("status", e.target.value)}>
            <option value="">All</option>
            {["hold", "pending", "booked", "rejected", "canceled", "expired"].map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </label>
        <label style={lbl}>
          Start
          <input type="date" style={inp} value={filters.start} onChange={(e) => setF("start", e.target.value)} />
        </label>
        <label style={lbl}>
          End
          <input type="date" style={inp} value={filters.end} onChange={(e) => setF("end", e.target.value)} />
        </label>
        <label style={lbl}>
          Client (contains)
          <input type="text" style={inp} value={filters.client} onChange={(e) => setF("client", e.target.value)} placeholder="name" />
        </label>
        <button type="submit" style={btn("primary")} disabled={loading}>Search</button>
      </form>
      {err && <p style={{ color: "#b00020" }}>{err}</p>}
      {data && (
        data.length === 0
          ? <p style={{ color: "#888", fontSize: "0.85rem" }}>No results</p>
          : (
            <table style={{ borderCollapse: "collapse", width: "100%", fontSize: "0.82rem" }}>
              <thead>
                <tr>
                  {["ID", "Farmhouse", "Bookie", "Status", "Start", "End", "Client", "Event", "Price"].map((h) => (
                    <th key={h} style={th}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.map((b) => (
                  <tr key={b.id}>
                    <td style={td}>{b.id}</td>
                    <td style={td}>{b.farmhouse_name}</td>
                    <td style={td}>{b.bookie_name}</td>
                    <td style={td}>{b.status}</td>
                    <td style={td}>{b.start_at ? b.start_at.slice(0, 16).replace("T", " ") : "—"}</td>
                    <td style={td}>{b.end_at ? b.end_at.slice(0, 16).replace("T", " ") : "—"}</td>
                    <td style={td}>{b.client_name ?? "—"}</td>
                    <td style={td}>{b.event_type ?? "—"}</td>
                    <td style={td}>{b.quoted_price != null ? `${b.quoted_price}` : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Export controls
// ---------------------------------------------------------------------------

function ExportControls({ start, end, farmhouseId }) {
  const [exportErr, setExportErr] = useState(null);
  const [exporting, setExporting] = useState(null);

  async function doExport(report, format) {
    setExportErr(null);
    setExporting(`${report}-${format}`);
    try {
      await downloadReportExport({ report, format, start, end, farmhouse_id: farmhouseId || undefined });
    } catch (e) {
      setExportErr(e.message);
    } finally {
      setExporting(null);
    }
  }

  const exports = [
    { label: "Summary (xlsx)", report: "summary", format: "xlsx", variant: "primary" },
    { label: "Summary (pdf)", report: "summary", format: "pdf", variant: "pdf" },
    { label: "Occupancy (xlsx)", report: "occupancy", format: "xlsx", variant: "primary" },
    { label: "Occupancy (pdf)", report: "occupancy", format: "pdf", variant: "pdf" },
    { label: "Bookie Perf (xlsx)", report: "bookie-performance", format: "xlsx", variant: "primary" },
    { label: "Bookie Perf (pdf)", report: "bookie-performance", format: "pdf", variant: "pdf" },
    { label: "Bookings (xlsx)", report: "bookings", format: "xlsx", variant: "primary" },
    { label: "Bookings (pdf)", report: "bookings", format: "pdf", variant: "pdf" },
  ];

  return (
    <div>
      <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
        {exports.map(({ label, report, format, variant }) => {
          const key = `${report}-${format}`;
          return (
            <button key={key} style={btn(variant)} disabled={exporting === key}
              onClick={() => doExport(report, format)}>
              {exporting === key ? "…" : label}
            </button>
          );
        })}
      </div>
      {exportErr && <p style={{ color: "#b00020", marginTop: "0.5rem", fontSize: "0.85rem" }}>{exportErr}</p>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main Reports page
// ---------------------------------------------------------------------------

export default function ReportsPage() {
  const [start, setStart] = useState(iso365DaysAgo());
  const [end, setEnd] = useState(isoToday());
  const [farmhouseId, setFarmhouseId] = useState("");
  const [farmhouses, setFarmhouses] = useState([]);

  useEffect(() => {
    listFarmhouses().then(setFarmhouses).catch(() => {});
  }, []);

  const filterRow = (
    <div style={row}>
      <label style={lbl}>
        Start date
        <input type="date" style={inp} value={start} onChange={(e) => setStart(e.target.value)} />
      </label>
      <label style={lbl}>
        End date
        <input type="date" style={inp} value={end} onChange={(e) => setEnd(e.target.value)} />
      </label>
      <label style={lbl}>
        Farmhouse (occupancy filter)
        <select style={inp} value={farmhouseId} onChange={(e) => setFarmhouseId(e.target.value)}>
          <option value="">All</option>
          {farmhouses.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
        </select>
      </label>
    </div>
  );

  return (
    <section>
      <h2 style={{ margin: "0 0 1rem" }}>Reports &amp; Analytics</h2>

      <div style={card}>
        <h3 style={{ margin: "0 0 0.75rem", fontSize: "0.95rem" }}>Date range &amp; filters</h3>
        {filterRow}
      </div>

      <div style={card}>
        <h3 style={{ margin: "0 0 0.75rem", fontSize: "0.95rem" }}>Booking Summary</h3>
        <SummaryPanel start={start} end={end} />
      </div>

      <div style={card}>
        <h3 style={{ margin: "0 0 0.75rem", fontSize: "0.95rem" }}>Occupancy</h3>
        <OccupancyPanel start={start} end={end} farmhouseId={farmhouseId} />
      </div>

      <div style={card}>
        <h3 style={{ margin: "0 0 0.75rem", fontSize: "0.95rem" }}>Bookie Performance</h3>
        <BookiePerformancePanel start={start} end={end} />
      </div>

      <div style={card}>
        <h3 style={{ margin: "0 0 0.75rem", fontSize: "0.95rem" }}>Search Bookings</h3>
        <BookingsSearchPanel farmhouses={farmhouses} />
      </div>

      <div style={card}>
        <h3 style={{ margin: "0 0 0.75rem", fontSize: "0.95rem" }}>Export</h3>
        <p style={{ fontSize: "0.8rem", color: "#666", marginTop: 0 }}>
          Exports use the date range selected above. Farmhouse filter applies to occupancy exports.
        </p>
        <ExportControls start={start} end={end} farmhouseId={farmhouseId} />
      </div>
    </section>
  );
}
