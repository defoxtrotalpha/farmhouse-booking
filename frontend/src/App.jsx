import { useEffect, useState } from "react";
import { getHealth, getMe, login, tokens } from "./api.js";
import FarmhousesPage from "./Farmhouses.jsx";
import InviteBookiePage from "./InviteBookie.jsx";
import SetPasswordPage from "./SetPassword.jsx";
import ActivityLogPage from "./ActivityLog.jsx";
import PoliciesPage from "./Policies.jsx";
import CalendarPage from "./CalendarPage.jsx";
import ApproveQueue from "./ApproveQueue.jsx";
import MyBookings from "./MyBookings.jsx";
import SettingsPage from "./Settings.jsx";
import BlackoutsManager from "./BlackoutsManager.jsx";
import NotificationBell from "./NotificationBell.jsx";

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
  const [tab, setTab] = useState("dashboard");

  useEffect(() => {
    getHealth().then(setHealth).catch((e) => setHealthError(e.message));
  }, []);

  const navBtn = (id, label) => (
    <button
      key={id}
      onClick={() => setTab(id)}
      style={{
        padding: "0.4rem 0.9rem",
        cursor: "pointer",
        background: "none",
        border: "none",
        borderBottom: tab === id ? "2px solid #333" : "2px solid transparent",
        fontWeight: tab === id ? 600 : 400,
        fontSize: "0.9rem",
      }}
    >
      {label}
    </button>
  );

  return (
    <main style={{ fontFamily: "system-ui, sans-serif", padding: "2rem", maxWidth: 760, margin: "0 auto" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <h1 style={{ margin: 0 }}>Farmhouse Booking</h1>
        <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
          <NotificationBell />
          <button onClick={onLogout} style={{ cursor: "pointer" }}>Sign out</button>
        </div>
      </div>
      <p style={{ color: "#666", marginTop: "0.25rem" }}>
        Signed in as <strong>{user.name || user.email}</strong> ({user.role})
      </p>

      <nav style={{ borderBottom: "1px solid #e5e5e5", display: "flex", gap: "0.25rem", marginBottom: "1.5rem" }}>
        {navBtn("dashboard", "Dashboard")}
        {navBtn("calendar", "Calendar")}
        {navBtn("bookings", "My Bookings")}
        {navBtn("farmhouses", "Farmhouses")}
        {user.role === "admin" && navBtn("approve", "Approvals")}
        {user.role === "admin" && navBtn("invites", "Invite Bookie")}
        {navBtn("activity", "Activity Log")}
        {navBtn("policies", "Policies")}
        {user.role === "admin" && navBtn("settings", "Settings")}
        {user.role === "admin" && navBtn("blackouts", "Blackouts")}
      </nav>

      {tab === "dashboard" && (        <section style={{ padding: "1rem 1.25rem", border: "1px solid #e5e5e5", borderRadius: 12 }}>
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
      )}

      {tab === "farmhouses" && <FarmhousesPage user={user} />}
      {tab === "bookings" && <MyBookings user={user} />}
      {tab === "calendar" && <CalendarPage />}
      {tab === "approve" && user.role === "admin" && <ApproveQueue />}
      {tab === "invites" && user.role === "admin" && <InviteBookiePage />}
      {tab === "activity" && <ActivityLogPage user={user} />}
      {tab === "policies" && <PoliciesPage user={user} />}
      {tab === "settings"  && user.role === "admin" && <SettingsPage />}
      {tab === "blackouts" && user.role === "admin" && <BlackoutsManager />}
    </main>
  );
}

// ---------------------------------------------------------------------------
// Root
// ---------------------------------------------------------------------------

export default function App() {
  const [user, setUser] = useState(undefined); // undefined = loading, null = logged out

  useEffect(() => {
    // Skip auth check on the public set-password route
    if (window.location.pathname === "/set-password") return;
    if (tokens.getAccess()) {
      getMe().then(setUser).catch(() => setUser(null));
    } else {
      setUser(null);
    }
  }, []);

  // Public route: /set-password — renders without auth
  if (window.location.pathname === "/set-password") {
    return <SetPasswordPage />;
  }

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

