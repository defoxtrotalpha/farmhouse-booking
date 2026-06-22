import { useState } from "react";
import { setPassword } from "./api.js";

export default function SetPasswordPage() {
  // Read ?token= from the URL query string
  const params = new URLSearchParams(window.location.search);
  const token = params.get("token") ?? "";

  const [password, setPass] = useState("");
  const [confirm, setConfirm] = useState("");
  const [status, setStatus] = useState(null); // null | {ok: bool, msg: string}
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    if (password !== confirm) {
      setStatus({ ok: false, msg: "Passwords do not match" });
      return;
    }
    setStatus(null);
    setLoading(true);
    try {
      await setPassword(token, password);
      setDone(true);
    } catch (err) {
      setStatus({ ok: false, msg: err.message ?? "Failed to set password" });
    } finally {
      setLoading(false);
    }
  }

  if (!token) {
    return (
      <main style={{ fontFamily: "system-ui, sans-serif", padding: "2rem", maxWidth: 400, margin: "4rem auto" }}>
        <h1>Invalid Link</h1>
        <p>No invite token found. Please use the link from your invitation email.</p>
      </main>
    );
  }

  if (done) {
    return (
      <main style={{ fontFamily: "system-ui, sans-serif", padding: "2rem", maxWidth: 400, margin: "4rem auto" }}>
        <h1>Password Set!</h1>
        <p>Your account is now active.</p>
        <a href="/" style={{ color: "#1a73e8" }}>Go to login →</a>
      </main>
    );
  }

  return (
    <main style={{ fontFamily: "system-ui, sans-serif", padding: "2rem", maxWidth: 400, margin: "4rem auto" }}>
      <h1 style={{ marginBottom: "0.25rem" }}>Set Your Password</h1>
      <p style={{ color: "#666", marginTop: 0 }}>Choose a password to activate your account.</p>
      <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
        <label>
          New Password
          <input
            type="password"
            value={password}
            onChange={(e) => setPass(e.target.value)}
            required
            minLength={8}
            autoFocus
            style={{ display: "block", width: "100%", marginTop: "0.25rem", padding: "0.5rem", boxSizing: "border-box" }}
          />
        </label>
        <label>
          Confirm Password
          <input
            type="password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            required
            style={{ display: "block", width: "100%", marginTop: "0.25rem", padding: "0.5rem", boxSizing: "border-box" }}
          />
        </label>
        {status && (
          <p style={{ color: "#b00020", margin: 0 }}>{status.msg}</p>
        )}
        <button type="submit" disabled={loading} style={{ padding: "0.6rem", cursor: "pointer" }}>
          {loading ? "Setting password…" : "Set Password"}
        </button>
      </form>
    </main>
  );
}
