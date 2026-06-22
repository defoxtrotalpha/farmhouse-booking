/**
 * MyBookings — bookings list + cancellation/withdraw actions (slice #26).
 *
 * Bookie view:
 *   - hold/pending  -> "Withdraw" button
 *   - booked (no cancel request)  -> "Request Cancellation" (with reason input)
 *   - booked (cancel requested)   -> shows "Cancellation requested" badge
 *   - canceled/rejected/expired   -> shows status only (read-only)
 *
 * Admin view (shown when user.role === 'admin'):
 *   - pending/booked -> "Cancel" button (with reason input)
 *   - booked + cancel_requested_at -> "Confirm Cancellation" button (in addition to Cancel)
 *   - canceled bookings are shown so admin can review history
 *
 * Canceled bookings are still shown in the list for history (but are grayed out).
 * The calendar availability endpoint already excludes non hold/pending/booked,
 * so canceled bookings drop off the calendar automatically.
 */
import { useEffect, useState } from "react";
import {
  listBookings,
  cancelBooking,
  withdrawBooking,
  requestCancel,
  confirmCancel,
} from "./api.js";

function fmtDt(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("en-PK", { timeZone: "Asia/Karachi" });
}

const STATUS_COLORS = {
  hold: "#888",
  pending: "#b45309",
  booked: "#1a7f37",
  canceled: "#b00020",
  rejected: "#b00020",
  expired: "#999",
};

