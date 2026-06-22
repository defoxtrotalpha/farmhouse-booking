/**
 * ApproveQueue — Admin view listing PENDING bookings with an Approve action.
 *
 * Slice #23: approve -> booked (+ 409 conflict feedback).
 * Slice #24: after approve, fetch /conflicts and show overlapping losers
 *            with a reason input + Reject Selected button (calls /reject-batch).
 *            On 409 conflict from /approve, offer to reject the pending that failed.
 */
import { useEffect, useState } from "react";
import { listBookings, approveBooking, getConflicts, rejectBatch, rejectBooking } from "./api.js";

function fmtDt(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("en-PK", { timeZone: "Asia/Karachi" });
}

// ---------------------------------------------------------------------------
// ConflictPanel — shown beneath a row after a successful approve
// ---------------------------------------------------------------------------
function ConflictPanel({ bookedId, onDone }) {
  const [losers, setLosers]       = useState(null);   // null=loading
  const [reason, setReason]       = useState("");
  const [selected, setSelected]   = useState([]);      // ids to reject
  const [status, setStatus]       = useState(null);    // { ok, text }
  const [working, setWorking]     = useState(false);

  useEffect(() => {
    getConflicts(bookedId)
      .then((data) => {
        setLosers(data);
        setSelected(data.map((b) => b.id));  // pre-select all
      })
      .catch(() => setLosers([]));
  }, [bookedId]);

  if (losers === null) return <p style={{ margin: "0.4rem 0", fontSize: "0.8rem" }}>Loading conflicts…</p>;
  if (losers.length === 0) return <p style={{ margin: "0.4rem 0", fontSize: "0.8rem", color: "#555" }}>No overlapping requests to reject.</p>;

  function toggleSelect(id) {
    setSelected((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );
  }

  async function handleRejectSelected() {
    if (!reason.trim()) { setStatus({ ok: false, text: "Enter a rejection reason first." }); return; }
    if (selected.length === 0) { setStatus({ ok: false, text: "Select at least one booking to reject." }); return; }
    setWorking(true);
    setStatus(null);
    try {
      const result = await rejectBatch(selected, reason);
      setStatus({ ok: true, text: `Rejected ${result.rejected.length} booking(s).` });
      setTimeout(onDone, 1200);
    } catch (e) {
      setStatus({ ok: false, text: e.message });
    } finally {
      setWorking(false);
    }
  }

  return (
    <div style={{ marginTop: "0.5rem", padding: "0.5rem", background: "#fff8e1", borderRadius: "4px", fontSize: "0.8rem" }}>
      <strong>Overlapping requests ({losers.length}) — reject the losers:</strong>
      <table style={{ width: "100%", borderCollapse: "collapse", marginTop: "0.3rem" }}>
        <thead>
          <tr style={{ textAlign: "left" }}>
            <th style={{ padding: "0.2rem 0.4rem" }}>☑</th>
            <th style={{ padding: "0.2rem 0.4rem" }}>#</th>
            <th style={{ padding: "0.2rem 0.4rem" }}>Status</th>
            <th style={{ padding: "0.2rem 0.4rem" }}>Start (PKT)</th>
            <th style={{ padding: "0.2rem 0.4rem" }}>End (PKT)</th>
          </tr>
        </thead>
        <tbody>
          {losers.map((b) => (
            <tr key={b.id}>
              <td style={{ padding: "0.2rem 0.4rem" }}>
                <input type="checkbox" checked={selected.includes(b.id)}
                  onChange={() => toggleSelect(b.id)} />
              </td>
              <td style={{ padding: "0.2rem 0.4rem" }}>{b.id}</td>
              <td style={{ padding: "0.2rem 0.4rem" }}>{b.status}</td>
              <td style={{ padding: "0.2rem 0.4rem" }}>{fmtDt(b.start_at)}</td>
              <td style={{ padding: "0.2rem 0.4rem" }}>{fmtDt(b.end_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div style={{ marginTop: "0.4rem", display: "flex", gap: "0.5rem", alignItems: "center" }}>
        <input
          type="text"
          placeholder="Rejection reason (required)"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          style={{ flex: 1, padding: "0.2rem 0.4rem", fontSize: "0.8rem" }}
        />
        <button onClick={handleRejectSelected} disabled={working}
          style={{ cursor: "pointer", padding: "0.2rem 0.6rem", fontSize: "0.8rem" }}>
          Reject Selected
        </button>
      </div>
      {status && (
        <p style={{ margin: "0.3rem 0 0", color: status.ok ? "#1a7f37" : "#b00020" }}>{status.text}</p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// ConflictRejectOffer — shown when /approve returns 409 conflict
// ---------------------------------------------------------------------------
function ConflictRejectOffer({ pendingId, conflictBookedId, onDone }) {
  const [reason, setReason]   = useState("");
  const [status, setStatus]   = useState(null);
  const [working, setWorking] = useState(false);

  async function handleReject() {
    if (!reason.trim()) { setStatus({ ok: false, text: "Enter a rejection reason." }); return; }
    setWorking(true);
    setStatus(null);
    try {
      await rejectBooking(pendingId, reason);
      setStatus({ ok: true, text: `Booking #${pendingId} rejected.` });
      setTimeout(onDone, 1200);
    } catch (e) {
      setStatus({ ok: false, text: e.message });
    } finally {
      setWorking(false);
    }
  }

  return (
    <div style={{ marginTop: "0.4rem", padding: "0.4rem", background: "#fce4ec", borderRadius: "4px", fontSize: "0.8rem" }}>
      Slot already confirmed as booking #{conflictBookedId}. Reject this request?
      <div style={{ display: "flex", gap: "0.4rem", marginTop: "0.3rem", alignItems: "center" }}>
        <input type="text" placeholder="Reason" value={reason} onChange={(e) => setReason(e.target.value)}
          style={{ flex: 1, padding: "0.2rem 0.4rem", fontSize: "0.8rem" }} />
        <button onClick={handleReject} disabled={working}
          style={{ cursor: "pointer", padding: "0.2rem 0.5rem", fontSize: "0.8rem" }}>
          Reject #{pendingId}
        </button>
      </div>
      {status && <p style={{ margin: "0.2rem 0 0", color: status.ok ? "#1a7f37" : "#b00020" }}>{status.text}</p>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// ApproveQueue — main component
// ---------------------------------------------------------------------------
export default function ApproveQueue() {
  const [bookings, setBookings]     = useState([]);
  const [loading, setLoading]       = useState(true);
  const [error, setError]           = useState(null);
  // per-id state: { ok, text, panel: 'conflicts'|'conflict_offer'|null, bookedId, conflictBookedId }
  const [actionMsg, setActionMsg]   = useState({});

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const data = await listBookings({ status: "pending" });
      setBookings(data);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  async function handleApprove(id) {
    setActionMsg((prev) => ({ ...prev, [id]: null }));
    try {
      const approved = await approveBooking(id);
      setActionMsg((prev) => ({
        ...prev,
        [id]: { ok: true, text: "Approved — now Booked.", panel: "conflicts", bookedId: approved.id },
      }));
      // Remove from pending list after short delay so user sees conflict panel
      setTimeout(() => setBookings((prev) => prev.filter((b) => b.id !== id)), 1500);
    } catch (e) {
      if (e.status === 409 && e.conflict_booking_id != null) {
        setActionMsg((prev) => ({
          ...prev,
          [id]: {
            ok: false,
            text: `Conflict with booking #${e.conflict_booking_id}.`,
            panel: "conflict_offer",
            conflictBookedId: e.conflict_booking_id,
          },
        }));
      } else {
        const msg = e.message ?? "Approval failed";
        setActionMsg((prev) => ({ ...prev, [id]: { ok: false, text: msg, panel: null } }));
      }
    }
  }

  if (loading) return <p>Loading pending bookings…</p>;
  if (error)   return <p style={{ color: "#b00020" }}>Error: {error}</p>;
  if (bookings.length === 0) return <p>No pending bookings.</p>;

  return (
    <section>
      <h2 style={{ marginTop: 0, fontSize: "1rem" }}>Pending Approvals</h2>
      <button onClick={load} style={{ marginBottom: "1rem", cursor: "pointer" }}>
        Refresh
      </button>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.875rem" }}>
        <thead>
          <tr style={{ borderBottom: "2px solid #e5e5e5", textAlign: "left" }}>
            <th style={{ padding: "0.4rem 0.6rem" }}>#</th>
            <th style={{ padding: "0.4rem 0.6rem" }}>Farmhouse</th>
            <th style={{ padding: "0.4rem 0.6rem" }}>Client</th>
            <th style={{ padding: "0.4rem 0.6rem" }}>Start (PKT)</th>
            <th style={{ padding: "0.4rem 0.6rem" }}>End (PKT)</th>
            <th style={{ padding: "0.4rem 0.6rem" }}>Event</th>
            <th style={{ padding: "0.4rem 0.6rem" }}>Action</th>
          </tr>
        </thead>
        <tbody>
          {bookings.map((b) => {
            const msg = actionMsg[b.id];
            return (
              <tr key={b.id} style={{ borderBottom: "1px solid #f0f0f0" }}>
                <td style={{ padding: "0.4rem 0.6rem" }}>{b.id}</td>
                <td style={{ padding: "0.4rem 0.6rem" }}>{b.farmhouse_id}</td>
                <td style={{ padding: "0.4rem 0.6rem" }}>{b.client_name ?? "—"}</td>
                <td style={{ padding: "0.4rem 0.6rem" }}>{fmtDt(b.start_at)}</td>
                <td style={{ padding: "0.4rem 0.6rem" }}>{fmtDt(b.end_at)}</td>
                <td style={{ padding: "0.4rem 0.6rem" }}>{b.event_type ?? "—"}</td>
                <td style={{ padding: "0.4rem 0.6rem" }}>
                  <button
                    onClick={() => handleApprove(b.id)}
                    disabled={!!msg}
                    style={{ cursor: "pointer", padding: "0.2rem 0.6rem" }}
                  >
                    Approve
                  </button>
                  {msg && (
                    <span
                      style={{
                        marginLeft: "0.5rem",
                        color: msg.ok ? "#1a7f37" : "#b00020",
                        fontSize: "0.8rem",
                      }}
                    >
                      {msg.text}
                    </span>
                  )}
                  {msg?.panel === "conflicts" && (
                    <ConflictPanel
                      bookedId={msg.bookedId}
                      onDone={() => {
                        setActionMsg((prev) => ({ ...prev, [b.id]: null }));
                        load();
                      }}
                    />
                  )}
                  {msg?.panel === "conflict_offer" && (
                    <ConflictRejectOffer
                      pendingId={b.id}
                      conflictBookedId={msg.conflictBookedId}
                      onDone={() => {
                        setBookings((prev) => prev.filter((x) => x.id !== b.id));
                        setActionMsg((prev) => ({ ...prev, [b.id]: null }));
                      }}
                    />
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </section>
  );
}
