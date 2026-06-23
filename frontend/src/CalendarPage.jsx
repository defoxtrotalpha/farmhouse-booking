import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import FullCalendar from "@fullcalendar/react";
import dayGridPlugin from "@fullcalendar/daygrid";
import interactionPlugin from "@fullcalendar/interaction";
import dayjs from "dayjs";
import {
  App as AntApp,
  Button,
  Card,
  DatePicker,
  Drawer,
  Form,
  Input,
  InputNumber,
  Select,
  Space,
  Tag,
} from "antd";
import {
  ClockCircleOutlined,
  PlusOutlined,
  ThunderboltOutlined,
  SendOutlined,
} from "@ant-design/icons";

import {
  listFarmhouses,
  getAvailability,
  createHold,
  submitBooking,
  directBook,
} from "./api.js";
import { PageHeader } from "./ui.jsx";
import { STATUS, statusOf, fmtDuration } from "./theme.js";

const POLL_INTERVAL_MS = 15_000;

function bookingToEvent(b) {
  const s = statusOf(b.status);
  const isPast = dayjs(b.end_at).isBefore(dayjs());
  return {
    id: String(b.id),
    title: s.label,
    start: b.start_at,
    end: b.end_at,
    backgroundColor: isPast ? "#b2d8b2" : s.dot,
    borderColor: "transparent",
    textColor: isPast ? "#3a6b3a" : "#fff",
    extendedProps: { status: b.status, start_at: b.start_at, end_at: b.end_at, isPast },
  };
}

function renderEventContent(arg) {
  const { status, isPast } = arg.event.extendedProps;
  const s = statusOf(status);
  const bg = isPast ? "#b2d8b2" : s.dot;
  const text = isPast ? "#3a6b3a" : "#fff";
  const dot = isPast ? "rgba(58,107,58,0.35)" : "rgba(255,255,255,0.75)";
  return (
    <div style={{
      display: "flex",
      alignItems: "center",
      gap: 5,
      background: bg,
      borderRadius: 999,
      padding: "2px 8px 2px 5px",
      overflow: "hidden",
      width: "100%",
      boxShadow: "0 1px 3px rgba(0,0,0,0.18)",
    }}>
      <span style={{
        width: 7, height: 7, borderRadius: "50%",
        background: dot,
        flexShrink: 0,
        display: "block",
      }} />
      <span style={{
        color: text,
        fontSize: 10.5,
        fontWeight: 700,
        letterSpacing: "0.02em",
        overflow: "hidden",
        textOverflow: "ellipsis",
        whiteSpace: "nowrap",
        lineHeight: 1.3,
        fontFamily: "var(--font-body)",
      }}>
        {s.label}
      </span>
    </div>
  );
}

const QUICK = [
  { label: "1 hr", mins: 60 },
  { label: "2 hr", mins: 120 },
  { label: "4 hr", mins: 240 },
  { label: "All day", mins: 600 },
];

