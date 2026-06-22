import { useState } from "react";
import { inviteBookie } from "./api.js";

export default function InviteBookiePage() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [status, setStatus] = useState(null); // null | {ok: bool, msg: string}
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setStatus(null);
    setLoading(true);
    try {
      await inviteBookie(name, email);
      setStatus({ ok: true, msg: `Invite sent to ${email}` });
      setName("");
      setEmail("");
    } catch (err) {
      const msg =
        err.status === 409
          ? "That email is already registered."
          : err.message ?? "Failed to send invite";
      setStatus({ ok: false, msg });
    } finally {
      setLoading(false);
    }
  }

  return (
    <section>
      <h2 style={{ marginTop: 0 }}>Invite a Bookie</h2>
      <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "0.75rem", maxWidth: 360 }}>
        <label>
          Name
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            style={{ display: "block", width: "100%", marginTop: "0.25rem", padding: "0.5rem", boxSizing: "border-box" }}
          />
        </label>
        <label>
          Email
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            style={{ display: "block", width: "100%", marginTop: "0.25rem", padding: "0.5rem", boxSizing: "border-box" }}
          />
        </label>
        {status && (
          <p style={{ color: status.ok ? "#2e7d32" : "#b00020", margin: 0 }}>{status.msg}</p>
        )}
        <button type="submit" disabled={loading} style={{ padding: "0.6rem", cursor: "pointer" }}>
          {loading ? "Sending…" : "Send Invite"}
        </button>
      </form>
    </section>
  );
}
