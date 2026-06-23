import { useEffect, useMemo, useState } from "react";
import { Button, Card, Skeleton } from "antd";
import {
  CalendarOutlined,
  CheckCircleOutlined,
  PlusOutlined,
  ArrowRightOutlined,
} from "@ant-design/icons";
import { listBookings, listFarmhouses } from "./api.js";
import {
  PageHeader,
  Stagger,
  StaggerItem,
  LedgerCard,
  EmptyNote,
  StatusTag,
} from "./ui.jsx";
import { statusOf } from "./theme.js";

function greeting() {
  const h = Number(new Date().toLocaleString("en-GB", { timeZone: "Asia/Karachi", hour: "2-digit", hour12: false }));
  if (h < 12) return "Good morning";
  if (h < 17) return "Good afternoon";
  return "Good evening";
}

function StatTile({ label, value, accent }) {
  return (
    <div
      style={{
        background: "var(--paper)",
        border: "1px solid var(--hairline)",
        borderRadius: 16,
        padding: "15px 16px",
        minWidth: 0,
      }}
    >
      <div className="eyebrow" style={{ color: accent || "var(--brass)" }}>{label}</div>
      <div style={{ fontFamily: "var(--font-display)", fontSize: 30, fontWeight: 600, lineHeight: 1.1, marginTop: 4 }}>
        {value}
      </div>
    </div>
  );
}

export default function OverviewPage({ user, onNavigate }) {
  const isAdmin = user.role === "admin";
  const company = user.tenant_name || "Your company";
  const today = new Date().toLocaleDateString("en-GB", { timeZone: "Asia/Karachi", weekday: "long", day: "numeric", month: "long" });
  const [bookings, setBookings] = useState(null);
  const [fhCount, setFhCount] = useState(null);

  useEffect(() => {
    let on = true;
    listBookings().then((d) => on && setBookings(d)).catch(() => on && setBookings([]));
    listFarmhouses().then((d) => on && setFhCount(d.length)).catch(() => on && setFhCount(0));
    return () => { on = false; };
  }, []);

  const stats = useMemo(() => {
    const b = bookings ?? [];
    const by = (s) => b.filter((x) => x.status === s).length;
    return { hold: by("hold"), pending: by("pending"), booked: by("booked") };
  }, [bookings]);

  const upcoming = useMemo(() => {
    const now = Date.now();
    return (bookings ?? [])
      .filter((b) => ["pending", "booked"].includes(b.status) && new Date(b.end_at).getTime() >= now)
      .sort((a, b) => new Date(a.start_at) - new Date(b.start_at))
      .slice(0, 4);
  }, [bookings]);

  return (
    <div>
      <PageHeader
        eyebrow={company}
        title={`${greeting()}, ${(user.name || user.email).split(" ")[0]}`}
        subtitle={isAdmin ? `${today} — your company at a glance: pending approvals, confirmed dates, and what's coming up.` : `${today} — here's where your holds and bookings stand right now.`}
      />

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))", gap: 12, marginBottom: 22 }}>
        {bookings === null ? (
          <Skeleton active paragraph={{ rows: 2 }} />
        ) : (
          <>
            <StatTile label="Holds" value={stats.hold} accent={statusOf("hold").color} />
            <StatTile label={isAdmin ? "Awaiting approval" : "Pending"} value={stats.pending} accent={statusOf("pending").color} />
            <StatTile label="Confirmed" value={stats.booked} accent={statusOf("booked").color} />
            <StatTile label="Estates" value={fhCount ?? "—"} />
          </>
        )}
      </div>

      <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginBottom: 26 }}>
        <Button type="primary" size="large" icon={<CalendarOutlined />} onClick={() => onNavigate("calendar")}>
          Open calendar
        </Button>
        {isAdmin ? (
          <Button size="large" icon={<CheckCircleOutlined />} onClick={() => onNavigate("approve")}>
            Review approvals{stats.pending ? ` (${stats.pending})` : ""}
          </Button>
        ) : (
          <Button size="large" icon={<PlusOutlined />} onClick={() => onNavigate("calendar")}>
            Place a hold
          </Button>
        )}
      </div>

      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: 12 }}>
        <h2 style={{ margin: 0, fontSize: 20 }}>Coming up</h2>
        <Button type="link" onClick={() => onNavigate("bookings")} style={{ paddingRight: 0 }}>
          All bookings <ArrowRightOutlined />
        </Button>
      </div>

      {bookings === null ? (
        <Card><Skeleton active /></Card>
      ) : upcoming.length === 0 ? (
        <EmptyNote
          icon={<CalendarOutlined />}
          title="Nothing on the horizon"
          hint={isAdmin ? "Confirmed and pending events will appear here." : "Place a hold on the calendar to get started."}
        />
      ) : (
        <Stagger>
          {upcoming.map((b) => (
            <StaggerItem key={b.id}>
              <LedgerCard booking={b} onClick={() => onNavigate("bookings")} footer={
                b.status === "pending" ? <StatusTag status="pending" size="sm" /> : null
              } />
            </StaggerItem>
          ))}
        </Stagger>
      )}
    </div>
  );
}
