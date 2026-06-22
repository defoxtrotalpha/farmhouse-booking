/**
 * CalendarPage — read-only availability calendar (slice #21).
 *
 * - Farmhouse selector (active farmhouses from GET /api/farmhouses)
 * - FullCalendar timeGrid (week / day views)
 * - Fetches occupied bookings for the visible window via GET /api/farmhouses/{id}/availability
 * - Multi-day bookings render correctly across day boundaries (FullCalendar native)
 * - Status colours: hold=#f59e0b (amber), pending=#3b82f6 (blue), booked=#22c55e (green)
 * - All times in Asia/Karachi (FullCalendar timeZone prop)
 * - Polling every POLL_INTERVAL_MS to pick up external changes
 */

import { useCallback, useEffect, useRef, useState } from "react";
import FullCalendar from "@fullcalendar/react";
import timeGridPlugin    from "@fullcalendar/timegrid";
import dayGridPlugin    from "@fullcalendar/daygrid";
import interactionPlugin from "@fullcalendar/interaction";

import { listFarmhouses, getAvailability, createHold, submitBooking } from "./api.js";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const POLL_INTERVAL_MS = 15_000; // 15 s

const STATUS_COLOR = {
  hold:    "#f59e0b", // amber
  pending: "#3b82f6", // blue
  booked:  "#22c55e", // green
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function bookingToEvent(b) {
  return {
    id:    String(b.id),
    title: b.status.charAt(0).toUpperCase() + b.status.slice(1),
    start: b.start_at,
    end:   b.end_at,
    backgroundColor: STATUS_COLOR[b.status] ?? "#6b7280",
    borderColor:     STATUS_COLOR[b.status] ?? "#6b7280",
    textColor:       "#fff",
    extendedProps:   { bookie_id: b.bookie_id, status: b.status },
  };
}

const OVERLAY_STYLE = {
  position: "fixed", inset: 0, background: "rgba(0,0,0,.45)",
  display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000,
};
const CARD_STYLE = {
  background: "#fff", borderRadius: 8, padding: "1.5rem", minWidth: 340, maxWidth: 460,
  boxShadow: "0 8px 24px rgba(0,0,0,.2)",
};
const INPUT_STYLE = {
  width: "100%", padding: "0.4rem 0.5rem", marginBottom: "0.75rem",
  boxSizing: "border-box", border: "1px solid #ccc", borderRadius: 4, fontSize: "0.9rem",
};
const BTN = (extra) => ({
  padding: "0.45rem 1rem", borderRadius: 4, border: "none", cursor: "pointer",
  fontWeight: 600, fontSize: "0.85rem", ...extra,
});

function fmtLocal(isoStr) {
  return new Date(isoStr).toLocaleString("en-PK", { timeZone: "Asia/Karachi" });
}

// ---------------------------------------------------------------------------
// HoldConfirmDialog
// ---------------------------------------------------------------------------

function HoldConfirmDialog({ selectInfo, farmhouseName, onConfirm, onCancel, loading, error }) {
  return (
    <div style={OVERLAY_STYLE}>
      <div style={CARD_STYLE}>
        <h3 style={{ marginTop: 0 }}>Place Hold</h3>
        <p style={{ fontSize: "0.9rem", marginBottom: "0.75rem" }}>
          <strong>Farmhouse:</strong> {farmhouseName}<br />
          <strong>From:</strong> {fmtLocal(selectInfo.startStr)}<br />
          <strong>To:</strong>   {fmtLocal(selectInfo.endStr)}
        </p>
        {error && <p style={{ color: "#b00020", fontSize: "0.85rem" }}>{error}</p>}
        <div style={{ display: "flex", gap: "0.5rem", justifyContent: "flex-end" }}>
          <button style={BTN({ background: "#e5e7eb" })} onClick={onCancel} disabled={loading}>Cancel</button>
          <button style={BTN({ background: "#f59e0b", color: "#fff" })} onClick={onConfirm} disabled={loading}>
            {loading ? "Placing..." : "Place Hold"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// SubmitBookingForm
// ---------------------------------------------------------------------------

function SubmitBookingForm({ booking, onSubmit, onCancel, loading, error }) {
  const [form, setForm] = useState({
    client_name: "", client_contact: "", event_type: "",
    event_info: "", notes: "", quoted_price: "",
  });
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  function handleSubmit(ev) {
    ev.preventDefault();
    onSubmit({
      client_name:    form.client_name,
      client_contact: form.client_contact,
      event_type:     form.event_type   || undefined,
      event_info:     form.event_info   || undefined,
      notes:          form.notes        || undefined,
      quoted_price:   form.quoted_price ? parseFloat(form.quoted_price) : undefined,
    });
  }

  return (
    <div style={OVERLAY_STYLE}>
      <div style={{ ...CARD_STYLE, minWidth: 380, maxWidth: 500 }}>
        <h3 style={{ marginTop: 0 }}>Submit Booking Request</h3>
        <p style={{ fontSize: "0.85rem", color: "#555", marginBottom: "0.75rem" }}>
          Hold #{booking.id} &middot; {fmtLocal(booking.start_at)} to {fmtLocal(booking.end_at)}
        </p>
        <form onSubmit={handleSubmit}>
          <input required style={INPUT_STYLE} placeholder="Client Name *"    value={form.client_name}    onChange={set("client_name")} />
          <input required style={INPUT_STYLE} placeholder="Client Contact *" value={form.client_contact} onChange={set("client_contact")} />
          <input style={INPUT_STYLE} placeholder="Event Type (e.g. Wedding)" value={form.event_type}     onChange={set("event_type")} />
          <textarea style={{ ...INPUT_STYLE, resize: "vertical", minHeight: 56 }}
            placeholder="Event Info (optional)" value={form.event_info} onChange={set("event_info")} />
          <textarea style={{ ...INPUT_STYLE, resize: "vertical", minHeight: 56 }}
            placeholder="Notes (optional)" value={form.notes} onChange={set("notes")} />
          <input type="number" min="0" step="0.01" style={INPUT_STYLE}
            placeholder="Quoted Price (optional)" value={form.quoted_price} onChange={set("quoted_price")} />
          {error && <p style={{ color: "#b00020", fontSize: "0.85rem" }}>{error}</p>}
          <div style={{ display: "flex", gap: "0.5rem", justifyContent: "flex-end" }}>
            <button type="button" style={BTN({ background: "#e5e7eb" })} onClick={onCancel} disabled={loading}>Discard</button>
            <button type="submit" style={BTN({ background: "#3b82f6", color: "#fff" })} disabled={loading}>
              {loading ? "Submitting..." : "Submit Request"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function CalendarPage() {
  const [farmhouses, setFarmhouses]       = useState([]);
  const [selectedFhId, setSelectedFhId]   = useState(null);
  const [events, setEvents]               = useState([]);
  const [error, setError]                 = useState(null);

  // Hold flow state
  const [selectInfo, setSelectInfo]       = useState(null);
  const [pendingHold, setPendingHold]     = useState(null);
  const [holdError, setHoldError]         = useState(null);
  const [holdLoading, setHoldLoading]     = useState(false);
  const [submitError, setSubmitError]     = useState(null);
  const [submitLoading, setSubmitLoading] = useState(false);

  const windowRef    = useRef({ start: null, end: null });
  const calendarRef  = useRef(null);
  const pollTimerRef = useRef(null);

  // ── Load active farmhouses on mount ──────────────────────────────────────
  useEffect(() => {
    listFarmhouses()
      .then((list) => {
        const active = list.filter((f) => f.status === "active");
        setFarmhouses(active);
        if (active.length > 0) setSelectedFhId(active[0].id);
      })
      .catch((e) => setError(e.message));
  }, []);

  // ── Fetch availability for current window ────────────────────────────────
  const fetchEvents = useCallback(async (fhId, start, end) => {
    if (!fhId || !start || !end) return;
    try {
      const bookings = await getAvailability(fhId, new Date(start), new Date(end));
      setEvents(bookings.map(bookingToEvent));
      setError(null);
    } catch (e) {
      setError(e.message);
    }
  }, []);

  // ── Re-fetch when selected farmhouse changes ──────────────────────────────
  useEffect(() => {
    const { start, end } = windowRef.current;
    if (selectedFhId && start && end) fetchEvents(selectedFhId, start, end);
  }, [selectedFhId, fetchEvents]);

  // ── Polling ───────────────────────────────────────────────────────────────
  useEffect(() => {
    function tick() {
      const { start, end } = windowRef.current;
      if (selectedFhId && start && end) fetchEvents(selectedFhId, start, end);
    }
    pollTimerRef.current = setInterval(tick, POLL_INTERVAL_MS);
    return () => clearInterval(pollTimerRef.current);
  }, [selectedFhId, fetchEvents]);

  // ── FullCalendar callbacks ─────────────────────────────────────────────────
  function handleDatesSet(info) {
    windowRef.current = { start: info.start, end: info.end };
    fetchEvents(selectedFhId, info.start, info.end);
  }

  function handleSelect(info) {
    setSelectInfo(info);
    setHoldError(null);
  }

  // ── Hold / Submit handlers ─────────────────────────────────────────────────
  async function handleConfirmHold() {
    if (!selectInfo || !selectedFhId) return;
    setHoldLoading(true);
    setHoldError(null);
    try {
      const booking = await createHold(selectedFhId, selectInfo.start, selectInfo.end);
      setPendingHold(booking);
      setSelectInfo(null);
    } catch (e) {
      setHoldError(e.message);
    } finally {
      setHoldLoading(false);
    }
  }

  async function handleSubmitBooking(details) {
    if (!pendingHold) return;
    setSubmitLoading(true);
    setSubmitError(null);
    try {
      await submitBooking(pendingHold.id, details);
      setPendingHold(null);
      const { start, end } = windowRef.current;
      if (selectedFhId && start && end) fetchEvents(selectedFhId, start, end);
    } catch (e) {
      setSubmitError(e.message);
    } finally {
      setSubmitLoading(false);
    }
  }

  // ── Legend ────────────────────────────────────────────────────────────────
  const legend = Object.entries(STATUS_COLOR).map(([st, color]) => (
    <span key={st} style={{ display: "inline-flex", alignItems: "center", gap: "0.3rem", marginRight: "1rem", fontSize: "0.8rem" }}>
      <span style={{ display: "inline-block", width: 12, height: 12, borderRadius: 3, background: color }} />
      {st.charAt(0).toUpperCase() + st.slice(1)}
    </span>
  ));

  const selectedFh = farmhouses.find((f) => f.id === selectedFhId);

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <section>
      <div style={{ display: "flex", alignItems: "center", gap: "1rem", marginBottom: "0.75rem", flexWrap: "wrap" }}>
        <label style={{ fontWeight: 600, fontSize: "0.9rem" }}>
          Farmhouse:{" "}
          <select value={selectedFhId ?? ""} onChange={(e) => setSelectedFhId(Number(e.target.value))}
            style={{ padding: "0.3rem 0.5rem", marginLeft: "0.25rem" }}>
            {farmhouses.length === 0 && <option value="">No active farmhouses</option>}
            {farmhouses.map((f) => (
              <option key={f.id} value={f.id}>{f.name}</option>
            ))}
          </select>
        </label>

        <div>{legend}</div>

        <span style={{ fontSize: "0.78rem", color: "#666" }}>
          Click &amp; drag on the calendar to place a hold
        </span>
      </div>

      {error && (
        <p style={{ color: "#b00020", marginBottom: "0.5rem", fontSize: "0.85rem" }}>{error}</p>
      )}

      <FullCalendar
        ref={calendarRef}
        plugins={[timeGridPlugin, dayGridPlugin, interactionPlugin]}
        initialView="timeGridWeek"
        headerToolbar={{
          left:   "prev,next today",
          center: "title",
          right:  "timeGridWeek,timeGridDay",
        }}
        timeZone="Asia/Karachi"
        events={events}
        datesSet={handleDatesSet}
        selectable={true}
        selectMirror={true}
        select={handleSelect}
        height="auto"
        allDaySlot={true}
        nowIndicator={true}
      />

      {selectInfo && selectedFh && (
        <HoldConfirmDialog
          selectInfo={selectInfo}
          farmhouseName={selectedFh.name}
          onConfirm={handleConfirmHold}
          onCancel={() => setSelectInfo(null)}
          loading={holdLoading}
          error={holdError}
        />
      )}

      {pendingHold && (
        <SubmitBookingForm
          booking={pendingHold}
          onSubmit={handleSubmitBooking}
          onCancel={() => setPendingHold(null)}
          loading={submitLoading}
          error={submitError}
        />
      )}
    </section>
  );
}
