/**
 * SettingsPage — admin-only page for editing system-wide booking rules.
 *
 * Fields:
 *   - hold_duration_hours          (number)
 *   - min_advance_notice_minutes   (number, 0 = OFF)
 *   - default_buffer_minutes       (number)
 *   - operating_hours_start        (HH:MM string or empty)
 *   - operating_hours_end          (HH:MM string or empty)
 */
import { useEffect, useState } from "react";
import { getSettings, updateSettings } from "./api.js";

const inputStyle = {
  display: "block",
  width: "100%",
  marginTop: "0.25rem",
  padding: "0.4rem 0.5rem",
  boxSizing: "border-box",
  border: "1px solid #ccc",
  borderRadius: 4,
  fontSize: "0.9rem",
};

const fieldStyle = { marginBottom: "0.9rem" };
const labelStyle = { fontSize: "0.85rem", fontWeight: 500, color: "#333" };
const hintStyle  = { fontSize: "0.78rem", color: "#666", marginTop: "0.2rem" };

export default function SettingsPage() {
  const [data,    setData]    = useState(null);
  const [form,    setForm]    = useState({});
  const [saving,  setSaving]  = useState(false);
  const [msg,     setMsg]     = useState(null);   // { ok: bool, text: string }
  const [loadErr, setLoadErr] = useState(null);

  useEffect(() => {
    getSettings()
      .then((s) => {
        setData(s);
        setForm({
          hold_duration_hours:        String(s.hold_duration_hours),
          min_advance_notice_minutes: String(s.min_advance_notice_minutes),
          default_buffer_minutes:     String(s.default_buffer_minutes),
          operating_hours_start:      s.operating_hours_start ?? "",
          operating_hours_end:        s.operating_hours_end   ?? "",
        });
      })
      .catch((e) => setLoadErr(e.message));
  }, []);

  function set(field, value) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  async function handleSave(e) {
    e.preventDefault();
    setMsg(null);
    setSaving(true);

    // Build the patch — only send fields that changed.
    const patch = {};
    const hdh = parseInt(form.hold_duration_hours,        10);
    const man = parseInt(form.min_advance_notice_minutes, 10);
    const dbm = parseInt(form.default_buffer_minutes,     10);

    if (!isNaN(hdh)) patch.hold_duration_hours        = hdh;
    if (!isNaN(man)) patch.min_advance_notice_minutes  = man;
    if (!isNaN(dbm)) patch.default_buffer_minutes      = dbm;

    // Operating hours: send null to clear, or the HH:MM string.
    // Allow empty string -> clear the field.
    patch.operating_hours_start = form.operating_hours_start.trim() || null;
    patch.operating_hours_end   = form.operating_hours_end.trim()   || null;

    try {
      const updated = await updateSettings(patch);
      setData(updated);
      setMsg({ ok: true, text: "Settings saved." });
    } catch (err) {
      setMsg({ ok: false, text: err.message ?? "Failed to save settings." });
    } finally {
      setSaving(false);
    }
  }

  if (loadErr) return <p style={{ color: "#b00020" }}>Error: {loadErr}</p>;
  if (!data)   return <p>Loading…</p>;

  return (
    <section>
      <h2 style={{ marginTop: 0, marginBottom: "1.25rem", fontSize: "1.1rem" }}>System Settings</h2>

      {msg && (
        <p style={{
          margin: "0 0 1rem",
          padding: "0.5rem 0.75rem",
          borderRadius: 4,
          background: msg.ok ? "#dcfce7" : "#fee2e2",
          color:      msg.ok ? "#166534" : "#b00020",
          fontSize: "0.88rem",
        }}>
          {msg.text}
        </p>
      )}

      <form onSubmit={handleSave}>
        {/* Hold duration */}
        <div style={fieldStyle}>
          <label style={labelStyle}>
            Hold Duration (hours)
            <input
              type="number" min="1"
              value={form.hold_duration_hours}
              onChange={(e) => set("hold_duration_hours", e.target.value)}
              style={inputStyle}
            />
          </label>
          <p style={hintStyle}>
            How long a hold stays active before it can be swept as expired (default 24).
          </p>
        </div>

        {/* Min advance notice */}
        <div style={fieldStyle}>
          <label style={labelStyle}>
            Min Advance Notice (minutes, 0 = OFF)
            <input
              type="number" min="0"
              value={form.min_advance_notice_minutes}
              onChange={(e) => set("min_advance_notice_minutes", e.target.value)}
              style={inputStyle}
            />
          </label>
          <p style={hintStyle}>
            Require bookings to start at least this many minutes from now. 0 disables the check.
          </p>
        </div>

        {/* Default buffer */}
        <div style={fieldStyle}>
          <label style={labelStyle}>
            Default Buffer Between Bookings (minutes)
            <input
              type="number" min="0"
              value={form.default_buffer_minutes}
              onChange={(e) => set("default_buffer_minutes", e.target.value)}
              style={inputStyle}
            />
          </label>
          <p style={hintStyle}>
            Global default; individual farmhouses may override with their own buffer.
          </p>
        </div>

        {/* Operating hours */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem", marginBottom: "0.9rem" }}>
          <div>
            <label style={labelStyle}>
              Operating Hours Start (HH:MM, blank = no limit)
              <input
                type="text"
                placeholder="09:00"
                value={form.operating_hours_start}
                onChange={(e) => set("operating_hours_start", e.target.value)}
                style={inputStyle}
              />
            </label>
          </div>
          <div>
            <label style={labelStyle}>
              Operating Hours End (HH:MM)
              <input
                type="text"
                placeholder="23:00"
                value={form.operating_hours_end}
                onChange={(e) => set("operating_hours_end", e.target.value)}
                style={inputStyle}
              />
            </label>
          </div>
        </div>
        <p style={{ ...hintStyle, marginBottom: "1rem" }}>
          Asia/Karachi local time. Applies to single-day bookings. Leave both blank to disable.
          Per-farmhouse operating hours take precedence when set.
        </p>

        <button
          type="submit"
          disabled={saving}
          style={{ padding: "0.45rem 1.25rem", cursor: "pointer" }}
        >
          {saving ? "Saving…" : "Save Settings"}
        </button>
      </form>
    </section>
  );
}
