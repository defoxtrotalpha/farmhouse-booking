import { motion } from "framer-motion";
import { Tag } from "antd";
import {
  statusOf,
  bookingNo,
  fmtDate,
  fmtTime,
  fmtDuration,
} from "./theme.js";

// ---------------------------------------------------------------------------
// Brand seal — a small estate "wax seal" mark (a sprig under an arch).
// ---------------------------------------------------------------------------
export function BrandSeal() {
  return (
    <span className="brand-seal" aria-hidden="true">
      <svg viewBox="0 0 24 24" fill="none">
        <path
          d="M12 21V11M12 11c0-2.6-1.7-4.4-4.2-4.7C7.6 8.9 9.3 10.7 12 11Zm0 0c0-2.6 1.7-4.4 4.2-4.7C16.4 8.9 14.7 10.7 12 11Z"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <path
          d="M5 21h14M6.5 21l.6-3.2a1 1 0 0 1 1-.8h7.8a1 1 0 0 1 1 .8l.6 3.2"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </span>
  );
}

export function Brand({ sub = "Estate Ledger" }) {
  return (
    <div className="brand-lockup">
      <BrandSeal />
      <div style={{ minWidth: 0 }}>
        <div className="brand-name">Estate Booking</div>
        <div className="brand-sub">{sub}</div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Status tag + wax-seal dot
// ---------------------------------------------------------------------------
export function StatusTag({ status, size }) {
  const s = statusOf(status);
  return (
    <Tag
      style={{
        color: s.color,
        background: s.bg,
        border: "none",
        fontWeight: 600,
        fontSize: size === "sm" ? 11.5 : 12.5,
        padding: size === "sm" ? "1px 9px" : "2px 11px",
        borderRadius: 999,
        margin: 0,
        textTransform: "capitalize",
      }}
    >
      {s.label}
    </Tag>
  );
}

export function SealDot({ status }) {
  const s = statusOf(status);
  return (
    <span
      className="seal-dot"
      style={{ background: s.dot, "--seal-ring": s.bg }}
    />
  );
}

// ---------------------------------------------------------------------------
// Page header — eyebrow / title / subtitle / actions
// ---------------------------------------------------------------------------
export function PageHeader({ eyebrow, title, subtitle, extra }) {
  return (
    <div
      className="page-head"
      style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", gap: 14, flexWrap: "wrap" }}
    >
      <div style={{ minWidth: 0 }}>
        {eyebrow && <div className="eyebrow">{eyebrow}</div>}
        <h1>{title}</h1>
        {subtitle && <p>{subtitle}</p>}
      </div>
      {extra && <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>{extra}</div>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Motion helpers — fade+rise page transition + staggered list reveal
// ---------------------------------------------------------------------------
export function MotionPage({ children, k }) {
  return (
    <motion.div
      key={k}
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.32, ease: [0.22, 0.61, 0.36, 1] }}
    >
      {children}
    </motion.div>
  );
}

export function Stagger({ children, gap = 12 }) {
  return (
    <motion.div
      style={{ display: "grid", gap }}
      initial="hidden"
      animate="show"
      variants={{ show: { transition: { staggerChildren: 0.045 } } }}
    >
      {children}
    </motion.div>
  );
}

export function StaggerItem({ children, ...rest }) {
  return (
    <motion.div
      variants={{
        hidden: { opacity: 0, y: 12 },
        show: { opacity: 1, y: 0, transition: { duration: 0.34, ease: [0.22, 0.61, 0.36, 1] } },
      }}
      {...rest}
    >
      {children}
    </motion.div>
  );
}

// ---------------------------------------------------------------------------
// Ledger card — the signature booking entry
// ---------------------------------------------------------------------------
export function LedgerCard({ booking, onClick, footer, showFarmhouse = true }) {
  const s = statusOf(booking.status);
  return (
    <div
      className={`ledger-card${onClick ? " tappable" : ""}`}
      style={{ "--edge": s.dot }}
      onClick={onClick}
      role={onClick ? "button" : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={onClick ? (e) => (e.key === "Enter" || e.key === " ") && onClick() : undefined}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10 }}>
        <span className="ledger-no mono">{bookingNo(booking.id)}</span>
        <StatusTag status={booking.status} size="sm" />
      </div>

      <div style={{ marginTop: 8, fontFamily: "var(--font-display)", fontSize: 17, fontWeight: 600, lineHeight: 1.2 }}>
        {booking.client_name || (showFarmhouse ? (booking.farmhouse_name || "—") : "Untitled hold")}
      </div>

      <div className="muted" style={{ fontSize: 13.5, marginTop: 3, display: "flex", flexWrap: "wrap", gap: "2px 8px" }}>
        {showFarmhouse && booking.client_name && booking.farmhouse_name && (
          <span>{booking.farmhouse_name}</span>
        )}
        {booking.event_type && <span>· {booking.event_type}</span>}
      </div>

      <div style={{ marginTop: 11, display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <span className="mono" style={{ fontSize: 13, fontWeight: 600 }}>
          {fmtDate(booking.start_at)}
        </span>
        <span className="muted" style={{ fontSize: 13 }}>
          {fmtTime(booking.start_at)} – {fmtTime(booking.end_at)}
        </span>
        <span
          style={{
            fontSize: 11,
            fontWeight: 600,
            color: "var(--brass)",
            background: "#f7efdc",
            borderRadius: 999,
            padding: "1px 8px",
          }}
        >
          {fmtDuration(booking.start_at, booking.end_at)}
        </span>
      </div>

      {booking.bookie_name && (
        <div className="muted" style={{ fontSize: 12.5, marginTop: 8 }}>
          Booked by {booking.bookie_name}
        </div>
      )}

      {footer && <div style={{ marginTop: 12 }}>{footer}</div>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Empty state
// ---------------------------------------------------------------------------
export function EmptyNote({ icon, title, hint }) {
  return (
    <div
      style={{
        textAlign: "center",
        padding: "44px 18px",
        color: "var(--muted)",
        border: "1px dashed var(--hairline)",
        borderRadius: 16,
        background: "rgba(255,255,255,0.45)",
      }}
    >
      {icon && <div style={{ fontSize: 30, marginBottom: 8, color: "var(--brass)" }}>{icon}</div>}
      <div style={{ fontFamily: "var(--font-display)", fontSize: 18, color: "var(--ink)" }}>{title}</div>
      {hint && <div style={{ fontSize: 14, marginTop: 5 }}>{hint}</div>}
    </div>
  );
}
