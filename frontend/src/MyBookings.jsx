import { useEffect, useMemo, useState } from "react";
import {
  App as AntApp,
  Button,
  Card,
  Drawer,
  Input,
  Popconfirm,
  Segmented,
  Select,
  Skeleton,
} from "antd";
import { ReloadOutlined, SearchOutlined } from "@ant-design/icons";

import {
  listBookings,
  listFarmhouses,
  cancelBooking,
  withdrawBooking,
  requestCancel,
  confirmCancel,
} from "./api.js";
import {
  PageHeader,
  Stagger,
  StaggerItem,
  LedgerCard,
  EmptyNote,
  StatusTag,
} from "./ui.jsx";
import { bookingNo, fmtDateTime, fmtDuration, statusOf } from "./theme.js";

const SEGMENTS = [
  { label: "All", value: "all" },
  { label: "Holds", value: "hold" },
  { label: "Pending", value: "pending" },
  { label: "Confirmed", value: "booked" },
  { label: "Closed", value: "closed" },
];
const CLOSED = new Set(["canceled", "rejected", "expired"]);

function Row({ label, value, mono }) {
  if (value === null || value === undefined || value === "") return null;
  return (
    <div className="kv">
      <span className="k">{label}</span>
      <span className="v" style={mono ? { fontFamily: "var(--font-mono)" } : undefined}>{value}</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Detail drawer with role-aware actions
// ---------------------------------------------------------------------------
function DetailDrawer({ booking, user, open, onClose, onChanged }) {
  const { message } = AntApp.useApp();
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => setReason(""), [booking?.id]);
  if (!booking) return null;

  const isAdmin = user.role === "admin";
  const isOwner = booking.bookie_id === user.id;
  const { status, cancel_requested_at } = booking;

  async function run(fn, ...args) {
    setBusy(true);
    try {
      await fn(...args);
      message.success("Done.");
      onChanged();
      onClose();
    } catch (e) {
      message.error(e.message ?? "Action failed");
    } finally {
      setBusy(false);
    }
  }

  const needReason = (
    <Input.TextArea
      rows={2}
      value={reason}
      onChange={(e) => setReason(e.target.value)}
      placeholder="Reason"
      style={{ marginBottom: 10 }}
    />
  );

  const actions = [];
  if (isAdmin) {
    if (status === "pending" || status === "booked") {
      actions.push(
        <div key="admin-cancel">
          <Input.TextArea
            rows={2}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Reason (optional)"
            style={{ marginBottom: 10 }}
          />
          <Popconfirm
            title="Cancel this booking?"
            description="The slot will be freed."
            okText="Cancel booking"
            okButtonProps={{ danger: true }}
            onConfirm={() => run(cancelBooking, booking.id, reason)}
          >
            <Button danger block loading={busy}>Cancel booking</Button>
          </Popconfirm>
        </div>
      );
    }
    if (status === "booked" && cancel_requested_at) {
      actions.push(
        <Button key="confirm" type="primary" block loading={busy} onClick={() => run(confirmCancel, booking.id)} style={{ marginTop: 8 }}>
          Confirm cancellation request
        </Button>
      );
    }
  } else if (isOwner) {
    if (status === "hold" || status === "pending") {
      actions.push(
        <div key="withdraw">
          {needReason}
          <Button danger block loading={busy} onClick={() => run(withdrawBooking, booking.id, reason)}>
            Withdraw {status === "hold" ? "hold" : "request"}
          </Button>
        </div>
      );
    }
    if (status === "booked" && !cancel_requested_at) {
      actions.push(
        <div key="reqcancel">
          {needReason}
          <Button block loading={busy} onClick={() => {
            if (!reason.trim()) return message.warning("A reason is required.");
            run(requestCancel, booking.id, reason);
          }}>
            Request cancellation
          </Button>
        </div>
      );
    }
    if (status === "booked" && cancel_requested_at) {
      actions.push(<p key="req" className="muted" style={{ fontSize: 13 }}>Cancellation requested — awaiting admin confirmation.</p>);
    }
  }

  return (
    <Drawer
      title={
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span className="mono">{bookingNo(booking.id)}</span>
          <StatusTag status={booking.status} size="sm" />
        </div>
      }
      placement="right"
      size={Math.min(440, typeof window !== "undefined" ? window.innerWidth : 440)}
      open={open}
      onClose={onClose}
      footer={actions.length ? <div className="stack">{actions}</div> : null}
    >
      <div style={{ marginBottom: 14 }}>
        <div style={{ fontFamily: "var(--font-display)", fontSize: 22, fontWeight: 600 }}>
          {booking.client_name || "Untitled hold"}
        </div>
        {booking.event_type && <div className="muted">{booking.event_type}</div>}
      </div>

      <Row label="Estate" value={booking.farmhouse_name || `#${booking.farmhouse_id}`} />
      <Row label="Booked by" value={booking.bookie_name} />
      <Row label="Starts" value={fmtDateTime(booking.start_at)} />
      <Row label="Ends" value={fmtDateTime(booking.end_at)} />
      <Row label="Duration" value={fmtDuration(booking.start_at, booking.end_at)} />
      <Row label="Client contact" value={booking.client_contact} />
      <Row label="Quoted price" value={booking.quoted_price != null ? `PKR ${Number(booking.quoted_price).toLocaleString()}` : null} mono />
      {booking.event_info && <Row label="Details" value={booking.event_info} />}
      {booking.notes && <Row label="Notes" value={booking.notes} />}
      <Row label="Created" value={fmtDateTime(booking.created_at)} />
      {booking.reason && <Row label="Reason" value={booking.reason} />}
      {booking.cancel_reason && <Row label="Cancel reason" value={booking.cancel_reason} />}
      {booking.cancel_requested_at && <Row label="Cancellation requested" value={fmtDateTime(booking.cancel_requested_at)} />}
    </Drawer>
  );
}

// ---------------------------------------------------------------------------
// Bookings page
// ---------------------------------------------------------------------------
export default function BookingsPage({ user }) {
  const { message } = AntApp.useApp();
  const isAdmin = user.role === "admin";
  const [bookings, setBookings] = useState(null);
  const [farmhouses, setFarmhouses] = useState([]);
  const [seg, setSeg] = useState("all");
  const [fhFilter, setFhFilter] = useState("all");
  const [q, setQ] = useState("");
  const [active, setActive] = useState(null);

  async function load() {
    try {
      const data = await listBookings();
      setBookings(data);
    } catch (e) {
      message.error(e.message);
      setBookings([]);
    }
  }

  useEffect(() => {
    load();
    if (isAdmin) listFarmhouses({ includeDisabled: true }).then(setFarmhouses).catch(() => {});
  }, []); // eslint-disable-line

  const filtered = useMemo(() => {
    let list = bookings ?? [];
    if (seg === "closed") list = list.filter((b) => CLOSED.has(b.status));
    else if (seg !== "all") list = list.filter((b) => b.status === seg);
    if (isAdmin && fhFilter !== "all") list = list.filter((b) => b.farmhouse_id === fhFilter);
    if (q.trim()) {
      const t = q.trim().toLowerCase();
      list = list.filter(
        (b) =>
          (b.client_name || "").toLowerCase().includes(t) ||
          (b.farmhouse_name || "").toLowerCase().includes(t) ||
          (b.bookie_name || "").toLowerCase().includes(t) ||
          bookingNo(b.id).includes(t)
      );
    }
    return list;
  }, [bookings, seg, fhFilter, q, isAdmin]);

  return (
    <div>
      <PageHeader
        eyebrow={isAdmin ? "Every farmhouse" : "Your pipeline"}
        title={isAdmin ? "All bookings" : "My bookings"}
        subtitle={isAdmin ? "Browse every hold, request, and confirmed event — filter by farmhouse and open any entry for full details." : "Track your holds, pending requests, and confirmed events from one place."}
        extra={<Button icon={<ReloadOutlined />} onClick={load}>Refresh</Button>}
      />

      <Card styles={{ body: { padding: 12 } }} style={{ marginBottom: 16 }}>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
          <Segmented options={SEGMENTS} value={seg} onChange={setSeg} />
          {isAdmin && (
            <Select
              value={fhFilter}
              onChange={setFhFilter}
              style={{ minWidth: 180 }}
              options={[{ value: "all", label: "All farmhouses" }, ...farmhouses.map((f) => ({ value: f.id, label: f.name }))]}
            />
          )}
          <Input
            prefix={<SearchOutlined style={{ color: "var(--muted)" }} />}
            placeholder="Search name, venue, #number"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            allowClear
            style={{ maxWidth: 260, flex: "1 1 180px" }}
          />
        </div>
      </Card>

      {bookings === null ? (
        <Card><Skeleton active paragraph={{ rows: 4 }} /></Card>
      ) : filtered.length === 0 ? (
        <EmptyNote title="No bookings here" hint="Try a different filter, or place a hold from the calendar." />
      ) : (
        <Stagger>
          {filtered.map((b) => (
            <StaggerItem key={b.id}>
              <LedgerCard
                booking={b}
                showFarmhouse
                onClick={() => setActive(b)}
                footer={
                  b.status === "booked" && b.cancel_requested_at ? (
                    <span style={{ fontSize: 12.5, color: statusOf("rejected").color, fontWeight: 600 }}>
                      Cancellation requested
                    </span>
                  ) : null
                }
              />
            </StaggerItem>
          ))}
        </Stagger>
      )}

      <DetailDrawer
        booking={active}
        user={user}
        open={!!active}
        onClose={() => setActive(null)}
        onChanged={load}
      />
    </div>
  );
}
