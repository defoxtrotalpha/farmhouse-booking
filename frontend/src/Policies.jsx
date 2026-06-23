import { useEffect, useState } from "react";
import {
  App as AntApp,
  Button,
  Card,
  Form,
  Input,
  Modal,
  Skeleton,
  Tag,
} from "antd";
import { EditOutlined, PlusOutlined, FileTextOutlined } from "@ant-design/icons";

import { listPolicies, createPolicy, updatePolicy } from "./api.js";
import { PageHeader, Stagger, StaggerItem, EmptyNote } from "./ui.jsx";
import { fmtDate } from "./theme.js";

function PolicyModal({ open, initial, onClose, onSaved }) {
  const { message } = AntApp.useApp();
  const [form] = Form.useForm();
  const [busy, setBusy] = useState(false);
  const editing = !!initial;

  useEffect(() => {
    if (open) form.setFieldsValue(initial ?? { title: "", body: "" });
  }, [open, initial, form]);

  async function submit() {
    let v;
    try {
      v = await form.validateFields();
    } catch {
      return;
    }
    setBusy(true);
    try {
      const payload = { title: v.title.trim(), body: v.body };
      if (editing) await updatePolicy(initial.id, payload);
      else await createPolicy(payload);
      message.success(editing ? "Policy updated." : "Policy created.");
      onSaved();
      onClose();
    } catch (e) {
      message.error(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open={open}
      title={editing ? "Edit policy" : "New policy"}
      okText={editing ? "Save" : "Create"}
      confirmLoading={busy}
      onOk={submit}
      onCancel={onClose}
      width={620}
    >
      <Form form={form} layout="vertical" requiredMark={false}>
        <Form.Item name="title" label="Title" rules={[{ required: true, message: "Title is required" }]}>
          <Input placeholder="e.g. Cancellation terms" />
        </Form.Item>
        <Form.Item name="body" label="Content" rules={[{ required: true, message: "Add some content" }]}>
          <Input.TextArea rows={8} placeholder="Write the policy text…" />
        </Form.Item>
      </Form>
    </Modal>
  );
}

export default function PoliciesPage({ user }) {
  const { message } = AntApp.useApp();
  const isAdmin = user.role === "admin";
  const [list, setList] = useState(null);
  const [modal, setModal] = useState({ open: false, initial: null });

  async function load() {
    try {
      setList(await listPolicies());
    } catch (e) {
      message.error(e.message);
      setList([]);
    }
  }

  useEffect(() => {
    load();
  }, []); // eslint-disable-line

  return (
    <div>
      <PageHeader
        eyebrow="Records"
        title="Policies & terms"
        subtitle={isAdmin ? "Maintain the booking policies and terms shared with the team." : "Booking policies and terms."}
        extra={isAdmin ? <Button type="primary" icon={<PlusOutlined />} onClick={() => setModal({ open: true, initial: null })}>New policy</Button> : null}
      />

      {list === null ? (
        <Card><Skeleton active paragraph={{ rows: 4 }} /></Card>
      ) : list.length === 0 ? (
        <EmptyNote icon={<FileTextOutlined />} title="No policies yet" hint={isAdmin ? "Create your first policy above." : "Nothing published yet."} />
      ) : (
        <Stagger>
          {list.map((p) => (
            <StaggerItem key={p.id}>
              <Card styles={{ body: { padding: 18 } }}>
                <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "flex-start" }}>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                      <span style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: 19 }}>{p.title}</span>
                      <Tag style={{ borderRadius: 999 }}>v{p.version}</Tag>
                    </div>
                    <div className="muted" style={{ fontSize: 12.5, marginTop: 2 }}>Updated {fmtDate(p.updated_at)}</div>
                  </div>
                  {isAdmin && (
                    <Button size="small" icon={<EditOutlined />} onClick={() => setModal({ open: true, initial: p })}>
                      Edit
                    </Button>
                  )}
                </div>
                <p style={{ whiteSpace: "pre-wrap", margin: "14px 0 0", lineHeight: 1.6, color: "var(--ink)" }}>
                  {p.body}
                </p>
              </Card>
            </StaggerItem>
          ))}
        </Stagger>
      )}

      <PolicyModal
        open={modal.open}
        initial={modal.initial}
        onClose={() => setModal({ open: false, initial: null })}
        onSaved={load}
      />
    </div>
  );
}
