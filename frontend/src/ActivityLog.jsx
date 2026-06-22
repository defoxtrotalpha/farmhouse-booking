import { useEffect, useState } from "react";
import { listActivity } from "./api.js";

export default function ActivityLogPage({ user }) {
  const [entries, setEntries] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [offset, setOffset] = useState(0);
  const LIMIT = 50;

  useEffect(() => {
    setLoading(true);
    setError(null);
    listActivity({ limit: LIMIT, offset })
      .then(setEntries)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [offset]);

  const fmt = (iso) => {
    if (!iso) return "—";
    return new Date(iso).toLocaleString("en-PK", { timeZone: "Asia/Karachi" });
  };

  return (
    <section>
      <h2 style={{ marginTop: 0, fontSize: "1rem" }}>
        Activity Log{user.role !== "admin" && " (your actions)"}
      </h2>

      {loading && <p>Loading…</p>}
      {error && <p style={{ color: "#b00020" }}>Error: {error}</p>}

      {!loading && !error && entries.length === 0 && (
        <p style={{ color: "#666" }}>No activity entries yet.</p>
      )}

      {!loading && !error && entries.length > 0 && (
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.85rem" }}>
            <thead>
              <tr style={{ background: "#f5f5f5", textAlign: "left" }}>
                <th style={{ padding: "0.5rem 0.75rem", borderBottom: "1px solid #ddd" }}>Time (PKT)</th>
                <th style={{ padding: "0.5rem 0.75rem", borderBottom: "1px solid #ddd" }}>Actor ID</th>
                <th style={{ padding: "0.5rem 0.75rem", borderBottom: "1px solid #ddd" }}>Action</th>
                <th style={{ padding: "0.5rem 0.75rem", borderBottom: "1px solid #ddd" }}>Target</th>
                <th style={{ padding: "0.5rem 0.75rem", borderBottom: "1px solid #ddd" }}>Note</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((e) => (
                <tr key={e.id} style={{ borderBottom: "1px solid #eee" }}>
                  <td style={{ padding: "0.4rem 0.75rem", whiteSpace: "nowrap" }}>{fmt(e.created_at)}</td>
                  <td style={{ padding: "0.4rem 0.75rem" }}>{e.actor_id ?? "system"}</td>
                  <td style={{ padding: "0.4rem 0.75rem", fontFamily: "monospace" }}>{e.action}</td>
                  <td style={{ padding: "0.4rem 0.75rem" }}>
                    {e.target_type && e.target_id ? `${e.target_type}#${e.target_id}` : "—"}
                  </td>
                  <td style={{ padding: "0.4rem 0.75rem", color: "#555" }}>{e.note ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.75rem" }}>
        <button
          onClick={() => setOffset((o) => Math.max(0, o - LIMIT))}
          disabled={offset === 0}
          style={{ cursor: "pointer", padding: "0.3rem 0.75rem" }}
        >
          ← Prev
        </button>
        <button
          onClick={() => setOffset((o) => o + LIMIT)}
          disabled={entries.length < LIMIT}
          style={{ cursor: "pointer", padding: "0.3rem 0.75rem" }}
        >
          Next →
        </button>
      </div>
    </section>
  );
}
