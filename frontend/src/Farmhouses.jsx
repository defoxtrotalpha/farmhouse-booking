import { useEffect, useState } from "react";
import {
  App as AntApp,
  Button,
  Card,
  Form,
  Input,
  InputNumber,
  Modal,
  Skeleton,
  Switch,
  Tag,
} from "antd";
import { EditOutlined, PlusOutlined, HomeOutlined } from "@ant-design/icons";

import { listFarmhouses, createFarmhouse, updateFarmhouse } from "./api.js";
import { PageHeader, Stagger, StaggerItem, EmptyNote } from "./ui.jsx";

function FarmhouseModal({ open, initial, onClose, onSaved }) {
  const { message } = AntApp.useApp();
  const [form] = Form.useForm();
  const [busy, setBusy] = useState(false);
  const editing = !!initial;

  useEffect(() => {
    if (open) {
      form.setFieldsValue(
        initial ?? { name: "", description: "", capacity: undefined, buffer_minutes: 0 }
      );
    }
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
      const payload = {
        name: v.name.trim(),
        description: v.description?.trim() || "",
        capacity: v.capacity ?? null,
        buffer_minutes: v.buffer_minutes ?? 0,
      };
      if (editing) await updateFarmhouse(initial.id, payload);
      else await createFarmhouse(payload);
      message.success(editing ? "Estate updated." : "Estate added.");
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
      title={editing ? "Edit estate" : "Add estate"}
      okText={editing ? "Save" : "Add"}
      confirmLoading={busy}
      onOk={submit}
      onCancel={onClose}
    >
      <Form form={form} layout="vertical" requiredMark={false}>
        <Form.Item name="name" label="Name" rules={[{ required: true, message: "Name is required" }]}>
          <Input placeholder="e.g. Orchard House" />
        </Form.Item>
        <Form.Item name="description" label="Description">
          <Input.TextArea rows={2} placeholder="A short note about this venue" />
        </Form.Item>
        <div className="two-col">
          <Form.Item name="capacity" label="Capacity">
            <InputNumber min={0} style={{ width: "100%" }} placeholder="Guests" />
          </Form.Item>
          <Form.Item name="buffer_minutes" label="Turnover buffer (min)" tooltip="Gap enforced before and after each booking">
            <InputNumber min={0} step={15} style={{ width: "100%" }} />
          </Form.Item>
        </div>
      </Form>
    </Modal>
  );
}

export default function FarmhousesPage({ user }) {
  const { message } = AntApp.useApp();
  const isAdmin = user.role === "admin";
  const [list, setList] = useState(null);
  const [modal, setModal] = useState({ open: false, initial: null });
  const [busyId, setBusyId] = useState(null);

  async function load() {
    try {
      setList(await listFarmhouses({ includeDisabled: isAdmin }));
    } catch (e) {
      message.error(e.message);
      setList([]);
    }
  }

  useEffect(() => {
    load();
  }, []); // eslint-disable-line

  async function toggle(f) {
    setBusyId(f.id);
    const next = f.status === "active" ? "disabled" : "active";
    try {
      await updateFarmhouse(f.id, { status: next });
      message.success(next === "active" ? "Estate enabled." : "Estate disabled.");
      load();
    } catch (e) {
      message.error(e.message);
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div>
      <PageHeader
        eyebrow="Estate"
        title="Estates"
        subtitle={isAdmin ? "Manage the venues available for booking, their capacity, and turnover buffers." : "The venues you can book."}
        extra={isAdmin ? <Button type="primary" icon={<PlusOutlined />} onClick={() => setModal({ open: true, initial: null })}>Add estate</Button> : null}
      />

      {list === null ? (
        <Card><Skeleton active paragraph={{ rows: 3 }} /></Card>
      ) : list.length === 0 ? (
        <EmptyNote icon={<HomeOutlined />} title="No estates" hint={isAdmin ? "Add your first venue to start taking bookings." : "Nothing here yet."} />
      ) : (
        <Stagger>
          {list.map((f) => (
            <StaggerItem key={f.id}>
              <Card styles={{ body: { padding: 16 } }} style={f.status !== "active" ? { opacity: 0.66 } : undefined}>
                <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "flex-start" }}>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <span style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: 18 }}>{f.name}</span>
                      {f.status !== "active" && <Tag style={{ borderRadius: 999 }}>Disabled</Tag>}
                    </div>
                    {f.description && <p className="muted" style={{ fontSize: 13.5, margin: "6px 0 0" }}>{f.description}</p>}
                    <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 10 }}>
                      {f.capacity != null && (
                        <Tag style={{ borderRadius: 999, background: "var(--linen)", border: "1px solid var(--hairline)" }}>
                          {f.capacity} guests
                        </Tag>
                      )}
                      <Tag style={{ borderRadius: 999, background: "var(--linen)", border: "1px solid var(--hairline)" }}>
                        {f.buffer_minutes} min buffer
                      </Tag>
                    </div>
                  </div>
                  {isAdmin && (
                    <div style={{ display: "flex", flexDirection: "column", gap: 10, alignItems: "flex-end" }}>
                      <Button size="small" icon={<EditOutlined />} onClick={() => setModal({ open: true, initial: f })}>
                        Edit
                      </Button>
                      <Switch
                        checked={f.status === "active"}
                        loading={busyId === f.id}
                        onChange={() => toggle(f)}
                      />
                    </div>
                  )}
                </div>
              </Card>
            </StaggerItem>
          ))}
        </Stagger>
      )}

      <FarmhouseModal
        open={modal.open}
        initial={modal.initial}
        onClose={() => setModal({ open: false, initial: null })}
        onSaved={load}
      />
    </div>
  );
}
