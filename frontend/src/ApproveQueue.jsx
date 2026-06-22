/**
 * ApproveQueue — Admin view listing PENDING bookings with an Approve action.
 *
 * Slice #23: approve -> booked (+ 409 conflict feedback).
 * Slice #24 (auto-reject losers) will extend this view — keep it simple for now.
 */
import { useEffect, useState } from "react";
import { listBookings, approveBooking } from "./api.js";

function fmtDt(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("en-PK", { timeZone: "Asia/Karachi" });
}

export default function ApproveQueue() {
  const [bookings, setBookings]   = useState([]);
  const [loading, setLoading]     = useState(true);
  const [error, setError]         = useState(null);
  const [actionMsg, setActionMsg] = useState({}); // { [id]: { ok, text } }

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
      await approveBooking(id);
      setActionMsg((prev) => ({ ...prev, [id]: { ok: true, text: "Approved — now Booked." } }));
      // Remove from pending list after short delay so user sees confirmation
      setTimeout(() => setBookings((prev) => prev.filter((b) => b.id !== id)), 1500);
    } catch (e) {
      let msg = e.message ?? "Approval failed";
      if (e.status === 409 && e.conflict_booking_id != null) {
        msg = `Conflict with booking #${e.conflict_booking_id}. Slot already confirmed.`;
      }
      setActionMsg((prev) => ({ ...prev, [id]: { ok: false, text: msg } }));
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
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </section>
  );
}
