import { useState } from "react";
import {
  App as AntApp,
  Button,
  Card,
  Form,
  Input,
  Modal,
  Segmented,
  Tabs,
  Typography,
} from "antd";
import {
  MailOutlined,
  UserAddOutlined,
  LockOutlined,
  UserOutlined,
} from "@ant-design/icons";

import { inviteBookie, createUserDirect } from "./api.js";
import { PageHeader } from "./ui.jsx";

export default function BookiesPage() {
  const { message } = AntApp.useApp();
  const [inviteForm] = Form.useForm();
  const [directForm] = Form.useForm();
  const [inviting, setInviting] = useState(false);
  const [adding, setAdding] = useState(false);
  const [inviteLink, setInviteLink] = useState(null); // set_password_url to show in modal

  async function onInvite(values) {
    setInviting(true);
    try {
      const res = await inviteBookie(
        values.name.trim(),
        values.email.trim(),
        values.role || "bookie",
      );
      message.success(`Invite created for ${values.email}.`);
      inviteForm.resetFields();
      if (res?.set_password_url) setInviteLink(res.set_password_url);
    } catch (e) {
      message.error(e.message ?? "Could not send invite");
    } finally {
      setInviting(false);
    }
  }

  async function onDirectAdd(values) {
    setAdding(true);
    try {
      await createUserDirect({
        name: values.name.trim(),
        username: values.username.trim(),
        password: values.password,
        role: values.role || "bookie",
      });
      message.success(`${values.name} added — they can sign in now.`);
      directForm.resetFields();
    } catch (e) {
      message.error(e.message ?? "Could not add user");
    } finally {
      setAdding(false);
    }
  }

  return (
    <div>
      <PageHeader
        eyebrow="Admin"
        title="Add bookies & admins"
        subtitle="Invite people by email, or add them directly with a username and password. Manage the full roster from the Users tab."
      />

      <Card>
        <Tabs
          items={[
            {
              key: "invite",
              label: <span><MailOutlined /> &nbsp;Invite by email</span>,
              children: (
                <Form
                  form={inviteForm}
                  layout="vertical"
                  onFinish={onInvite}
                  requiredMark={false}
                  initialValues={{ role: "bookie" }}
                >
                  <div className="two-col">
                    <Form.Item name="name" label="Name" rules={[{ required: true, message: "Enter a name" }]}>
                      <Input placeholder="e.g. Bilal Ahmed" />
                    </Form.Item>
                    <Form.Item name="email" label="Email" rules={[{ required: true, type: "email", message: "Enter a valid email" }]}>
                      <Input placeholder="name@example.com" prefix={<MailOutlined style={{ color: "var(--muted)" }} />} />
                    </Form.Item>
                  </div>
                  <Form.Item name="role" label="Role">
                    <Segmented
                      options={[
                        { label: "Bookie", value: "bookie" },
                        { label: "Admin", value: "admin" },
                      ]}
                    />
                  </Form.Item>
                  <Button type="primary" htmlType="submit" loading={inviting} icon={<UserAddOutlined />}>
                    Create invite link
                  </Button>
                  <div className="muted" style={{ fontSize: 12, marginTop: 8 }}>
                    A set-password link will be shown to copy and share directly.
                  </div>
                </Form>
              ),
            },
            {
              key: "direct",
              label: <span><UserOutlined /> &nbsp;Add directly</span>,
              children: (
                <Form
                  form={directForm}
                  layout="vertical"
                  onFinish={onDirectAdd}
                  requiredMark={false}
                  initialValues={{ role: "bookie" }}
                >
                  <div className="two-col">
                    <Form.Item name="name" label="Name" rules={[{ required: true, message: "Enter a name" }]}>
                      <Input placeholder="e.g. Bilal Ahmed" />
                    </Form.Item>
                    <Form.Item
                      name="username"
                      label="Username"
                      tooltip="This is also their login identifier."
                      rules={[{ required: true, message: "Choose a username" }]}
                    >
                      <Input placeholder="bilal" prefix={<UserOutlined style={{ color: "var(--muted)" }} />} />
                    </Form.Item>
                  </div>
                  <div className="two-col">
                    <Form.Item
                      name="password"
                      label="Password"
                      rules={[{ required: true, message: "Enter a password" }, { min: 8, message: "At least 8 characters" }]}
                    >
                      <Input.Password placeholder="••••••••" prefix={<LockOutlined style={{ color: "var(--muted)" }} />} />
                    </Form.Item>
                    <Form.Item name="role" label="Role">
                      <Segmented
                        options={[
                          { label: "Bookie", value: "bookie" },
                          { label: "Admin", value: "admin" },
                        ]}
                      />
                    </Form.Item>
                  </div>
                  <Button type="primary" htmlType="submit" loading={adding} icon={<UserAddOutlined />}>
                    Add user
                  </Button>
                </Form>
              ),
            },
          ]}
        />
      </Card>

      <Modal
        open={!!inviteLink}
        onCancel={() => setInviteLink(null)}
        onOk={() => setInviteLink(null)}
        okText="Done"
        cancelButtonProps={{ style: { display: "none" } }}
        title="Invite link ready"
      >
        <p className="muted" style={{ marginTop: 0 }}>
          No email is sent automatically. Copy this link and share it with the person —
          they'll use it to set a password and activate their account.
        </p>
        <Typography.Paragraph
          copyable={{ text: inviteLink }}
          style={{ wordBreak: "break-all", background: "var(--panel-2, #f5f1e6)", padding: "10px 12px", borderRadius: 8 }}
        >
          {inviteLink}
        </Typography.Paragraph>
      </Modal>
    </div>
  );
}
