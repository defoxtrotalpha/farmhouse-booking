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
import ReportsPage from "./Reports.jsx";

// ---------------------------------------------------------------------------
// Login form
// ---------------------------------------------------------------------------

function BrandMark({ size = 34 }) {
  return (
    <span className="brand-mark" style={{ width: size, height: size }} aria-hidden="true">
      🌿
    </span>
  );
}

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
    <div className="auth-wrap">
      <div className="auth-card card">
        <div className="auth-brand">
          <BrandMark size={40} />
          <div>
            <div className="brand-title">Farmhouse Booking</div>
            <div className="brand-sub">Private estate reservations</div>
          </div>
        </div>
        <h2 style={{ margin: "0 0 0.25rem" }}>Welcome back</h2>
        <p style={{ color: "var(--muted)", marginTop: 0, fontSize: "0.9rem" }}>Sign in to continue</p>
        <form onSubmit={handleSubmit}>
          <label className="field">
            <span>Email</span>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoFocus
              autoComplete="username"
            />
          </label>
          <label className="field">
            <span>Password</span>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoComplete="current-password"
            />
          </label>
          {error && <div className="alert alert-error">{error}</div>}
          <button type="submit" disabled={loading} className="btn" style={{ width: "100%", marginTop: "0.25rem" }}>
            {loading ? "Signing in…" : "Sign in"}
          </button>
        </form>
      </div>
    </div>
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

  const tabs = [
    { id: "dashboard", label: "Dashboard" },
    { id: "calendar", label: "Calendar" },
    { id: "bookings", label: "My Bookings" },
    { id: "farmhouses", label: "Farmhouses" },
    { id: "approve", label: "Approvals", admin: true },
    { id: "reports", label: "Reports", admin: true },
    { id: "invites", label: "Invite Bookie", admin: true },
    { id: "activity", label: "Activity Log" },
    { id: "policies", label: "Policies" },
    { id: "settings", label: "Settings", admin: true },
    { id: "blackouts", label: "Blackouts", admin: true },
  ].filter((t) => !t.admin || user.role === "admin");

  return (
    <div className="app-bg">
      <header className="app-header">
        <div className="app-header-inner">
          <div className="brand">
            <BrandMark />
            <div>
              <div className="brand-title">Farmhouse Booking</div>
              <div className="brand-sub">Private estate reservations</div>
            </div>
          </div>
          <div className="header-actions">
            <NotificationBell />
            <span className="user-pill">
              <span className="email">{user.name || user.email}</span>
              <span className="role">{user.role}</span>
            </span>
            <button onClick={onLogout} className="btn btn-ghost btn-sm">Sign out</button>
          </div>
        </div>
        <nav className="app-nav">
          {tabs.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`tab${tab === t.id ? " active" : ""}`}
            >
              {t.label}
            </button>
          ))}
        </nav>
      </header>

      <main className="app-main" key={tab}>
        {tab === "dashboard" && (
          <section className="card" style={{ maxWidth: 480 }}>
            <h2 style={{ marginTop: 0, fontSize: "1.05rem" }}>System status</h2>
            {healthError && <div className="alert alert-error">Backend unreachable: {healthError}</div>}
            {!healthError && !health && <p style={{ color: "var(--muted)" }}>Checking…</p>}
            {health && (
              <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: "0.4rem" }}>
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
        {tab === "reports" && user.role === "admin" && <ReportsPage />}
        {tab === "invites" && user.role === "admin" && <InviteBookiePage />}
        {tab === "activity" && <ActivityLogPage user={user} />}
        {tab === "policies" && <PoliciesPage user={user} />}
        {tab === "settings" && user.role === "admin" && <SettingsPage />}
        {tab === "blackouts" && user.role === "admin" && <BlackoutsManager />}
      </main>
    </div>
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

