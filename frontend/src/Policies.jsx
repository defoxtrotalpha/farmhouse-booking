import { useEffect, useState } from "react";
import { listPolicies, createPolicy, updatePolicy } from "./api.js";

// ---------------------------------------------------------------------------
// Policies page
// Admins: can create new policies and edit existing ones (version is shown).
// Bookies / all authenticated users: read-only view of current policies.
// ---------------------------------------------------------------------------

export default function PoliciesPage({ user }) {
  const isAdmin = user?.role === "admin";
  const [policies, setPolicies] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // editor state (admin only)
  const [editingId, setEditingId] = useState(null); // null = not editing
  const [formTitle, setFormTitle] = useState("");
  const [formBody, setFormBody] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState(null);

  // create form visibility
  const [showCreate, setShowCreate] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [newBody, setNewBody] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const data = await listPolicies();
      setPolicies(data);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  function startEdit(policy) {
    setEditingId(policy.id);
    setFormTitle(policy.title);
    setFormBody(policy.body);
    setSaveError(null);
  }

  function cancelEdit() {
    setEditingId(null);
    setSaveError(null);
  }

  async function handleSave(id) {
    setSaving(true);
    setSaveError(null);
    try {
      await updatePolicy(id, { title: formTitle, body: formBody });
      setEditingId(null);
      await load();
    } catch (e) {
      setSaveError(e.message);
    } finally {
      setSaving(false);
    }
  }

  async function handleCreate(e) {
    e.preventDefault();
    setCreating(true);
    setCreateError(null);
    try {
      await createPolicy({ title: newTitle, body: newBody });
      setNewTitle("");
      setNewBody("");
      setShowCreate(false);
      await load();
    } catch (e) {
      setCreateError(e.message);
    } finally {
      setCreating(false);
    }
  }

  return (
    <section>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: "1rem" }}>
        <h2 style={{ margin: 0 }}>Policies &amp; Terms</h2>
        {isAdmin && !showCreate && (
          <button onClick={() => setShowCreate(true)} style={{ cursor: "pointer" }}>
            + New Policy
          </button>
        )}
      </div>

      {/* Create form (admin) */}
      {isAdmin && showCreate && (
        <form
          onSubmit={handleCreate}
          style={{ border: "1px solid #e5e5e5", borderRadius: 8, padding: "1rem", marginBottom: "1.5rem" }}
        >
          <h3 style={{ marginTop: 0 }}>New Policy</h3>
          <label style={{ display: "block", marginBottom: "0.5rem" }}>
            Title
            <input
              type="text"
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
              required
              style={{ display: "block", width: "100%", marginTop: "0.25rem", padding: "0.4rem", boxSizing: "border-box" }}
            />
          </label>
          <label style={{ display: "block", marginBottom: "0.75rem" }}>
            Body
            <textarea
              value={newBody}
              onChange={(e) => setNewBody(e.target.value)}
              required
              rows={5}
              style={{ display: "block", width: "100%", marginTop: "0.25rem", padding: "0.4rem", boxSizing: "border-box" }}
            />
          </label>
          {createError && <p style={{ color: "#b00020", margin: "0 0 0.5rem" }}>{createError}</p>}
          <div style={{ display: "flex", gap: "0.5rem" }}>
            <button type="submit" disabled={creating} style={{ cursor: "pointer" }}>
              {creating ? "Creating…" : "Create"}
            </button>
            <button type="button" onClick={() => setShowCreate(false)} style={{ cursor: "pointer" }}>
              Cancel
            </button>
          </div>
        </form>
      )}

      {loading && <p>Loading…</p>}
      {error && <p style={{ color: "#b00020" }}>{error}</p>}
      {!loading && !error && policies.length === 0 && (
        <p style={{ color: "#666" }}>No policies defined yet.</p>
      )}

      {policies.map((p) => (
        <div
          key={p.id}
          style={{ border: "1px solid #e5e5e5", borderRadius: 8, padding: "1rem", marginBottom: "1rem" }}
        >
          {editingId === p.id ? (
            /* Admin edit form */
            <div>
              <label style={{ display: "block", marginBottom: "0.5rem" }}>
                Title
                <input
                  type="text"
                  value={formTitle}
                  onChange={(e) => setFormTitle(e.target.value)}
                  style={{ display: "block", width: "100%", marginTop: "0.25rem", padding: "0.4rem", boxSizing: "border-box" }}
                />
              </label>
              <label style={{ display: "block", marginBottom: "0.75rem" }}>
                Body
                <textarea
                  value={formBody}
                  onChange={(e) => setFormBody(e.target.value)}
                  rows={6}
                  style={{ display: "block", width: "100%", marginTop: "0.25rem", padding: "0.4rem", boxSizing: "border-box" }}
                />
              </label>
              {saveError && <p style={{ color: "#b00020", margin: "0 0 0.5rem" }}>{saveError}</p>}
              <div style={{ display: "flex", gap: "0.5rem" }}>
                <button onClick={() => handleSave(p.id)} disabled={saving} style={{ cursor: "pointer" }}>
                  {saving ? "Saving…" : "Save"}
                </button>
                <button onClick={cancelEdit} style={{ cursor: "pointer" }}>Cancel</button>
              </div>
            </div>
          ) : (
            /* Read-only view */
            <div>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                <h3 style={{ margin: "0 0 0.25rem" }}>{p.title}</h3>
                {isAdmin && (
                  <span style={{ fontSize: "0.8rem", color: "#888" }}>
                    v{p.version} &nbsp;
                    <button onClick={() => startEdit(p)} style={{ cursor: "pointer", fontSize: "0.8rem" }}>
                      Edit
                    </button>
                  </span>
                )}
              </div>
              <p style={{ whiteSpace: "pre-wrap", margin: "0.5rem 0 0", lineHeight: 1.6 }}>{p.body}</p>
              {!isAdmin && (
                <p style={{ margin: "0.5rem 0 0", fontSize: "0.75rem", color: "#aaa" }}>Version {p.version}</p>
              )}
            </div>
          )}
        </div>
      ))}
    </section>
  );
}
