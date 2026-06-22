import { useEffect, useState } from "react";
import { listFarmhouses, createFarmhouse, updateFarmhouse } from "./api.js";

const S = {
  card: { border: "1px solid #e5e5e5", borderRadius: 8, padding: "1rem 1.25rem", marginBottom: "1rem" },
  row: { display: "flex", gap: "0.5rem", alignItems: "center", marginBottom: "0.4rem" },
  label: { minWidth: 120, fontWeight: 500 },
  input: { padding: "0.4rem 0.5rem", flex: 1, boxSizing: "border-box" },
  btn: { padding: "0.4rem 0.8rem", cursor: "pointer" },
  danger: { padding: "0.4rem 0.8rem", cursor: "pointer", background: "#ffeaea", border: "1px solid #e57373" },
  error: { color: "#b00020", margin: "0.5rem 0" },
};

function FarmhouseForm({ initial, onSave, onCancel }) {
  const [name, setName] = useState(initial?.name ?? "");
  const [description, setDescription] = useState(initial?.description ?? "");
  const [capacity, setCapacity] = useState(initial?.capacity ?? "");
  const [bufferMinutes, setBufferMinutes] = useState(initial?.buffer_minutes ?? 0);
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setSaving(true);
    try {
      const payload = {
        name,
        description,
        buffer_minutes: Number(bufferMinutes),
        ...(capacity !== "" ? { capacity: Number(capacity) } : { capacity: null }),
      };
      await onSave(payload);
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} style={S.card}>
      <h3 style={{ margin: "0 0 0.75rem" }}>{initial ? "Edit Farmhouse" : "New Farmhouse"}</h3>
      <div style={S.row}>
        <span style={S.label}>Name *</span>
        <input style={S.input} value={name} onChange={(e) => setName(e.target.value)} required />
      </div>
      <div style={S.row}>
        <span style={S.label}>Description</span>
        <input style={S.input} value={description} onChange={(e) => setDescription(e.target.value)} />
      </div>
      <div style={S.row}>
        <span style={S.label}>Capacity</span>
        <input style={S.input} type="number" min={1} value={capacity} onChange={(e) => setCapacity(e.target.value)} placeholder="optional" />
      </div>
      <div style={S.row}>
        <span style={S.label}>Buffer (min)</span>
        <input style={S.input} type="number" min={0} value={bufferMinutes} onChange={(e) => setBufferMinutes(e.target.value)} />
      </div>
      {error && <p style={S.error}>{error}</p>}
      <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.75rem" }}>
        <button type="submit" style={S.btn} disabled={saving}>{saving ? "Saving…" : "Save"}</button>
        <button type="button" style={S.btn} onClick={onCancel}>Cancel</button>
      </div>
    </form>
  );
}

export default function FarmhousesPage({ user }) {
  const isAdmin = user.role === "admin";
  const [farmhouses, setFarmhouses] = useState([]);
  const [includeDisabled, setIncludeDisabled] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState(null); // farmhouse object being edited

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const data = await listFarmhouses({ includeDisabled: isAdmin && includeDisabled });
      setFarmhouses(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, [includeDisabled]); // eslint-disable-line

  async function handleCreate(payload) {
    await createFarmhouse(payload);
    setShowForm(false);
    load();
  }

  async function handleUpdate(payload) {
    await updateFarmhouse(editing.id, payload);
    setEditing(null);
    load();
  }

  async function handleDisable(fh) {
    await updateFarmhouse(fh.id, { status: "disabled" });
    load();
  }

  async function handleEnable(fh) {
    await updateFarmhouse(fh.id, { status: "active" });
    load();
  }

  return (
    <section style={{ marginTop: "1.5rem" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
        <h2 style={{ margin: 0 }}>Farmhouses</h2>
        {isAdmin && (
          <div style={{ display: "flex", gap: "0.75rem", alignItems: "center" }}>
            <label style={{ fontSize: "0.875rem" }}>
              <input
                type="checkbox"
                checked={includeDisabled}
                onChange={(e) => setIncludeDisabled(e.target.checked)}
                style={{ marginRight: 4 }}
              />
              Show disabled
            </label>
            <button style={S.btn} onClick={() => { setShowForm(true); setEditing(null); }}>+ New</button>
          </div>
        )}
      </div>

      {showForm && (
        <FarmhouseForm
          onSave={handleCreate}
          onCancel={() => setShowForm(false)}
        />
      )}
      {editing && (
        <FarmhouseForm
          initial={editing}
          onSave={handleUpdate}
          onCancel={() => setEditing(null)}
        />
      )}

      {error && <p style={S.error}>{error}</p>}
      {loading && <p>Loading…</p>}

      {!loading && farmhouses.length === 0 && <p style={{ color: "#888" }}>No farmhouses found.</p>}

      {farmhouses.map((fh) => (
        <div key={fh.id} style={{ ...S.card, opacity: fh.status === "disabled" ? 0.6 : 1 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
            <div>
              <strong>{fh.name}</strong>
              {fh.status === "disabled" && <span style={{ marginLeft: 8, fontSize: "0.75rem", color: "#888", background: "#f5f5f5", padding: "0 6px", borderRadius: 4 }}>disabled</span>}
              {fh.description && <p style={{ margin: "0.25rem 0 0", color: "#555", fontSize: "0.875rem" }}>{fh.description}</p>}
              <p style={{ margin: "0.25rem 0 0", fontSize: "0.8rem", color: "#888" }}>
                Capacity: {fh.capacity ?? "—"} · Buffer: {fh.buffer_minutes} min
              </p>
            </div>
            {isAdmin && (
              <div style={{ display: "flex", gap: "0.4rem" }}>
                <button style={S.btn} onClick={() => { setEditing(fh); setShowForm(false); }}>Edit</button>
                {fh.status === "active"
                  ? <button style={S.danger} onClick={() => handleDisable(fh)}>Disable</button>
                  : <button style={S.btn} onClick={() => handleEnable(fh)}>Enable</button>
                }
              </div>
            )}
          </div>
        </div>
      ))}
    </section>
  );
}
