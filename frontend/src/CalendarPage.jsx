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
import timeGridPlugin from "@fullcalendar/timegrid";
import dayGridPlugin from "@fullcalendar/daygrid";

import { listFarmhouses, getAvailability } from "./api.js";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const POLL_INTERVAL_MS = 15_000; // 15 s — change here to reconfigure

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

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function CalendarPage() {
  const [farmhouses, setFarmhouses]     = useState([]);
  const [selectedFhId, setSelectedFhId] = useState(null);
  const [events, setEvents]             = useState([]);
  const [error, setError]               = useState(null);

  // Refs so the poll callback always has the current window / farmhouse
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
  const fetchEvents = useCallback(
    async (fhId, start, end) => {
      if (!fhId || !start || !end) return;
      try {
        const bookings = await getAvailability(fhId, new Date(start), new Date(end));
        setEvents(bookings.map(bookingToEvent));
        setError(null);
      } catch (e) {
        setError(e.message);
      }
    },
    []
  );

  // ── Re-fetch when selected farmhouse changes ──────────────────────────────
  useEffect(() => {
    const { start, end } = windowRef.current;
    if (selectedFhId && start && end) {
      fetchEvents(selectedFhId, start, end);
    }
  }, [selectedFhId, fetchEvents]);

  // ── Polling ───────────────────────────────────────────────────────────────
  useEffect(() => {
    function tick() {
      const { start, end } = windowRef.current;
      if (selectedFhId && start && end) {
        fetchEvents(selectedFhId, start, end);
      }
    }
    pollTimerRef.current = setInterval(tick, POLL_INTERVAL_MS);
    return () => clearInterval(pollTimerRef.current);
  }, [selectedFhId, fetchEvents]);

  // ── FullCalendar datesSet callback (fires on view/nav change) ────────────
  function handleDatesSet(info) {
    windowRef.current = { start: info.start, end: info.end };
    fetchEvents(selectedFhId, info.start, info.end);
  }

  // ── Legend ────────────────────────────────────────────────────────────────
  const legend = Object.entries(STATUS_COLOR).map(([st, color]) => (
    <span
      key={st}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "0.3rem",
        marginRight: "1rem",
        fontSize: "0.8rem",
      }}
    >
      <span
        style={{
          display: "inline-block",
          width: 12,
          height: 12,
          borderRadius: 3,
          background: color,
        }}
      />
      {st.charAt(0).toUpperCase() + st.slice(1)}
    </span>
  ));

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <section>
      <div style={{ display: "flex", alignItems: "center", gap: "1rem", marginBottom: "0.75rem", flexWrap: "wrap" }}>
        <label style={{ fontWeight: 600, fontSize: "0.9rem" }}>
          Farmhouse:{" "}
          <select
            value={selectedFhId ?? ""}
            onChange={(e) => setSelectedFhId(Number(e.target.value))}
            style={{ padding: "0.3rem 0.5rem", marginLeft: "0.25rem" }}
          >
            {farmhouses.length === 0 && <option value="">No active farmhouses</option>}
            {farmhouses.map((f) => (
              <option key={f.id} value={f.id}>
                {f.name}
              </option>
            ))}
          </select>
        </label>

        <div>{legend}</div>
      </div>

      {error && (
        <p style={{ color: "#b00020", marginBottom: "0.5rem", fontSize: "0.85rem" }}>
          {error}
        </p>
      )}

      <FullCalendar
        ref={calendarRef}
        plugins={[timeGridPlugin, dayGridPlugin]}
        initialView="timeGridWeek"
        headerToolbar={{
          left:   "prev,next today",
          center: "title",
          right:  "timeGridWeek,timeGridDay",
        }}
        timeZone="Asia/Karachi"
        events={events}
        datesSet={handleDatesSet}
        height="auto"
        allDaySlot={true}
        nowIndicator={true}
      />
    </section>
  );
}
