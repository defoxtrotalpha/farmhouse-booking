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
      <div className="auth-wrap">
        <div className="auth-card card">
          <h2 style={{ marginTop: 0 }}>Invalid link</h2>
          <p style={{ color: "var(--muted)" }}>No invite token found. Please use the link from your invitation email.</p>
        </div>
      </div>
    );
  }

  if (done) {
    return (
      <div className="auth-wrap">
        <div className="auth-card card">
          <h2 style={{ marginTop: 0 }}>Password set 🎉</h2>
          <p style={{ color: "var(--muted)" }}>Your account is now active.</p>
          <a href="/" className="btn" style={{ textDecoration: "none" }}>Go to login →</a>
        </div>
      </div>
    );
  }

  return (
    <div className="auth-wrap">
      <div className="auth-card card">
        <h2 style={{ margin: "0 0 0.25rem" }}>Set your password</h2>
        <p style={{ color: "var(--muted)", marginTop: 0, fontSize: "0.9rem" }}>Choose a password to activate your account.</p>
        <form onSubmit={handleSubmit}>
          <label className="field">
            <span>New password</span>
            <input
              type="password"
              value={password}
              onChange={(e) => setPass(e.target.value)}
              required
              minLength={8}
              autoFocus
              autoComplete="new-password"
            />
          </label>
          <label className="field">
            <span>Confirm password</span>
            <input
              type="password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              required
              autoComplete="new-password"
            />
          </label>
          {status && <div className="alert alert-error">{status.msg}</div>}
          <button type="submit" disabled={loading} className="btn" style={{ width: "100%", marginTop: "0.25rem" }}>
            {loading ? "Setting password…" : "Set password"}
          </button>
        </form>
      </div>
    </div>
  );
}
