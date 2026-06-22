import { useEffect, useState } from "react";
import { getHealth, getMe, login, tokens } from "./api.js";

// ---------------------------------------------------------------------------
// Login form
// ---------------------------------------------------------------------------

function LoginPage({ onLogin }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await login(email, password);
      onLogin();
    } catch (err) {
      setError(err.message ?? "Login failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main style={{ fontFamily: "system-ui, sans-serif", padding: "2rem", maxWidth: 400, margin: "4rem auto" }}>
      <h1 style={{ marginBottom: "0.25rem" }}>Farmhouse Booking</h1>
      <p style={{ color: "#666", marginTop: 0 }}>Sign in to continue</p>
      <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
        <label>
          Email
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            autoFocus
            style={{ display: "block", width: "100%", marginTop: "0.25rem", padding: "0.5rem", boxSizing: "border-box" }}
          />
        </label>
        <label>
          Password
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            style={{ display: "block", width: "100%", marginTop: "0.25rem", padding: "0.5rem", boxSizing: "border-box" }}
          />
        </label>
        {error && <p style={{ color: "#b00020", margin: 0 }}>{error}</p>}
        <button type="submit" disabled={loading} style={{ padding: "0.6rem", cursor: "pointer" }}>
          {loading ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </main>
  );
}

// ---------------------------------------------------------------------------
// Authenticated shell
// ---------------------------------------------------------------------------

function AppShell({ user, onLogout }) {
  const [health, setHealth] = useState(null);
  const [healthError, setHealthError] = useState(null);

  useEffect(() => {
    getHealth().then(setHealth).catch((e) => setHealthError(e.message));
  }, []);

  return (
    <main style={{ fontFamily: "system-ui, sans-serif", padding: "2rem", maxWidth: 640, margin: "0 auto" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <h1 style={{ margin: 0 }}>Farmhouse Booking</h1>
        <button onClick={onLogout} style={{ cursor: "pointer" }}>Sign out</button>
      </div>
      <p style={{ color: "#666" }}>
        Signed in as <strong>{user.name || user.email}</strong> ({user.role})
      </p>

      <section style={{ marginTop: "2rem", padding: "1rem 1.25rem", border: "1px solid #e5e5e5", borderRadius: 12 }}>
        <h2 style={{ margin: 0, fontSize: "1rem" }}>System status</h2>
        {healthError && <p style={{ color: "#b00020" }}>Backend unreachable: {healthError}</p>}
        {!healthError && !health && <p>Checking…</p>}
        {health && (
          <ul style={{ listStyle: "none", padding: 0 }}>
            <li>API: <strong>{health.status}</strong></li>
            <li>Database: <strong>{health.database}</strong></li>
            <li>Timezone: <strong>{health.timezone}</strong></li>
          </ul>
        )}
      </section>
    </main>
  );
}

// ---------------------------------------------------------------------------
// Root
// ---------------------------------------------------------------------------

export default function App() {
  const [user, setUser] = useState(undefined); // undefined = loading, null = logged out

  useEffect(() => {
    if (tokens.getAccess()) {
      getMe().then(setUser).catch(() => setUser(null));
    } else {
      setUser(null);
    }
  }, []);

  function handleLogin() {
    getMe().then(setUser).catch(() => setUser(null));
  }

  function handleLogout() {
    tokens.clear();
    setUser(null);
  }

  if (user === undefined) return null; // brief loading flash
  if (!user) return <LoginPage onLogin={handleLogin} />;
  return <AppShell user={user} onLogout={handleLogout} />;
}

