import { useEffect, useState } from "react";
import {
  App as AntApp,
  Button,
  Card,
  Form,
  Input,
  Modal,
  Popconfirm,
  Skeleton,
  Tag,
  Tooltip,
} from "antd";
import {
  CrownOutlined,
  DeleteOutlined,
  PlusOutlined,
  ReloadOutlined,
} from "@ant-design/icons";

import {
  listGlobalAdmins,
  createGlobalAdmin,
  deleteGlobalAdmin,
} from "./api.js";
import { PageHeader, Stagger, StaggerItem, EmptyNote } from "./ui.jsx";
import { fmtDate } from "./theme.js";

function AdminBadge({ name, email }) {
  const initials = (name || email || "?")
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase())
    .join("");
  return (
    <span style={{
      width: 46, height: 46, borderRadius: 13, flexShrink: 0,
      display: "grid", placeItems: "center",
      background: "linear-gradient(150deg,#2E5246,#1F3D33)", color: "#E8D6A8",
      fontFamily: "var(--font-display)", fontWeight: 600, fontSize: 16,
    }}>
      {initials || <CrownOutlined />}
    </span>
  );
}

export default function GlobalAdminsPage({ user }) {
  const { message } = AntApp.useApp();
  const [admins, setAdmins] = useState(null);
  const [busyId, setBusyId] = useState(null);
  const [addOpen, setAddOpen] = useState(false);
  const [adding, setAdding] = useState(false);
  const [form] = Form.useForm();

  async function load() {
    try {
      setAdmins(await listGlobalAdmins());
    } catch (e) {
      message.error(e.message ?? "Failed to load global admins");
      setAdmins([]);
    }
  }

  useEffect(() => {
    load();
  }, []); // eslint-disable-line

  async function onAdd(values) {
    setAdding(true);
    try {
      await createGlobalAdmin({
        name: values.name.trim(),
        email: values.email.trim(),
        password: values.password,
      });
      message.success("Global admin added.");
      form.resetFields();
      setAddOpen(false);
      load();
    } catch (e) {
      message.error(e.message ?? "Could not add global admin");
    } finally {
      setAdding(false);
    }
  }

  async function onRemove(a) {
    setBusyId(a.id);
    try {
      await deleteGlobalAdmin(a.id);
      message.success("Global admin removed.");
      load();
    } catch (e) {
      message.error(e.message ?? "Could not remove global admin");
    } finally {
      setBusyId(null);
    }
  }

  const isLast = (admins ?? []).length <= 1;

  return (
    <>
      <PageHeader
        eyebrow="Platform"
        title="Global admins"
        subtitle="Global admins govern the whole platform. At least one must always remain."
        extra={[
          <Button key="refresh" icon={<ReloadOutlined />} onClick={load}>
            Refresh
          </Button>,
          <Button key="add" type="primary" icon={<PlusOutlined />} onClick={() => setAddOpen(true)}>
            Add global admin
          </Button>,
        ]}
      />

      {admins === null ? (
        <Card><Skeleton active paragraph={{ rows: 3 }} /></Card>
      ) : admins.length === 0 ? (
        <EmptyNote
          icon={<CrownOutlined />}
          title="No global admins"
          hint="Add a global admin to govern the platform."
        />
      ) : (
        <Stagger gap={12}>
          {admins.map((a) => (
            <StaggerItem key={a.id}>
              <Card styles={{ body: { padding: 16 } }}>
                <div style={{ display: "flex", gap: 14, alignItems: "center", flexWrap: "wrap" }}>
                  <AdminBadge name={a.name} email={a.email} />
                  <div style={{ flex: 1, minWidth: 200 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                      <span style={{ fontFamily: "var(--font-display)", fontSize: 18, fontWeight: 600 }}>
                        {a.name}
                      </span>
                      {user?.id === a.id && <Tag color="green">You</Tag>}
                    </div>
                    <div className="muted" style={{ fontSize: 13, marginTop: 4 }}>
                      {a.email}
                    </div>
                    <div className="muted" style={{ fontSize: 12.5, marginTop: 3 }}>
                      Added {fmtDate(a.created_at)}
                    </div>
                  </div>
                  <Popconfirm
                    title="Remove this global admin?"
                    description={user?.id === a.id ? "You will lose your own platform access." : "They will lose platform access."}
                    okText="Remove"
                    okButtonProps={{ danger: true }}
                    disabled={isLast}
                    onConfirm={() => onRemove(a)}
                  >
                    <Tooltip title={isLast ? "At least one global admin must remain" : "Remove global admin"}>
                      <Button danger icon={<DeleteOutlined />} loading={busyId === a.id} disabled={isLast}>
                        Remove
                      </Button>
                    </Tooltip>
                  </Popconfirm>
                </div>
              </Card>
            </StaggerItem>
          ))}
        </Stagger>
      )}

      <Modal
        title="Add a global admin"
        open={addOpen}
        onCancel={() => { form.resetFields(); setAddOpen(false); }}
        onOk={() => form.submit()}
        okText="Add global admin"
        confirmLoading={adding}
        destroyOnHidden
      >
        <Form form={form} layout="vertical" onFinish={onAdd} requiredMark={false}>
          <Form.Item
            name="name"
            label="Name"
            rules={[{ required: true, message: "Enter a name" }]}
          >
            <Input placeholder="Alex Morgan" />
          </Form.Item>
          <Form.Item
            name="email"
            label="Email"
            rules={[
              { required: true, message: "Enter an email" },
              { type: "email", message: "Enter a valid email" },
            ]}
          >
            <Input placeholder="alex@platform.com" />
          </Form.Item>
          <Form.Item
            name="password"
            label="Temporary password"
            rules={[{ required: true, message: "Enter a password" }, { min: 8, message: "At least 8 characters" }]}
          >
            <Input.Password placeholder="••••••••" />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
}