// ---------------------------------------------------------------------------
// Booking sheet — editable times + optional client details + role actions
// ---------------------------------------------------------------------------
function BookingSheet({ open, onClose, farmhouses, fhId, setFhId, initial, user, onDone }) {
  const { message } = AntApp.useApp();
  const [form] = Form.useForm();
  const [start, setStart] = useState(initial.start);
  const [end, setEnd] = useState(initial.end);
  const [busy, setBusy] = useState(false);
  const isAdmin = user.role === "admin";

  useEffect(() => {
    setStart(initial.start);
    setEnd(initial.end);
  }, [initial.start, initial.end]);

  function applyDuration(mins) {
    setEnd(start.add(mins, "minute"));
  }

  function validTimes() {
    if (!start || !end) return "Pick a start and end time.";
    if (!end.isAfter(start)) return "End time must be after the start time.";
    if (!start.isAfter(dayjs())) return "Start time must be in the future.";
    return null;
  }

  async function runHold() {
    const err = validTimes();
    if (err) return message.warning(err);
    setBusy(true);
    try {
      await createHold(fhId, start.toDate(), end.toDate());
      message.success("Hold placed — submit details when you're ready.");
      onDone();
      onClose();
    } catch (e) {
      message.error(e.message ?? "Could not place the hold");
    } finally {
      setBusy(false);
    }
  }

  async function runSubmit() {
    const err = validTimes();
    if (err) return message.warning(err);
    let values;
    try {
      values = await form.validateFields();
    } catch {
      return;
    }
    setBusy(true);
    try {
      const hold = await createHold(fhId, start.toDate(), end.toDate());
      await submitBooking(hold.id, {
        client_name: values.client_name,
        client_contact: values.client_contact,
        event_type: values.event_type || undefined,
        event_info: values.event_info || undefined,
        notes: values.notes || undefined,
        quoted_price: values.quoted_price ?? undefined,
      });
      message.success("Request submitted for approval.");
      onDone();
      onClose();
    } catch (e) {
      message.error(e.message ?? "Could not submit the request");
    } finally {
      setBusy(false);
    }
  }

  async function runDirect() {
    const err = validTimes();
    if (err) return message.warning(err);
    let values;
    try {
      values = await form.validateFields();
    } catch {
      return;
    }
    setBusy(true);
    try {
      await directBook({
        farmhouse_id: fhId,
        start_at: start.toDate(),
        end_at: end.toDate(),
        client_name: values.client_name,
        client_contact: values.client_contact,
        event_type: values.event_type || undefined,
        event_info: values.event_info || undefined,
        notes: values.notes || undefined,
        quoted_price: values.quoted_price ?? undefined,
      });
      message.success("Booking confirmed.");
      onDone();
      onClose();
    } catch (e) {
      if (e.conflict_booking_id) {
        message.error(`Slot already confirmed (booking #${e.conflict_booking_id}).`);
      } else {
        message.error(e.message ?? "Could not create the booking");
      }
    } finally {
      setBusy(false);
    }
  }

  const fh = farmhouses.find((f) => f.id === fhId);

  return (
    <Drawer
      title={isAdmin ? "New booking" : "Reserve a slot"}
      placement="bottom"
      size="auto"
      open={open}
      onClose={onClose}
      styles={{ body: { paddingBottom: 24, maxHeight: "82vh" }, footer: { padding: 14 } }}
      footer={
        <Space wrap style={{ width: "100%", justifyContent: "flex-end" }}>
          <Button onClick={runHold} loading={busy} icon={<ClockCircleOutlined />}>
            Place hold
          </Button>
          {isAdmin ? (
            <>
              <Button onClick={runSubmit} loading={busy} icon={<SendOutlined />}>
                Submit request
              </Button>
              <Button type="primary" onClick={runDirect} loading={busy} icon={<ThunderboltOutlined />}>
                Book directly
              </Button>
            </>
          ) : (
            <Button type="primary" onClick={runSubmit} loading={busy} icon={<SendOutlined />}>
              Submit request
            </Button>
          )}
        </Space>
      }
    >
      <div style={{ maxWidth: 560, margin: "0 auto" }}>
        <div style={{ marginBottom: 14 }}>
          <div className="eyebrow" style={{ marginBottom: 6 }}>Estate</div>
          <Select
            value={fhId}
            onChange={setFhId}
            options={farmhouses.map((f) => ({ value: f.id, label: f.name }))}
            size="large"
            style={{ width: "100%" }}
          />
        </div>

        <div className="two-col">
          <div>
            <div className="eyebrow" style={{ marginBottom: 6 }}>Starts</div>
            <DatePicker
              value={start}
              onChange={(v) => v && setStart(v)}
              showTime={{ format: "hh:mm A", minuteStep: 15 }}
              format="DD MMM · hh:mm A"
              allowClear={false}
              size="large"
              style={{ width: "100%" }}
            />
          </div>
          <div>
            <div className="eyebrow" style={{ marginBottom: 6 }}>Ends</div>
            <DatePicker
              value={end}
              onChange={(v) => v && setEnd(v)}
              showTime={{ format: "hh:mm A", minuteStep: 15 }}
              format="DD MMM · hh:mm A"
              allowClear={false}
              size="large"
              style={{ width: "100%" }}
            />
          </div>
        </div>

        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 12, alignItems: "center" }}>
          <span className="muted" style={{ fontSize: 13 }}>Quick set:</span>
          {QUICK.map((q) => (
            <Tag.CheckableTag key={q.label} checked={false} onChange={() => applyDuration(q.mins)} style={{ border: "1px solid var(--hairline)", padding: "3px 12px", borderRadius: 999, cursor: "pointer" }}>
              {q.label}
            </Tag.CheckableTag>
          ))}
          <span style={{ marginLeft: "auto", fontSize: 12, fontWeight: 600, color: "var(--brass)", background: "#f7efdc", borderRadius: 999, padding: "2px 10px" }}>
            {start && end && end.isAfter(start) ? fmtDuration(start.toISOString(), end.toISOString()) : "—"}
          </span>
        </div>

        <div style={{ marginTop: 20 }}>
          <div className="eyebrow" style={{ marginBottom: 10 }}>
            Client details {isAdmin ? "" : "(required to submit)"}
          </div>
          <Form form={form} layout="vertical" requiredMark={false}>
            <div className="two-col">
              <Form.Item name="client_name" label="Client name" rules={[{ required: true, message: "Who is this for?" }]}>
                <Input placeholder="e.g. Ayesha Khan" />
              </Form.Item>
              <Form.Item name="client_contact" label="Contact" rules={[{ required: true, message: "Add a phone or email" }]}>
                <Input placeholder="Phone or email" />
              </Form.Item>
            </div>
            <div className="two-col">
              <Form.Item name="event_type" label="Event type">
                <Input placeholder="Wedding, mehndi, dinner…" />
              </Form.Item>
              <Form.Item
                name="quoted_price"
                label="Quoted price (PKR)"
                rules={isAdmin ? [] : [{ required: true, message: "Enter the quoted price" }]}
              >
                <InputNumber min={0} step={1000} style={{ width: "100%" }} placeholder={isAdmin ? "Optional" : "Required"} controls={false} />
              </Form.Item>
            </div>
            <Form.Item name="event_info" label="Event details">
              <Input.TextArea rows={2} placeholder="Guest count, timings, requests…" />
            </Form.Item>
            <Form.Item name="notes" label="Internal notes">
              <Input.TextArea rows={2} placeholder="Only visible to staff" />
            </Form.Item>
          </Form>
        </div>
        {fh?.buffer_minutes > 0 && (
          <p className="muted" style={{ fontSize: 12.5 }}>
            A {fh.buffer_minutes}-minute turnover buffer applies around this booking.
          </p>
        )}
      </div>
    </Drawer>
  );
}

