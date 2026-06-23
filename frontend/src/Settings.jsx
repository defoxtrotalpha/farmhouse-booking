import { useEffect, useState } from "react";
import {
  App as AntApp,
  Button,
  Card,
  Form,
  InputNumber,
  Skeleton,
  TimePicker,
} from "antd";
import { SaveOutlined } from "@ant-design/icons";
import dayjs from "dayjs";

import { getSettings, updateSettings } from "./api.js";
import { PageHeader } from "./ui.jsx";

const TFMT = "HH:mm";

export default function SettingsPage() {
  const { message } = AntApp.useApp();
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    getSettings()
      .then((s) => {
        form.setFieldsValue({
          hold_duration_hours: s.hold_duration_hours,
          min_advance_notice_minutes: s.min_advance_notice_minutes,
          default_buffer_minutes: s.default_buffer_minutes,
          operating_hours_start: s.operating_hours_start ? dayjs(s.operating_hours_start, TFMT) : null,
          operating_hours_end: s.operating_hours_end ? dayjs(s.operating_hours_end, TFMT) : null,
        });
      })
      .catch((e) => message.error(e.message))
      .finally(() => setLoading(false));
  }, [form, message]);

  async function save(v) {
    setSaving(true);
    try {
      await updateSettings({
        hold_duration_hours: v.hold_duration_hours,
        min_advance_notice_minutes: v.min_advance_notice_minutes,
        default_buffer_minutes: v.default_buffer_minutes,
        operating_hours_start: v.operating_hours_start ? v.operating_hours_start.format(TFMT) : null,
        operating_hours_end: v.operating_hours_end ? v.operating_hours_end.format(TFMT) : null,
      });
      message.success("Settings saved.");
    } catch (e) {
      message.error(e.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div>
      <PageHeader
        eyebrow="Admin"
        title="Settings"
        subtitle="System-wide rules that govern holds, advance notice, buffers, and operating hours."
      />
      <Card style={{ maxWidth: 620 }}>
        <Form form={form} layout="vertical" onFinish={save} requiredMark={false}>
          {loading ? (
            <Skeleton active paragraph={{ rows: 5 }} />
          ) : (
            <>
            <Form.Item
              name="hold_duration_hours"
              label="Hold duration (hours)"
              tooltip="How long a soft hold lasts before it expires automatically."
              rules={[{ required: true }]}
            >
              <InputNumber min={1} max={168} style={{ width: "100%" }} />
            </Form.Item>
            <Form.Item
              name="min_advance_notice_minutes"
              label="Minimum advance notice (minutes)"
              tooltip="Bookings must start at least this far in the future."
              rules={[{ required: true }]}
            >
              <InputNumber min={0} step={15} style={{ width: "100%" }} />
            </Form.Item>
            <Form.Item
              name="default_buffer_minutes"
              label="Default turnover buffer (minutes)"
              tooltip="Applied to farmhouses without their own buffer."
              rules={[{ required: true }]}
            >
              <InputNumber min={0} step={15} style={{ width: "100%" }} />
            </Form.Item>
            <div className="two-col">
              <Form.Item name="operating_hours_start" label="Operating hours — start">
                <TimePicker format={TFMT} minuteStep={15} style={{ width: "100%" }} />
              </Form.Item>
              <Form.Item name="operating_hours_end" label="Operating hours — end">
                <TimePicker format={TFMT} minuteStep={15} style={{ width: "100%" }} />
              </Form.Item>
            </div>
            <Button type="primary" htmlType="submit" loading={saving} icon={<SaveOutlined />}>
              Save settings
            </Button>
            </>
          )}
        </Form>
      </Card>
    </div>
  );
}