// ---------------------------------------------------------------------------
// Row action cell — shows the relevant action(s) for a given booking
// ---------------------------------------------------------------------------
function ActionCell({ booking, user, onRefresh }) {
  const [msg, setMsg]         = useState(null);
  const [reason, setReason]   = useState("");
  const [working, setWorking] = useState(false);
  const [showInput, setShowInput] = useState(null); // 'withdraw'|'cancel'|'requestCancel'|null

  const isAdmin  = user.role === "admin";
  const isOwner  = booking.bookie_id === user.id;
  const { status, cancel_requested_at } = booking;

  async function doAction(fn, ...args) {
    setWorking(true);
    setMsg(null);
    try {
      await fn(...args);
      setMsg({ ok: true, text: "Done." });
      setShowInput(null);
      setReason("");
      setTimeout(onRefresh, 800);
    } catch (e) {
      setMsg({ ok: false, text: e.message ?? "Failed" });
    } finally {
      setWorking(false);
    }
  }

  // Terminal / read-only statuses
  if (["canceled", "rejected", "expired"].includes(status)) {
    return <span style={{ fontSize: "0.78rem", color: "#999" }}>—</span>;
  }

  const btnStyle = {
    cursor: "pointer",
    padding: "0.2rem 0.55rem",
    fontSize: "0.78rem",
    marginRight: "0.3rem",
  };

  const inputStyle = {
    padding: "0.2rem 0.4rem",
    fontSize: "0.78rem",
    marginRight: "0.3rem",
    width: "160px",
  };

  // ── Bookie actions ──────────────────────────────────────────────────────
  function BookieActions() {
    if (!isOwner && !isAdmin) return null;

    // hold or pending -> withdraw
    if (status === "hold" || status === "pending") {
      if (showInput === "withdraw") {
        return (
          <span>
            <input
              type="text"
              placeholder="Reason (optional)"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              style={inputStyle}
            />
            <button
              onClick={() => doAction(withdrawBooking, booking.id, reason)}
              disabled={working}
              style={btnStyle}
            >
              Confirm Withdraw
            </button>
            <button onClick={() => setShowInput(null)} style={btnStyle}>
              Cancel
            </button>
          </span>
        );
      }
      return (
        <button onClick={() => setShowInput("withdraw")} style={btnStyle}>
          Withdraw
        </button>
      );
    }

    // booked -> request cancellation (if not already requested)
    if (status === "booked" && !cancel_requested_at) {
      if (showInput === "requestCancel") {
        return (
          <span>
            <input
              type="text"
              placeholder="Reason (required)"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              style={inputStyle}
            />
            <button
              onClick={() => {
                if (!reason.trim()) {
                  setMsg({ ok: false, text: "Reason is required." });
                  return;
                }
                doAction(requestCancel, booking.id, reason);
              }}
              disabled={working}
              style={btnStyle}
            >
              Submit Request
            </button>
            <button onClick={() => setShowInput(null)} style={btnStyle}>
              Cancel
            </button>
          </span>
        );
      }
      return (
        <button onClick={() => setShowInput("requestCancel")} style={btnStyle}>
          Request Cancellation
        </button>
      );
    }

    // booked + cancel_requested_at set -> pending admin confirmation (bookie view)
    if (status === "booked" && cancel_requested_at) {
      return (
        <span style={{ fontSize: "0.78rem", color: "#b45309", fontStyle: "italic" }}>
          Cancellation requested
        </span>
      );
    }

    return null;
  }

  // ── Admin-only actions ──────────────────────────────────────────────────
  function AdminActions() {
    if (!isAdmin) return null;

    const items = [];

    // Admin can cancel any pending or booked booking
    if (status === "pending" || status === "booked") {
      if (showInput === "cancel") {
        items.push(
          <span key="cancel-input">
            <input
              type="text"
              placeholder="Cancel reason (required)"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              style={inputStyle}
            />
            <button
              onClick={() => {
                if (!reason.trim()) {
                  setMsg({ ok: false, text: "Reason is required." });
                  return;
                }
                doAction(cancelBooking, booking.id, reason);
              }}
              disabled={working}
              style={btnStyle}
            >
              Confirm Cancel
            </button>
            <button onClick={() => setShowInput(null)} style={btnStyle}>
              Back
            </button>
          </span>
        );
      } else {
        items.push(
          <button key="cancel-btn" onClick={() => setShowInput("cancel")} style={btnStyle}>
            Cancel
          </button>
        );
      }
    }

    // Admin can confirm a pending cancellation request on a booked event
    if (status === "booked" && cancel_requested_at) {
      items.push(
        <button
          key="confirm-cancel"
          onClick={() => doAction(confirmCancel, booking.id)}
          disabled={working}
          style={{ ...btnStyle, background: "#fff3cd" }}
        >
          Confirm Cancellation
        </button>
      );
    }

    return items.length > 0 ? <span>{items}</span> : null;
  }

  return (
    <span>
      {isAdmin ? <AdminActions /> : <BookieActions />}
      {msg && (
        <span
          style={{
            marginLeft: "0.3rem",
            fontSize: "0.75rem",
            color: msg.ok ? "#1a7f37" : "#b00020",
          }}
        >
          {msg.text}
        </span>
      )}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------
export default function MyBookings({ user }) {
  const [bookings, setBookings] = useState([]);
  const [loading, setLoading]   = useState(true);
  const [error, setError]       = useState(null);
  const [filter, setFilter]     = useState("all"); // 'all'|'active'|'canceled'

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const data = await listBookings();
      setBookings(data);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  const ACTIVE_STATUSES = new Set(["hold", "pending", "booked"]);
  const displayed = bookings.filter((b) => {
    if (filter === "active")   return ACTIVE_STATUSES.has(b.status);
    if (filter === "canceled") return b.status === "canceled";
    return true;
  });

  if (loading) return <p>Loading bookings…</p>;
  if (error)   return <p style={{ color: "#b00020" }}>Error: {error}</p>;

  return (
    <section>
      <div style={{ display: "flex", alignItems: "center", gap: "1rem", marginBottom: "0.75rem" }}>
        <h2 style={{ margin: 0, fontSize: "1rem" }}>
          {user.role === "admin" ? "All Bookings" : "My Bookings"}
        </h2>
        <button onClick={load} style={{ cursor: "pointer", fontSize: "0.8rem" }}>Refresh</button>
        <span style={{ fontSize: "0.8rem" }}>
          Filter:&nbsp;
          {["all", "active", "canceled"].map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              style={{
                cursor: "pointer",
                marginRight: "0.25rem",
                padding: "0.15rem 0.5rem",
                fontSize: "0.78rem",
                fontWeight: filter === f ? 700 : 400,
                background: filter === f ? "#e5e5e5" : "none",
                border: "1px solid #ccc",
                borderRadius: "3px",
              }}
            >
              {f.charAt(0).toUpperCase() + f.slice(1)}
            </button>
          ))}
        </span>
      </div>

      {displayed.length === 0 && (
        <p style={{ color: "#555", fontSize: "0.875rem" }}>No bookings to show.</p>
      )}

      {displayed.length > 0 && (
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.85rem" }}>
          <thead>
            <tr style={{ borderBottom: "2px solid #e5e5e5", textAlign: "left" }}>
              <th style={{ padding: "0.35rem 0.5rem" }}>#</th>
              <th style={{ padding: "0.35rem 0.5rem" }}>FH</th>
              <th style={{ padding: "0.35rem 0.5rem" }}>Status</th>
              <th style={{ padding: "0.35rem 0.5rem" }}>Start (PKT)</th>
              <th style={{ padding: "0.35rem 0.5rem" }}>End (PKT)</th>
              <th style={{ padding: "0.35rem 0.5rem" }}>Client</th>
              <th style={{ padding: "0.35rem 0.5rem" }}>Notes</th>
              <th style={{ padding: "0.35rem 0.5rem" }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {displayed.map((b) => {
              const isCanceled = b.status === "canceled";
              const hasCancelReq = b.status === "booked" && b.cancel_requested_at;
              return (
                <tr
                  key={b.id}
                  style={{
                    borderBottom: "1px solid #f0f0f0",
                    opacity: isCanceled ? 0.55 : 1,
                  }}
                >
                  <td style={{ padding: "0.35rem 0.5rem" }}>{b.id}</td>
                  <td style={{ padding: "0.35rem 0.5rem" }}>{b.farmhouse_id}</td>
                  <td style={{ padding: "0.35rem 0.5rem" }}>
                    <span style={{ color: STATUS_COLORS[b.status] ?? "#333", fontWeight: 600 }}>
                      {b.status}
                    </span>
                    {hasCancelReq && (
                      <span
                        style={{
                          marginLeft: "0.3rem",
                          fontSize: "0.72rem",
                          background: "#fff3cd",
                          color: "#856404",
                          padding: "0.1rem 0.3rem",
                          borderRadius: "3px",
                          border: "1px solid #ffc107",
                        }}
                      >
                        cancel requested
                      </span>
                    )}
                    {isCanceled && b.cancel_reason && (
                      <span
                        style={{ marginLeft: "0.3rem", fontSize: "0.72rem", color: "#999" }}
                        title={b.cancel_reason}
                      >
                        ({b.cancel_reason.length > 30 ? b.cancel_reason.slice(0, 30) + "…" : b.cancel_reason})
                      </span>
                    )}
                  </td>
                  <td style={{ padding: "0.35rem 0.5rem" }}>{fmtDt(b.start_at)}</td>
                  <td style={{ padding: "0.35rem 0.5rem" }}>{fmtDt(b.end_at)}</td>
                  <td style={{ padding: "0.35rem 0.5rem" }}>{b.client_name ?? "—"}</td>
                  <td style={{ padding: "0.35rem 0.5rem" }}>{b.event_type ?? "—"}</td>
                  <td style={{ padding: "0.35rem 0.5rem" }}>
                    <ActionCell booking={b} user={user} onRefresh={load} />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </section>
  );
}
