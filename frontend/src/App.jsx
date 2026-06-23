import { useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { App as AntApp, Avatar, Button, Drawer, Dropdown, Form, Input, Modal } from "antd";
import {
  HomeOutlined,
  CalendarOutlined,
  ProfileOutlined,
  CheckCircleOutlined,
  ApartmentOutlined,
  TeamOutlined,
  BarChartOutlined,
  HistoryOutlined,
  FileTextOutlined,
  SettingOutlined,
  StopOutlined,
  EllipsisOutlined,
  LogoutOutlined,
  LockOutlined,
  MailOutlined,
  UserOutlined,
  BankOutlined,
  ShopOutlined,
  CrownOutlined,
  ArrowRightOutlined,
} from "@ant-design/icons";

import { getMe, login, signupCompany, changePassword, tokens } from "./api.js";
import { Brand, BrandSeal } from "./ui.jsx";

import CalendarPage from "./CalendarPage.jsx";
import BookingsPage from "./MyBookings.jsx";
import FarmhousesPage from "./Farmhouses.jsx";
import ApproveQueue from "./ApproveQueue.jsx";
import ReportsPage from "./Reports.jsx";
import BookiesPage from "./Bookies.jsx";
import UsersPage from "./Users.jsx";
import ActivityLogPage from "./ActivityLog.jsx";
import PoliciesPage from "./Policies.jsx";
import SettingsPage from "./Settings.jsx";
import BlackoutsManager from "./BlackoutsManager.jsx";
import OverviewPage from "./Overview.jsx";
import SetPasswordPage from "./SetPassword.jsx";
import NotificationBell from "./NotificationBell.jsx";
import CompaniesPage from "./Companies.jsx";
import GlobalAdminsPage from "./GlobalAdmins.jsx";

// ---------------------------------------------------------------------------
// Navigation model
// ---------------------------------------------------------------------------
const NAV = [
  // Platform (global admin only)
  { id: "companies", label: "Companies", icon: <ShopOutlined />, global: true, group: "Platform" },
  { id: "globaladmins", label: "Global admins", icon: <CrownOutlined />, global: true, group: "Platform" },
  // Company-scoped
  { id: "overview", label: "Home", icon: <HomeOutlined />, group: "Booking" },
  { id: "calendar", label: "Calendar", icon: <CalendarOutlined />, group: "Booking" },
  { id: "bookings", label: "Bookings", icon: <ProfileOutlined />, group: "Booking" },
  { id: "approve", label: "Approvals", icon: <CheckCircleOutlined />, admin: true, group: "Booking" },
  { id: "farmhouses", label: "Estates", icon: <ApartmentOutlined />, group: "Company" },
  { id: "bookies", label: "Bookies", icon: <TeamOutlined />, admin: true, group: "Company" },
  { id: "users", label: "Users", icon: <UserOutlined />, group: "Company" },
  { id: "reports", label: "Reports", icon: <BarChartOutlined />, admin: true, group: "Company" },
  { id: "activity", label: "Activity", icon: <HistoryOutlined />, group: "Records" },
  { id: "policies", label: "Policies", icon: <FileTextOutlined />, group: "Records" },
  { id: "settings", label: "Settings", icon: <SettingOutlined />, admin: true, group: "Records" },
  { id: "blackouts", label: "Blackouts", icon: <StopOutlined />, admin: true, group: "Records" },
];

function visibleNav(role) {
  if (role === "global_admin") return NAV.filter((n) => n.global);
  return NAV.filter((n) => !n.global && (!n.admin || role === "admin"));
}

// ---------------------------------------------------------------------------
// Login
// ---------------------------------------------------------------------------
function LoginPage({ onLogin }) {
  const { message } = AntApp.useApp();
  const [loading, setLoading] = useState(false);
  const [mode, setMode] = useState("login"); // 'login' | 'signup'

  async function onFinish(values) {
    setLoading(true);
    try {
      await login(values.tenant?.trim(), values.identifier.trim(), values.password);
      onLogin();
    } catch (err) {
      message.error(err.message ?? "Sign in failed");
    } finally {
      setLoading(false);
    }
  }

  async function onSignup(values) {
    setLoading(true);
    try {
      const res = await signupCompany({
        company_name: values.company_name.trim(),
        name: values.name.trim(),
        email: values.email.trim(),
        password: values.password,
      });
      message.success(
        res?.message ||
          "Your company request has been submitted for approval. You'll be able to sign in once a platform admin approves it.",
        8,
      );
      setMode("login");
    } catch (err) {
      message.error(err.message ?? "Sign up failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="auth-stage">
      <motion.aside
        className="auth-aside"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.5 }}
      >
        <div className="brand-lockup" style={{ color: "inherit" }}>
          <BrandSeal />
          <div>
            <div className="brand-name" style={{ color: "#fbf7ec" }}>Estate Booking</div>
            <div className="brand-sub" style={{ color: "rgba(232,214,168,.7)" }}>Booking Ledger</div>
          </div>
        </div>
        <div>
          <div className="eyebrow" style={{ color: "var(--brass-soft)" }}>Multi-company</div>
          <div className="auth-hero-title">One calendar for every estate.</div>
          <div className="auth-hero-sub">
            Hold a slot, send it for approval, and confirm exactly one booking per
            window — so a date is never promised twice.
          </div>
        </div>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, letterSpacing: ".14em", color: "rgba(232,214,168,.55)", textTransform: "uppercase" }}>
          Private access
        </div>
      </motion.aside>

      <div className="auth-panel">
        <motion.div
          className="auth-card"
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, ease: [0.22, 0.61, 0.36, 1] }}
        >
          <div style={{ display: "flex", justifyContent: "center", marginBottom: 18 }}>
            <Brand />
          </div>

          {mode === "login" ? (
            <>
              <h1 style={{ fontSize: 30, margin: "0 0 4px", textAlign: "center" }}>Welcome back</h1>
              <p className="muted" style={{ textAlign: "center", margin: "0 0 22px" }}>
                Sign in to your company.
              </p>
              <Form layout="vertical" onFinish={onFinish} requiredMark={false} size="large">
                <Form.Item
                  name="tenant"
                  label="Company name"
                  extra="Platform global admins can leave this blank."
                >
                  <Input prefix={<BankOutlined style={{ color: "var(--muted)" }} />} placeholder="Your company" autoFocus />
                </Form.Item>
                <Form.Item
                  name="identifier"
                  label="Username or email"
                  rules={[{ required: true, message: "Enter your username or email" }]}
                >
                  <Input prefix={<UserOutlined style={{ color: "var(--muted)" }} />} placeholder="admin" autoComplete="username" />
                </Form.Item>
                <Form.Item
                  name="password"
                  label="Password"
                  rules={[{ required: true, message: "Enter your password" }]}
                >
                  <Input.Password prefix={<LockOutlined style={{ color: "var(--muted)" }} />} placeholder="••••••••" autoComplete="current-password" />
                </Form.Item>
                <Button
                  type="primary"
                  htmlType="submit"
                  block
                  size="large"
                  loading={loading}
                  iconPlacement="end"
                  icon={<ArrowRightOutlined />}
                  style={{ marginTop: 4 }}
                >
                  Sign in
                </Button>
              </Form>
              <p className="muted" style={{ textAlign: "center", margin: "18px 0 0" }}>
                New here?{" "}
                <a onClick={() => setMode("signup")} style={{ cursor: "pointer" }}>Create a company</a>
              </p>
            </>
          ) : (
            <>
              <h1 style={{ fontSize: 30, margin: "0 0 4px", textAlign: "center" }}>Create your company</h1>
              <p className="muted" style={{ textAlign: "center", margin: "0 0 22px" }}>
                We'll send your request to the platform admin for approval.
              </p>
              <Form layout="vertical" onFinish={onSignup} requiredMark={false} size="large">
                <Form.Item
                  name="company_name"
                  label="Company name"
                  rules={[{ required: true, message: "Enter a company name" }]}
                >
                  <Input prefix={<BankOutlined style={{ color: "var(--muted)" }} />} placeholder="Green Acres Pvt Ltd" autoFocus />
                </Form.Item>
                <Form.Item
                  name="name"
                  label="Your name"
                  rules={[{ required: true, message: "Enter your name" }]}
                >
                  <Input prefix={<UserOutlined style={{ color: "var(--muted)" }} />} placeholder="Jane Doe" />
                </Form.Item>
                <Form.Item
                  name="email"
                  label="Email"
                  rules={[
                    { required: true, message: "Enter your email" },
                    { type: "email", message: "Enter a valid email" },
                  ]}
                >
                  <Input prefix={<MailOutlined style={{ color: "var(--muted)" }} />} placeholder="jane@company.com" autoComplete="email" />
                </Form.Item>
                <Form.Item
                  name="password"
                  label="Password"
                  rules={[{ required: true, message: "Enter a password" }, { min: 8, message: "At least 8 characters" }]}
                >
                  <Input.Password prefix={<LockOutlined style={{ color: "var(--muted)" }} />} placeholder="••••••••" autoComplete="new-password" />
                </Form.Item>
                <Button
                  type="primary"
                  htmlType="submit"
                  block
                  size="large"
                  loading={loading}
                  iconPlacement="end"
                  icon={<ArrowRightOutlined />}
                  style={{ marginTop: 4 }}
                >
                  Submit for approval
                </Button>
              </Form>
              <p className="muted" style={{ textAlign: "center", margin: "18px 0 0" }}>
                Already have a company?{" "}
                <a onClick={() => setMode("login")} style={{ cursor: "pointer" }}>Sign in</a>
              </p>
            </>
          )}
        </motion.div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Change password modal
