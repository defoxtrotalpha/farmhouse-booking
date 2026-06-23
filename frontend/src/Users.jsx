import { useEffect, useState } from "react";
import {
  App as AntApp,
  Button,
  Card,
  Popconfirm,
  Skeleton,
  Switch,
  Tag,
  Tooltip,
} from "antd";
import {
  DeleteOutlined,
  CrownOutlined,
} from "@ant-design/icons";

import {
  listUsers,
  updateUser,
  deleteUser,
  cancelInvite,
} from "./api.js";
import { PageHeader, Stagger, StaggerItem, EmptyNote } from "./ui.jsx";
import { fmtDate } from "./theme.js";

function Initials({ name, email }) {
  const src = (name || email || "?").trim();
  const initials = src
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase())
    .join("");
  return (
    <span style={{
      width: 42, height: 42, borderRadius: 12, flexShrink: 0,
      display: "grid", placeItems: "center",
      background: "var(--pine)", color: "var(--linen)",
      fontFamily: "var(--font-display)", fontWeight: 600, fontSize: 15,
    }}>
      {initials}
    </span>
  );
}

export default function UsersPage({ user }) {
  const { message } = AntApp.useApp();
  const isAdmin = user?.role === "admin";
  const [users, setUsers] = useState(null);
  const [busyId, setBusyId] = useState(null);

  async function load() {
    try {
      setUsers(await listUsers({}));
    } catch (e) {
      message.error(e.message);
      setUsers([]);
    }
  }

  useEffect(() => {
    load();
  }, []); // eslint-disable-line

  async function toggle(u, next) {
    setBusyId(u.id);
    try {
      await updateUser(u.id, { is_active: next });
      message.success(next ? "Account enabled." : "Account disabled.");
      load();
    } catch (e) {
      message.error(e.message ?? "Could not update account");
    } finally {
      setBusyId(null);
    }
  }

  async function onCancelInvite(u) {
    setBusyId(u.id);
    try {
      await cancelInvite(u.id);
      message.success("Invite cancelled.");
      load();
    } catch (e) {
      message.error(e.message ?? "Could not cancel invite");
    } finally {
      setBusyId(null);
    }
  }

  async function onRemove(u) {
    setBusyId(u.id);
    try {
      await deleteUser(u.id);
      message.success("Removed.");
      load();
    } catch (e) {
      message.error(e.message ?? "Could not remove user");
    } finally {
      setBusyId(null);
    }
  }

  const admins = (users || []).filter((u) => u.role === "admin").length;
  const bookies = (users || []).filter((u) => u.role === "bookie").length;

  return (
    <div>
      <PageHeader
        eyebrow={isAdmin ? "Admin" : "Team"}
        title="All users"
        subtitle={
          isAdmin
            ? "Everyone in your company. You can disable or remove accounts — the primary admin is protected."
            : "Everyone in your company — admins and bookies."
        }
      />

      {users !== null && users.length > 0 && (
        <div className="muted" style={{ fontSize: 13, marginBottom: 12 }}>
          {admins} admin{admins === 1 ? "" : "s"} · {bookies} bookie{bookies === 1 ? "" : "s"}
        </div>
      )}

      {users === null ? (
        <Card><Skeleton active paragraph={{ rows: 4 }} /></Card>
      ) : users.length === 0 ? (
        <EmptyNote title="No users yet" hint="Add people from the Bookies tab." />
      ) : (
        <Stagger>
          {users.map((u) => {
            const isSelf = u.id === user?.id;
            return (
              <StaggerItem key={u.id}>
                <Card styles={{ body: { padding: 14 } }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                    <Initials name={u.name} email={u.email || u.username} />
                    <div style={{ minWidth: 0, flex: 1 }}>
                      <div style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: 16, display: "flex", alignItems: "center", gap: 8 }}>
                        {u.name || u.username || u.email}
                        {isSelf && <Tag style={{ borderRadius: 999 }}>You</Tag>}
                      </div>
                      <div className="muted" style={{ fontSize: 13, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {u.email || (u.username ? `@${u.username}` : "—")}
                      </div>
                      <div style={{ marginTop: 6, display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
                        <Tag color={u.role === "admin" ? "geekblue" : "default"} style={{ borderRadius: 999 }}>
                          {u.role === "admin" ? "Admin" : "Bookie"}
                        </Tag>
                        {u.is_primary && (
                          <Tag color="gold" icon={<CrownOutlined />} style={{ borderRadius: 999 }}>
                            Primary admin
                          </Tag>
                        )}
                        {u.accepted ? (
                          <Tag color="green" style={{ borderRadius: 999 }}>Accepted</Tag>
                        ) : (
                          <Tag color="gold" style={{ borderRadius: 999 }}>Pending invite</Tag>
                        )}
                        {!u.is_active && <Tag color="default" style={{ borderRadius: 999 }}>Disabled</Tag>}
                        <span className="muted" style={{ fontSize: 12 }}>Joined {fmtDate(u.created_at)}</span>
                      </div>
                    </div>

                    {isAdmin && (
                      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                        {u.accepted && (
                          u.is_primary || isSelf ? (
                            <Tooltip title={u.is_primary ? "The primary admin cannot be disabled" : "You cannot disable your own account"}>
                              <Switch checked={u.is_active} disabled />
                            </Tooltip>
                          ) : (
                            <Popconfirm
                              title={u.is_active ? "Disable this account?" : "Enable this account?"}
                              description={u.is_active ? "They will no longer be able to sign in." : "They will regain access."}
                              onConfirm={() => toggle(u, !u.is_active)}
                            >
                              <Switch checked={u.is_active} loading={busyId === u.id} />
                            </Popconfirm>
                          )
                        )}

                        {u.is_primary ? (
                          <Tooltip title="The primary admin cannot be removed">
                            <Button type="text" icon={<DeleteOutlined />} disabled />
                          </Tooltip>
                        ) : isSelf ? (
                          <Tooltip title="You cannot remove your own account">
                            <Button type="text" icon={<DeleteOutlined />} disabled />
                          </Tooltip>
                        ) : u.accepted ? (
                          <Popconfirm
                            title="Remove this user?"
                            description="This permanently deletes their account and their bookings."
                            okText="Remove"
                            okButtonProps={{ danger: true }}
                            onConfirm={() => onRemove(u)}
                          >
                            <Button danger type="text" icon={<DeleteOutlined />} loading={busyId === u.id} />
                          </Popconfirm>
                        ) : (
                          <Popconfirm
                            title="Cancel this invite?"
                            description="The pending account and its link will be removed."
                            okText="Cancel invite"
                            okButtonProps={{ danger: true }}
                            onConfirm={() => onCancelInvite(u)}
                          >
                            <Button danger type="text" icon={<DeleteOutlined />} loading={busyId === u.id}>
                              Cancel
                            </Button>
                          </Popconfirm>
                        )}
                      </div>
                    )}
                  </div>
                </Card>
              </StaggerItem>
            );
          })}
        </Stagger>
      )}
    </div>
  );
}
