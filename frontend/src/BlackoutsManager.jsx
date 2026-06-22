/**
 * BlackoutsManager — admin page for managing blackout dates.
 *
 * Features:
 *   - List all blackout dates
 *   - Add a new blackout (global or per-farmhouse)
 *   - Delete a blackout
 */
import { useEffect, useState } from "react";
import { listBlackouts, createBlackout, deleteBlackout, listFarmhouses } from "./api.js";

function fmtDate(iso) {
  if (!iso) return "—";
  // iso may come as 'YYYY-MM-DD'
  return iso;
}

export default function BlackoutsManager() {
  const [blackouts,   setBlackouts]   = useState([]);
  const [farmhouses,  setFarmhouses]  = useState([]);
  const [loading,     setLoading]     = useState(true);
  const [error,       setError]       = useState(null);

  // New blackout form state
  const [form, setForm] = useState({
    farmhouse_id: "",
    start_date:   "",
    end_date:     "",
    reason:       "",
  });
  const [saving,  setSaving]  = useState(false);
  const [formErr, setFormErr] = useState(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [bx, fhs] = await Promise.all([
        listBlackouts(),
        listFarmhouses({ includeDisabled: true }),
      ]);
      setBlackouts(bx);
      setFarmhouses(fhs);
    } catch (e) {
      setError(e.message ?? "Failed to load data");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  function setField(f, v) {
    setForm((prev) => ({ ...prev, [f]: v }));
  }

  async function handleCreate(e) {
    e.preventDefault();
    setFormErr(null);
    setSaving(true);
    try {
      await createBlackout({
        farmhouse_id: form.farmhouse_id ? parseInt(form.farmhouse_id, 10) : null,
        start_date:   form.start_date,
        end_date:     form.end_date || form.start_date,   // default end = start
        reason:       form.reason.trim() || undefined,
      });
      setForm({ farmhouse_id: "", start_date: "", end_date: "", reason: "" });
      await load();
    } catch (err) {
      setFormErr(err.message ?? "Failed to create blackout");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(id) {
    if (!window.confirm("Delete this blackout date?")) return;
    try {
      await deleteBlackout(id);
      await load();
    } catch (err) {
      alert(err.message ?? "Failed to delete blackout");
    }
  }

  const inputStyle = {
    display: "block",
    width: "100%",
    marginTop: "0.25rem",
    padding: "0.4rem 0.5rem",
    boxSizing: "border-box",
    border: "1px solid #ccc",
    borderRadius: 4,
    fontSize: "0.875rem",
  };

  const labelStyle = { fontSize: "0.83rem", fontWeight: 500, color: "#333" };

  return (
    <section>
      <h2 style={{ marginTop: 0, marginBottom: "1.25rem", fontSize: "1.1rem" }}>Blackout Dates</h2>

      {/* Add form */}
      <div style={{ border: "1px solid #e5e5e5", borderRadius: 8, padding: "1rem", marginBottom: "1.5rem" }}>
        <h3 style={{ margin: "0 0 0.75rem", fontSize: "0.95rem" }}>Add Blackout</h3>

        {formErr && (
          <p style={{ color: "#b00020", margin: "0 0 0.75rem", fontSize: "0.85rem" }}>{formErr}</p>
        )}

        <form onSubmit={handleCreate}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem", marginBottom: "0.75rem" }}>
            <div>
              <label style={labelStyle}>
                Start Date *
                <input
                  type="date" required
                  value={form.start_date}
                  onChange={(e) => setField("start_date", e.target.value)}
                  style={inputStyle}
                />
              </label>
            </div>
            <div>
              <label style={labelStyle}>
                End Date (blank = same as start)
                <input
                  type="date"
                  value={form.end_date}
                  onChange={(e) => setField("end_date", e.target.value)}
                  style={inputStyle}
                />
              </label>
            </div>
          </div>

          <div style={{ marginBottom: "0.75rem" }}>
            <label style={labelStyle}>
              Farmhouse (blank = global / applies to all)
              <select
                value={form.farmhouse_id}
                onChange={(e) => setField("farmhouse_id", e.target.value)}
                style={{ ...inputStyle, background: "#fff" }}
              >
                <option value="">— Global (all farmhouses) —</option>
                {farmhouses.map((fh) => (
                  <option key={fh.id} value={fh.id}>{fh.name}</option>
                ))}
              </select>
            </label>
          </div>

          <div style={{ marginBottom: "0.75rem" }}>
            <label style={labelStyle}>
              Reason / Label (optional)
              <input
                type="text"
                placeholder="e.g. National Holiday, Maintenance"
                value={form.reason}
                onChange={(e) => setField("reason", e.target.value)}
                style={inputStyle}
              />
            </label>
          </div>

          <button
            type="submit"
            disabled={saving}
            style={{ padding: "0.4rem 1rem", cursor: "pointer" }}
          >
            {saving ? "Adding…" : "Add Blackout"}
          </button>
        </form>
      </div>

      {/* List */}
      {loading && <p>Loading…</p>}
      {error   && <p style={{ color: "#b00020" }}>Error: {error}</p>}

      {!loading && !error && blackouts.length === 0 && (
        <p style={{ color: "#666", fontSize: "0.875rem" }}>No blackout dates configured.</p>
      )}

      {!loading && blackouts.length > 0 && (
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.875rem" }}>
          <thead>
            <tr style={{ borderBottom: "2px solid #e5e5e5", textAlign: "left" }}>
              <th style={{ padding: "0.4rem 0.5rem" }}>Start</th>
              <th style={{ padding: "0.4rem 0.5rem" }}>End</th>
              <th style={{ padding: "0.4rem 0.5rem" }}>Scope</th>
              <th style={{ padding: "0.4rem 0.5rem" }}>Reason</th>
              <th style={{ padding: "0.4rem 0.5rem" }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {blackouts.map((b) => {
              const fh = farmhouses.find((f) => f.id === b.farmhouse_id);
              return (
                <tr key={b.id} style={{ borderBottom: "1px solid #f0f0f0" }}>
                  <td style={{ padding: "0.4rem 0.5rem" }}>{fmtDate(b.start_date)}</td>
                  <td style={{ padding: "0.4rem 0.5rem" }}>{fmtDate(b.end_date)}</td>
                  <td style={{ padding: "0.4rem 0.5rem" }}>
                    {b.farmhouse_id == null
                      ? <span style={{ color: "#b45309", fontWeight: 500 }}>Global</span>
                      : <span>{fh ? fh.name : `FH #${b.farmhouse_id}`}</span>
                    }
                  </td>
                  <td style={{ padding: "0.4rem 0.5rem", color: "#555" }}>
                    {b.reason ?? <span style={{ color: "#bbb" }}>—</span>}
                  </td>
                  <td style={{ padding: "0.4rem 0.5rem" }}>
                    <button
                      onClick={() => handleDelete(b.id)}
                      style={{
                        cursor: "pointer",
                        background: "none",
                        border: "1px solid #b00020",
                        color: "#b00020",
                        borderRadius: 4,
                        padding: "0.15rem 0.5rem",
                        fontSize: "0.78rem",
                      }}
                    >
                      Delete
                    </button>
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