// ---------------------------------------------------------------------------
function ChangePasswordModal({ open, onClose }) {
  const { message } = AntApp.useApp();
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);

  async function submit(values) {
    setLoading(true);
    try {
      await changePassword(values.current_password, values.new_password);
      message.success("Password updated.");
      form.resetFields();
      onClose();
    } catch (err) {
      message.error(err.message ?? "Failed to change password");
    } finally {
      setLoading(false);
    }
  }

  return (
    <Modal
      title="Change password"
      open={open}
      onCancel={() => { form.resetFields(); onClose(); }}
      onOk={() => form.submit()}
      okText="Update password"
      confirmLoading={loading}
      destroyOnHidden
    >
      <Form form={form} layout="vertical" onFinish={submit} requiredMark={false}>
        <Form.Item
          name="current_password"
          label="Current password"
          rules={[{ required: true, message: "Enter your current password" }]}
        >
          <Input.Password prefix={<LockOutlined style={{ color: "var(--muted)" }} />} autoComplete="current-password" />
        </Form.Item>
        <Form.Item
          name="new_password"
          label="New password"
          rules={[{ required: true, message: "Enter a new password" }, { min: 8, message: "At least 8 characters" }]}
        >
          <Input.Password prefix={<LockOutlined style={{ color: "var(--muted)" }} />} autoComplete="new-password" />
        </Form.Item>
        <Form.Item
          name="confirm_password"
          label="Confirm new password"
          dependencies={["new_password"]}
          rules={[
            { required: true, message: "Confirm your new password" },
            ({ getFieldValue }) => ({
              validator(_, value) {
                if (!value || getFieldValue("new_password") === value) return Promise.resolve();
                return Promise.reject(new Error("Passwords do not match"));
              },
            }),
          ]}
        >
          <Input.Password prefix={<LockOutlined style={{ color: "var(--muted)" }} />} autoComplete="new-password" />
        </Form.Item>
      </Form>
    </Modal>
  );
}

