import { useEffect, useState } from "react";
import { App as AntApp, Button, Card, Popconfirm, Skeleton, Timeline, Tag } from "antd";
import { ReloadOutlined, HistoryOutlined, DeleteOutlined } from "@ant-design/icons";

import { listActivity, clearActivity } from "./api.js";
import { PageHeader, EmptyNote } from "./ui.jsx";
import { fmtDateTime, STATUS } from "./theme.js";

const PAGE = 50;

// Map raw action codes to readable labels + a dot colour
const ACTION_META = {
  "booking.hold": { label: "Hold placed", color: STATUS.hold.dot },
  "booking.submitted": { label: "Request submitted", color: STATUS.pending.dot },
  "booking.approved": { label: "Booking confirmed", color: STATUS.booked.dot },
  "booking.rejected": { label: "Request rejected", color: STATUS.rejected.dot },
  "booking.canceled": { label: "Booking canceled", color: STATUS.canceled.dot },
  "booking.withdrawn": { label: "Withdrawn", color: STATUS.canceled.dot },
  "booking.cancel_requested": { label: "Cancellation requested", color: STATUS.rejected.dot },
  "booking.expired": { label: "Hold expired", color: STATUS.expired.dot },
  "invite.created": { label: "Bookie invited", color: "var(--brass)" },
  "invite.accepted": { label: "Invite accepted", color: STATUS.booked.dot },
  "farmhouse.created": { label: "Estate added", color: "var(--pine)" },
  "farmhouse.updated": { label: "Estate updated", color: "var(--pine)" },
};

function metaFor(action) {
  return ACTION_META[action] ?? { label: action.replace(/[._]/g, " "), color: "var(--muted)" };
}

export default function ActivityLogPage({ user }) {
  const { message } = AntApp.useApp();
  const [items, setItems] = useState(null);
  const [offset, setOffset] = useState(0);
  const [more, setMore] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [clearing, setClearing] = useState(false);
  const isAdmin = user?.role === "admin";

  async function onClear() {
    setClearing(true);
    try {
      await clearActivity();
      message.success("Activity log cleared.");
      setOffset(0);
      load(true);
    } catch (e) {
      message.error(e.message ?? "Could not clear activity");
    } finally {
      setClearing(false);
    }
  }

  async function load(reset = false) {
    try {
      const off = reset ? 0 : offset;
      const batch = await listActivity({ limit: PAGE, offset: off });
      setMore(batch.length === PAGE);
      setItems((prev) => (reset || prev === null ? batch : [...prev, ...batch]));
      setOffset(off + batch.length);
    } catch (e) {
      message.error(e.message);
      setItems([]);
    }
  }

  useEffect(() => {
    load(true);
  }, []); // eslint-disable-line

  async function loadMore() {
    setLoadingMore(true);
    await load(false);
    setLoadingMore(false);
  }

  return (
    <div>
      <PageHeader
        eyebrow="Records"
        title="Activity log"
        subtitle="A running ledger of every action across the company."
        extra={
          <div style={{ display: "flex", gap: 8 }}>
            <Button icon={<ReloadOutlined />} onClick={() => { setOffset(0); load(true); }}>Refresh</Button>
            {isAdmin && (
              <Popconfirm
                title="Clear your activity?"
                description="This removes only the log entries you created. Other admins' entries are untouched."
                okText="Clear"
                okButtonProps={{ danger: true }}
                onConfirm={onClear}
              >
                <Button danger icon={<DeleteOutlined />} loading={clearing}>Clear</Button>
              </Popconfirm>
            )}
          </div>
        }
      />

      <Card>
        {items === null ? (
          <Skeleton active paragraph={{ rows: 6 }} />
        ) : items.length === 0 ? (
          <EmptyNote icon={<HistoryOutlined />} title="No activity yet" hint="Actions will appear here as they happen." />
        ) : (
          <>
            <Timeline
              items={items.map((a) => {
                const m = metaFor(a.action);
                return {
                  color: m.color,
                  content: (
                    <div>
                      <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                        <span style={{ fontWeight: 600 }}>{m.label}</span>
                        {a.target_type && (
                          <Tag style={{ borderRadius: 999, margin: 0, fontSize: 11 }}>
                            {a.target_type}{a.target_id ? ` #${a.target_id}` : ""}
                          </Tag>
                        )}
                      </div>
                      {a.note && <div className="muted" style={{ fontSize: 13, marginTop: 2 }}>{a.note}</div>}
                      <div className="muted mono" style={{ fontSize: 12, marginTop: 2 }}>{fmtDateTime(a.created_at)}</div>
                    </div>
                  ),
                };
              })}
            />
            {more && (
              <div style={{ textAlign: "center", marginTop: 8 }}>
                <Button onClick={loadMore} loading={loadingMore}>Load more</Button>
              </div>
            )}
          </>
        )}
      </Card>
    </div>
  );
}
