import { useEffect, useState, useCallback, useRef } from "react";
import { Badge, Button, Empty, Popover, Spin } from "antd";
import { BellOutlined, CheckOutlined } from "@ant-design/icons";
import {
  listNotifications,
  unreadCount,
  markNotificationRead,
  markAllNotificationsRead,
} from "./api.js";
import { fmtDateTime } from "./theme.js";

const POLL_MS = 30000;

export default function NotificationBell() {
  const [count, setCount] = useState(0);
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const mounted = useRef(true);

  const refreshCount = useCallback(async () => {
    try {
      const { count } = await unreadCount();
      if (mounted.current) setCount(count);
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

  useEffect(() => {
    mounted.current = true;
    refreshCount();
    const t = setInterval(refreshCount, POLL_MS);
    return () => {
      mounted.current = false;
      clearInterval(t);
    };
  }, [refreshCount]);

  function onOpenChange(next) {
    setOpen(next);
    if (next) loadList();
  }

  async function handleRead(n) {
    if (n.is_read) return;
    try {
      await markNotificationRead(n.id);
      setItems((prev) => prev.map((x) => (x.id === n.id ? { ...x, is_read: true } : x)));
      refreshCount();
    } catch {
      /* ignore */
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

  const content = (
    <div style={{ width: 320, maxWidth: "78vw" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
        <span style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: 16 }}>Notifications</span>
        <Button type="link" size="small" icon={<CheckOutlined />} onClick={handleReadAll} style={{ paddingRight: 0 }}>
          Mark all read
        </Button>
      </div>
      <div style={{ maxHeight: 380, overflowY: "auto", margin: "0 -6px" }}>
        {loading ? (
          <div style={{ padding: 24, textAlign: "center" }}>
            <Spin />
          </div>
        ) : items.length === 0 ? (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="You're all caught up" style={{ padding: "18px 0" }} />
        ) : (
          items.map((n) => (
            <button
              key={n.id}
              onClick={() => handleRead(n)}
              style={{
                display: "block",
                width: "100%",
                textAlign: "left",
                border: "none",
                cursor: "pointer",
                borderRadius: 12,
                padding: "10px 10px",
                marginBottom: 2,
                background: n.is_read ? "transparent" : "#f6efdd",
              }}
            >
              <div style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
                {!n.is_read && (
                  <span style={{ width: 7, height: 7, borderRadius: 999, background: "var(--brass)", marginTop: 6, flex: "none" }} />
                )}
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontWeight: n.is_read ? 500 : 700, fontSize: 14, lineHeight: 1.3 }}>{n.title}</div>
                  {n.body && <div className="muted" style={{ fontSize: 12.5, marginTop: 2 }}>{n.body}</div>}
                  <div className="muted mono" style={{ fontSize: 11, marginTop: 4 }}>{fmtDateTime(n.created_at)}</div>
                </div>
              </div>
            </button>
          ))
        )}
      </div>
    </div>
  );

  return (
    <Popover content={content} trigger="click" open={open} onOpenChange={onOpenChange} placement="bottomRight" arrow={false}>
      <Badge count={count} size="small" offset={[-2, 2]} color="#A8453A">
        <Button type="text" shape="circle" size="large" icon={<BellOutlined style={{ fontSize: 19 }} />} aria-label="Notifications" />
      </Badge>
    </Popover>
  );
}