// ---------------------------------------------------------------------------
// Authenticated shell
// ---------------------------------------------------------------------------
function AppShell({ user, onLogout }) {
  const isGlobal = user.role === "global_admin";
  const [tab, setTab] = useState(isGlobal ? "companies" : "overview");
  const [moreOpen, setMoreOpen] = useState(false);
  const [pwOpen, setPwOpen] = useState(false);

  const nav = useMemo(() => visibleNav(user.role), [user.role]);

  // Bottom-nav primary set (mobile)
  const primaryIds = isGlobal
    ? ["companies", "globaladmins"]
    : ["overview", "calendar", "bookings", user.role === "admin" ? "approve" : "farmhouses"];
  const primary = primaryIds.map((id) => nav.find((n) => n.id === id)).filter(Boolean);
  const moreItems = nav.filter((n) => !primaryIds.includes(n.id));

  function go(id) {
    setTab(id);
    setMoreOpen(false);
    window.scrollTo({ top: 0, behavior: "auto" });
  }

  const railGroups = useMemo(() => {
    const groups = {};
    nav.forEach((n) => {
      (groups[n.group] ||= []).push(n);
    });
    return groups;
  }, [nav]);

  const pages = {
    companies: <CompaniesPage />,
    globaladmins: <GlobalAdminsPage user={user} />,
    overview: <OverviewPage user={user} onNavigate={go} />,
    calendar: <CalendarPage user={user} />,
    bookings: <BookingsPage user={user} />,
    approve: <ApproveQueue />,
    farmhouses: <FarmhousesPage user={user} />,
    bookies: <BookiesPage />,
    users: <UsersPage user={user} />,
    reports: <ReportsPage />,
    activity: <ActivityLogPage user={user} />,
    policies: <PoliciesPage user={user} />,
    settings: <SettingsPage />,
    blackouts: <BlackoutsManager />,
  };

  const roleLabel = isGlobal ? "Global admin" : user.role === "admin" ? "Administrator" : "Bookie";

  return (
    <div className="estate-shell">
      <header className="estate-topbar">
        <Brand sub={roleLabel} />
        <div className="topbar-actions">
          {!isGlobal && <NotificationBell />}
          <Dropdown
            placement="bottomRight"
            menu={{
              items: [
                { key: "who", label: <span style={{ fontWeight: 600 }}>{user.name || user.email}</span>, disabled: true },
                { type: "divider" },
                { key: "password", icon: <LockOutlined />, label: "Change password", onClick: () => setPwOpen(true) },
                { key: "logout", icon: <LogoutOutlined />, label: "Sign out", onClick: onLogout },
              ],
            }}
          >
            <Avatar
              style={{ background: "linear-gradient(150deg,#2E5246,#1F3D33)", color: "#E8D6A8", cursor: "pointer", fontWeight: 600 }}
            >
              {(user.name || user.email || "?").charAt(0).toUpperCase()}
            </Avatar>
          </Dropdown>
        </div>
      </header>

      <ChangePasswordModal open={pwOpen} onClose={() => setPwOpen(false)} />

      <div className="estate-body">
        <nav className="estate-rail" aria-label="Sections">
          {Object.entries(railGroups).map(([group, items]) => (
            <div key={group}>
              <div className="rail-section">{group}</div>
              {items.map((n) => (
                <button
                  key={n.id}
                  className={`rail-link${tab === n.id ? " active" : ""}`}
                  onClick={() => go(n.id)}
                >
                  {n.icon}
                  {n.label}
                </button>
              ))}
            </div>
          ))}
        </nav>

        <main className="estate-main">
          <AnimatePresence mode="wait">
            <motion.div
              key={tab}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -6 }}
              transition={{ duration: 0.28, ease: [0.22, 0.61, 0.36, 1] }}
            >
              {pages[tab]}
            </motion.div>
          </AnimatePresence>
        </main>
      </div>

      {/* Mobile bottom navigation */}
      <nav className="estate-bottomnav" aria-label="Primary">
        {primary.map((n) => (
          <button
            key={n.id}
            className={`bottomnav-item${tab === n.id ? " active" : ""}`}
            onClick={() => go(n.id)}
          >
            {n.icon}
            {n.label}
          </button>
        ))}
        <button
          className={`bottomnav-item${moreItems.some((m) => m.id === tab) ? " active" : ""}`}
          onClick={() => setMoreOpen(true)}
        >
          <EllipsisOutlined />
          More
        </button>
      </nav>

      <Drawer
        title="More"
        placement="bottom"
        size="auto"
        open={moreOpen}
        onClose={() => setMoreOpen(false)}
        styles={{ body: { padding: 14 } }}
      >
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 10 }}>
          {moreItems.map((n) => (
            <button
              key={n.id}
              onClick={() => go(n.id)}
              style={{
                border: "1px solid var(--hairline)",
                background: tab === n.id ? "#eaf0ec" : "var(--paper)",
                color: tab === n.id ? "var(--pine)" : "var(--ink)",
                borderRadius: 14,
                padding: "16px 8px",
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                gap: 7,
                cursor: "pointer",
                fontWeight: 600,
                fontSize: 12.5,
              }}
            >
              <span style={{ fontSize: 21, color: "var(--brass)" }}>{n.icon}</span>
              {n.label}
            </button>
          ))}
        </div>
      </Drawer>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Root
// ---------------------------------------------------------------------------
export default function App() {
  const [user, setUser] = useState(undefined);

  useEffect(() => {
    if (window.location.pathname === "/set-password") return;
    if (tokens.getAccess()) {
      getMe().then(setUser).catch(() => setUser(null));
    } else {
      setUser(null);
    }
  }, []);

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

  if (user === undefined) return null;
  if (!user) return <LoginPage onLogin={handleLogin} />;
  return <AppShell user={user} onLogout={handleLogout} />;
}
