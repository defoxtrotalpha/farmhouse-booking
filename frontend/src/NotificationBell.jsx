import { useEffect, useState, useCallback, useRef } from "react";
import {
  listNotifications,
  unreadCount,
  markNotificationRead,
  markAllNotificationsRead,
} from "./api.js";

const POLL_MS = 30000;

function fmt(ts) {
  try {
    return new Date(ts).toLocaleString("en-GB", { timeZone: "Asia/Karachi" });
  } catch {
    return ts;
  }
}

export default function NotificationBell() {
  const [count, setCount] = useState(0);
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const boxRef = useRef(null);

  const refreshCount = useCallback(async () => {
    try {
      const { count } = await unreadCount();
      setCount(count);
    } catch {
      /* non-fatal */
    }
  }, []);

  const loadList = useCallback(async () => {
    setLoading(true);
    try {
      setItems(await listNotifications({ limit: 30 }));
    } catch {
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, []);

  // Poll the unread count
  useEffect(() => {
    refreshCount();
    const t = setInterval(refreshCount, POLL_MS);
    return () => clearInterval(t);
  }, [refreshCount]);

  // Close on outside click
  useEffect(() => {
    function onClick(e) {
      if (boxRef.current && !boxRef.current.contains(e.target)) setOpen(false);
    }
    if (open) document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [open]);

  async function toggle() {
    const next = !open;
    setOpen(next);
    if (next) await loadList();
  }

  async function handleRead(n) {
    if (!n.is_read) {
      try {
        await markNotificationRead(n.id);
        setItems((prev) => prev.map((x) => (x.id === n.id ? { ...x, is_read: true } : x)));
        refreshCount();
      } catch {
        /* ignore */
      }
    }
  }

  async function handleReadAll() {
    try {
      await markAllNotificationsRead();
      setItems((prev) => prev.map((x) => ({ ...x, is_read: true })));
      setCount(0);
    } catch {
      /* ignore */
    }
  }

  return (
    <div ref={boxRef} style={{ position: "relative" }}>
      <button
        onClick={toggle}
        aria-label="Notifications"
        style={{ position: "relative", cursor: "pointer", background: "none", border: "none", fontSize: "1.3rem" }}
      >
        <span role="img" aria-hidden="true">🔔</span>
        {count > 0 && (
          <span
            style={{
              position: "absolute",
              top: -4,
              right: -6,
              background: "#b00020",
              color: "#fff",
              borderRadius: "999px",
              fontSize: "0.65rem",
              minWidth: 16,
              height: 16,
              lineHeight: "16px",
              padding: "0 4px",
              textAlign: "center",
            }}
          >
            {count > 99 ? "99+" : count}
          </span>
        )}
      </button>

      {open && (
        <div
          style={{
            position: "absolute",
            right: 0,
            top: "2rem",
            width: 340,
            maxHeight: 420,
            overflowY: "auto",
            background: "#fff",
            border: "1px solid #e5e5e5",
            borderRadius: 10,
            boxShadow: "0 6px 24px rgba(0,0,0,0.12)",
            zIndex: 100,
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "0.6rem 0.9rem", borderBottom: "1px solid #eee" }}>
            <strong style={{ fontSize: "0.9rem" }}>Notifications</strong>
            <button onClick={handleReadAll} style={{ fontSize: "0.75rem", cursor: "pointer", background: "none", border: "none", color: "#1565c0" }}>
              Mark all read
            </button>
          </div>

          {loading && <p style={{ padding: "0.9rem", margin: 0, color: "#666" }}>Loading…</p>}
          {!loading && items.length === 0 && (
            <p style={{ padding: "0.9rem", margin: 0, color: "#666" }}>No notifications.</p>
          )}
          {!loading &&
            items.map((n) => (
              <div
                key={n.id}
                onClick={() => handleRead(n)}
                style={{
                  padding: "0.6rem 0.9rem",
                  borderBottom: "1px solid #f2f2f2",
                  cursor: "pointer",
                  background: n.is_read ? "#fff" : "#f0f7ff",
                }}
              >
                <div style={{ fontSize: "0.85rem", fontWeight: n.is_read ? 400 : 600 }}>{n.title}</div>
                {n.body && <div style={{ fontSize: "0.78rem", color: "#555", marginTop: 2 }}>{n.body}</div>}
                <div style={{ fontSize: "0.7rem", color: "#999", marginTop: 4 }}>{fmt(n.created_at)}</div>
              </div>
            ))}
        </div>
      )}
    </div>
  );
}