// ---------------------------------------------------------------------------
// Calendar page
// ---------------------------------------------------------------------------
export default function CalendarPage({ user }) {
  const { message } = AntApp.useApp();
  const [farmhouses, setFarmhouses] = useState([]);
  const [selectedFhId, setSelectedFhId] = useState(null);
  const [events, setEvents] = useState([]);
  const [view, setView] = useState("dayGridMonth");

  const [sheet, setSheet] = useState(null); // { start: dayjs, end: dayjs }

  const windowRef = useRef({ start: null, end: null });
  const calendarRef = useRef(null);
  const pollTimerRef = useRef(null);

  // Contain the page to the viewport on desktop (no outer scroll)
  useEffect(() => {
    document.documentElement.classList.add("cal-active");
    return () => document.documentElement.classList.remove("cal-active");
  }, []);

  useEffect(() => {
    listFarmhouses()
      .then((list) => {
        const active = list.filter((f) => f.status === "active");
        setFarmhouses(active);
        if (active.length > 0) setSelectedFhId(active[0].id);
      })
      .catch((e) => message.error(e.message));
  }, [message]);

  const fetchEvents = useCallback(async (fhId, start, end) => {
    if (!fhId || !start || !end) return;
    try {
      const bookings = await getAvailability(fhId, new Date(start), new Date(end));
      setEvents(bookings.map(bookingToEvent));
    } catch (e) {
      message.error(e.message);
    }
  }, [message]);

  useEffect(() => {
    const { start, end } = windowRef.current;
    if (selectedFhId && start && end) fetchEvents(selectedFhId, start, end);
  }, [selectedFhId, fetchEvents]);

  useEffect(() => {
    function tick() {
      const { start, end } = windowRef.current;
      if (selectedFhId && start && end) fetchEvents(selectedFhId, start, end);
    }
    pollTimerRef.current = setInterval(tick, POLL_INTERVAL_MS);
    return () => clearInterval(pollTimerRef.current);
  }, [selectedFhId, fetchEvents]);

  function handleDatesSet(info) {
    windowRef.current = { start: info.start, end: info.end };
    fetchEvents(selectedFhId, info.start, info.end);
  }

  function handleSelect(info) {
    if (!selectedFhId) {
      message.warning("Add an active estate first.");
      return;
    }
    // FullCalendar gives a default 30-min selection on tap; it's fully editable
    // in the sheet (resolves the "stuck at 30 min" issue).
    const start = dayjs(info.start);
    let end = dayjs(info.end);
    if (!end.isAfter(start)) end = start.add(2, "hour");
    setSheet({ start, end });
  }

  function refresh() {
    const { start, end } = windowRef.current;
    if (selectedFhId && start && end) fetchEvents(selectedFhId, start, end);
  }

  const legend = useMemo(
    () =>
      ["hold", "pending", "booked"].map((st) => (
        <span key={st} style={{ display: "inline-flex", alignItems: "center", gap: 8, fontSize: 13, color: "var(--ink)" }}>
          <span style={{ width: 10, height: 10, borderRadius: 3, background: STATUS[st].dot }} />
          {STATUS[st].label}
        </span>
      )),
    []
  );

  const selectedFh = useMemo(
    () => farmhouses.find((f) => f.id === selectedFhId) ?? null,
    [farmhouses, selectedFhId]
  );

  // Upcoming occupied slots within the loaded window, soonest first.
  const upcoming = useMemo(() => {
    const now = dayjs();
    return events
      .map((e) => ({ ...e, _start: dayjs(e.start), _end: dayjs(e.end) }))
      .filter((e) => e._end.isAfter(now))
      .sort((a, b) => a._start.valueOf() - b._start.valueOf())
      .slice(0, 8);
  }, [events]);

  function changeView(v) {
    setView(v);
    calendarRef.current?.getApi().changeView(v);
  }

  const calendarCard = (
    <Card styles={{ body: { padding: 0, height: "100%" } }} className="cal-grid-card">
      <FullCalendar
        ref={calendarRef}
        plugins={[dayGridPlugin, interactionPlugin]}
        initialView="dayGridMonth"
        headerToolbar={{ left: "today prevYear,prev", center: "title", right: "next,nextYear" }}
        timeZone="Asia/Karachi"
        events={events}
        datesSet={handleDatesSet}
        selectable
        selectMirror
        select={handleSelect}
        longPressDelay={120}
        selectLongPressDelay={120}
        height="100%"
        expandRows
        eventContent={renderEventContent}
        dayMaxEvents={3}
        moreLinkClick="popover"
      />
    </Card>
  );

  return (
    <div>
      <PageHeader
        title="Calendar"
        subtitle={user.role === "admin" ? "Tap any date to book directly or place a hold." : "Tap a date to place a hold, then submit your client's details."}
      />

      <Card styles={{ body: { padding: 12 } }} style={{ marginBottom: 14 }}>
        <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
          <Select
            value={selectedFhId ?? undefined}
            onChange={setSelectedFhId}
            placeholder="Select estate"
            style={{ minWidth: 200, flex: "1 1 220px" }}
            size="large"
            options={farmhouses.map((f) => ({ value: f.id, label: f.name }))}
            notFoundContent="No active estates"
          />
        </div>
      </Card>

      <div className="cal-layout">
        <div className="cal-main">{calendarCard}</div>

        <aside className="cal-side">
          <Card styles={{ body: { padding: 16 } }} className="cal-side-card">
            <div className="eyebrow" style={{ marginBottom: 8 }}>Estate</div>
            {selectedFh ? (
              <>
                <div style={{ fontFamily: "var(--font-display)", fontSize: 18, fontWeight: 600, color: "var(--ink)" }}>
                  {selectedFh.name}
                </div>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 8 }}>
                  {selectedFh.capacity != null && (
                    <Tag variant="filled" style={{ background: "var(--linen)" }}>
                      Capacity {selectedFh.capacity}
                    </Tag>
                  )}
                  {selectedFh.buffer_minutes > 0 && (
                    <Tag variant="filled" style={{ background: "var(--linen)" }}>
                      {selectedFh.buffer_minutes}-min buffer
                    </Tag>
                  )}
                </div>
              </>
            ) : (
              <div className="muted" style={{ fontSize: 13 }}>No active estate selected.</div>
            )}
          </Card>

          <Card styles={{ body: { padding: 16 } }} className="cal-side-card">
            <div className="eyebrow" style={{ marginBottom: 12 }}>Legend</div>
            <div className="cal-legend-list" style={{ display: "flex", flexDirection: "column", gap: 10 }}>{legend}</div>
          </Card>

          <Card styles={{ body: { padding: 16 } }} className="cal-side-card">
            <div className="eyebrow" style={{ marginBottom: 12 }}>Upcoming</div>
            {upcoming.length === 0 ? (
              <div className="muted" style={{ fontSize: 13 }}>
                Nothing scheduled in this range. Tap a slot to start a booking.
              </div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                {upcoming.map((e) => {
                  const sameDay = e._start.isSame(e._end, "day");
                  return (
                    <div key={e.id} className="cal-upcoming-row">
                      <span className="cal-upcoming-dot" style={{ background: e.backgroundColor }} />
                      <div style={{ minWidth: 0, flex: 1 }}>
                        <div style={{ fontSize: 13.5, fontWeight: 600, color: "var(--ink)" }}>
                          {e._start.format("ddd, MMM D")}
                        </div>
                        <div className="muted" style={{ fontSize: 12.5 }}>
                          {e._start.format("h:mm A")} – {sameDay ? e._end.format("h:mm A") : e._end.format("MMM D, h:mm A")}
                        </div>
                      </div>
                      <Tag
                        variant="filled"
                        style={{ background: "var(--linen)", color: "var(--muted)", margin: 0, textTransform: "capitalize" }}
                      >
                        {e.extendedProps.status}
                      </Tag>
                    </div>
                  );
                })}
              </div>
            )}
          </Card>
        </aside>
      </div>

      {sheet && (
        <BookingSheet
          open
          onClose={() => setSheet(null)}
          farmhouses={farmhouses}
          fhId={selectedFhId}
          setFhId={setSelectedFhId}
          initial={sheet}
          user={user}
          onDone={refresh}
        />
      )}

      <p className="muted" style={{ fontSize: 12.5, marginTop: 12, textAlign: "center" }}>
        <PlusOutlined /> Tip: tap a slot, then fine-tune the start and end times in the sheet.
      </p>
    </div>
  );
}
