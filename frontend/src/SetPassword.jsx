import { useState } from "react";
import { App as AntApp, Button, Form, Input, Result } from "antd";
import { motion } from "framer-motion";
import { LockOutlined, ArrowRightOutlined } from "@ant-design/icons";
import { setPassword } from "./api.js";
import { Brand } from "./ui.jsx";

function getToken() {
  return new URLSearchParams(window.location.search).get("token") || "";
}

export default function SetPasswordPage() {
  const { message } = AntApp.useApp();
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);
  const token = getToken();

  async function onFinish(values) {
    setLoading(true);
    try {
      await setPassword(token, values.password);
      setDone(true);
    } catch (err) {
      message.error(err.message ?? "Could not set your password");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="auth-stage">
      <motion.aside className="auth-aside" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.5 }}>
        <Brand />
        <div>
          <div className="eyebrow" style={{ color: "var(--brass-soft)" }}>Activate your account</div>
          <div className="auth-hero-title">You're on the guest list.</div>
          <p className="auth-hero-sub">Choose a password to finish setting up your bookie account and start placing holds.</p>
        </div>
        <span />
      </motion.aside>

      <div className="auth-panel">
        <motion.div className="auth-card" initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }}>
          {done ? (
            <Result
              status="success"
              title="Password set"
              subTitle="Your account is active. You can sign in now."
              extra={
                <Button type="primary" onClick={() => (window.location.href = "/")} icon={<ArrowRightOutlined />} iconPlacement="end">
                  Go to sign in
                </Button>
              }
            />
          ) : !token ? (
            <Result status="warning" title="Missing invite link" subTitle="This page needs a valid invite token. Please use the link from your invitation email." />
          ) : (
            <>
              <h1 style={{ fontSize: 28, margin: "0 0 4px", textAlign: "center" }}>Set your password</h1>
              <p className="muted" style={{ textAlign: "center", margin: "0 0 22px" }}>At least 8 characters.</p>
              <Form layout="vertical" onFinish={onFinish} requiredMark={false} size="large">
                <Form.Item
                  name="password"
                  label="New password"
                  rules={[{ required: true, message: "Choose a password" }, { min: 8, message: "Use at least 8 characters" }]}
                >
                  <Input.Password prefix={<LockOutlined style={{ color: "var(--muted)" }} />} placeholder="••••••••" autoFocus />
                </Form.Item>
                <Form.Item
                  name="confirm"
                  label="Confirm password"
                  dependencies={["password"]}
                  rules={[
                    { required: true, message: "Confirm your password" },
                    ({ getFieldValue }) => ({
                      validator: (_, v) =>
                        !v || getFieldValue("password") === v ? Promise.resolve() : Promise.reject(new Error("Passwords do not match")),
                    }),
                  ]}
                >
                  <Input.Password prefix={<LockOutlined style={{ color: "var(--muted)" }} />} placeholder="••••••••" />
                </Form.Item>
                <Button type="primary" htmlType="submit" block size="large" loading={loading} icon={<ArrowRightOutlined />} iconPlacement="end">
                  Activate account
                </Button>
              </Form>
            </>
          )}
        </motion.div>
      </div>
    </div>
  );
}
