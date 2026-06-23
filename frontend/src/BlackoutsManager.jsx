import { useEffect, useState } from "react";
import {
  App as AntApp,
  Button,
  Card,
  DatePicker,
  Form,
  Input,
  Popconfirm,
  Select,
  Skeleton,
} from "antd";
import { DeleteOutlined, PlusOutlined, StopOutlined } from "@ant-design/icons";

import {
  listBlackouts,
  createBlackout,
  deleteBlackout,
  listFarmhouses,
} from "./api.js";
import { PageHeader, Stagger, StaggerItem, EmptyNote } from "./ui.jsx";
import { fmtDate } from "./theme.js";

const { RangePicker } = DatePicker;

export default function BlackoutsManager() {
  const { message } = AntApp.useApp();
  const [form] = Form.useForm();
  const [blackouts, setBlackouts] = useState(null);
  const [farmhouses, setFarmhouses] = useState([]);
  const [saving, setSaving] = useState(false);
  const [busyId, setBusyId] = useState(null);

  async function load() {
    try {
      const [b, f] = await Promise.all([
        listBlackouts(),
        listFarmhouses({ includeDisabled: true }),
      ]);
      setBlackouts(b);
      setFarmhouses(f);
    } catch (e) {
      message.error(e.message);
      setBlackouts([]);
    }
  }

  useEffect(() => {
    load();
  }, []); // eslint-disable-line

  async function add(v) {
    if (!v.range || v.range.length !== 2) return message.warning("Pick a date range.");
    setSaving(true);
    try {
      await createBlackout({
        farmhouse_id: v.farmhouse_id ?? null,
        start_date: v.range[0].format("YYYY-MM-DD"),
        end_date: v.range[1].format("YYYY-MM-DD"),
        reason: v.reason?.trim() || null,
      });
      message.success("Blackout added.");
      form.resetFields();
      load();
    } catch (e) {
      message.error(e.message);
    } finally {
      setSaving(false);
    }
  }

  async function remove(id) {
    setBusyId(id);
    try {
      await deleteBlackout(id);
      message.success("Blackout removed.");
      load();
    } catch (e) {
      message.error(e.message);
    } finally {
      setBusyId(null);
    }
  }

  const fhName = (id) => (id == null ? "All estates" : farmhouses.find((f) => f.id === id)?.name ?? `#${id}`);

  return (
    <div>
      <PageHeader
        eyebrow="Admin"
        title="Blackout dates"
        subtitle="Block out dates when no bookings can be made — estate-wide or for a single farmhouse."
      />

      <Card style={{ marginBottom: 18 }} title="Add a blackout">
        <Form form={form} layout="vertical" onFinish={add} requiredMark={false}>
          <div className="two-col">
            <Form.Item name="range" label="Dates" rules={[{ required: true, message: "Pick a date range" }]}>
              <RangePicker style={{ width: "100%" }} format="DD MMM YYYY" />
            </Form.Item>
            <Form.Item name="farmhouse_id" label="Estate">
              <Select
                allowClear
                placeholder="All estates"
                options={farmhouses.map((f) => ({ value: f.id, label: f.name }))}
              />
            </Form.Item>
          </div>
          <Form.Item name="reason" label="Reason">
            <Input placeholder="e.g. Maintenance, public holiday" />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={saving} icon={<PlusOutlined />}>
            Add blackout
          </Button>
        </Form>
      </Card>

      <div className="eyebrow" style={{ marginBottom: 10 }}>Scheduled blackouts</div>
      {blackouts === null ? (
        <Card><Skeleton active paragraph={{ rows: 2 }} /></Card>
      ) : blackouts.length === 0 ? (
        <EmptyNote icon={<StopOutlined />} title="No blackouts" hint="Add a date range above to block bookings." />
      ) : (
        <Stagger>
          {blackouts.map((b) => (
            <StaggerItem key={b.id}>
              <Card styles={{ body: { padding: 14 } }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
                  <div>
                    <div style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: 16 }}>
                      {fmtDate(b.start_date)} – {fmtDate(b.end_date)}
                    </div>
                    <div className="muted" style={{ fontSize: 13, marginTop: 3 }}>
                      {fhName(b.farmhouse_id)}{b.reason ? ` · ${b.reason}` : ""}
                    </div>
                  </div>
                  <Popconfirm title="Remove this blackout?" onConfirm={() => remove(b.id)}>
                    <Button danger type="text" icon={<DeleteOutlined />} loading={busyId === b.id} />
                  </Popconfirm>
                </div>
              </Card>
            </StaggerItem>
          ))}
        </Stagger>
      )}
    </div>
  );
}
