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
  CheckOutlined,
  CloseOutlined,
  DeleteOutlined,
  PlusOutlined,
  ShopOutlined,
  ReloadOutlined,
} from "@ant-design/icons";

import {
  listCompanies,
  createCompany,
  approveCompany,
  rejectCompany,
  deleteCompany,
} from "./api.js";
import { PageHeader, Stagger, StaggerItem, EmptyNote } from "./ui.jsx";
import { fmtDate } from "./theme.js";

const STATUS_META = {
  pending: { color: "gold", label: "Pending" },
  approved: { color: "green", label: "Approved" },
  rejected: { color: "red", label: "Rejected" },
};

function CompanyLogo({ name }) {
  const initials = (name || "?")
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase())
    .join("");
  return (
    <span style={{
      width: 46, height: 46, borderRadius: 13, flexShrink: 0,
      display: "grid", placeItems: "center",
      background: "var(--pine)", color: "var(--linen)",
      fontFamily: "var(--font-display)", fontWeight: 600, fontSize: 16,
    }}>
      {initials || <ShopOutlined />}
    </span>
  );
}

export default function CompaniesPage() {
  const { message } = AntApp.useApp();
  const [companies, setCompanies] = useState(null);
  const [busyId, setBusyId] = useState(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [form] = Form.useForm();

  async function load() {
    try {
      setCompanies(await listCompanies());
    } catch (e) {
      message.error(e.message ?? "Failed to load companies");
      setCompanies([]);
    }
  }

  useEffect(() => {
    load();
  }, []); // eslint-disable-line

  async function onApprove(c) {
    setBusyId(c.id);
    try {
      await approveCompany(c.id);
      message.success(`${c.name} approved.`);
      load();
    } catch (e) {
      message.error(e.message ?? "Could not approve company");
    } finally {
      setBusyId(null);
    }
  }

  async function onReject(c) {
    setBusyId(c.id);
    try {
      await rejectCompany(c.id);
      message.success(`${c.name} rejected.`);
      load();
    } catch (e) {
      message.error(e.message ?? "Could not reject company");
    } finally {
      setBusyId(null);
    }
  }

  async function onDelete(c) {
    setBusyId(c.id);
    try {
      await deleteCompany(c.id);
      message.success(`${c.name} and all its data were removed.`);
      load();
    } catch (e) {
      message.error(e.message ?? "Could not delete company");
    } finally {
      setBusyId(null);
    }
  }

  async function onCreate(values) {
    setCreating(true);
    try {
      await createCompany({
        company_name: values.company_name.trim(),
        admin_name: values.admin_name.trim(),
        admin_email: values.admin_email.trim(),
        admin_password: values.admin_password,
      });
      message.success("Company created.");
      form.resetFields();
      setCreateOpen(false);
      load();
    } catch (e) {
      message.error(e.message ?? "Could not create company");
    } finally {
      setCreating(false);
    }
  }

  const pendingCount = (companies ?? []).filter((c) => c.status === "pending").length;

  return (
    <>
      <PageHeader
        eyebrow="Platform"
        title="Companies"
        subtitle="Approve new company requests and manage every organization on the platform."
        extra={[
          <Button key="refresh" icon={<ReloadOutlined />} onClick={load}>
            Refresh
          </Button>,
          <Button key="create" type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
            New company
          </Button>,
        ]}
      />

      {pendingCount > 0 && (
        <div style={{ marginBottom: 14 }}>
          <Tag color="gold" style={{ fontSize: 13, padding: "3px 10px" }}>
            {pendingCount} awaiting approval
          </Tag>
        </div>
      )}

      {companies === null ? (
        <Card><Skeleton active paragraph={{ rows: 4 }} /></Card>
      ) : companies.length === 0 ? (
        <EmptyNote
          icon={<ShopOutlined />}
          title="No companies yet"
          hint="Create the first company or wait for a signup request."
        />
      ) : (
        <Stagger gap={12}>
          {companies.map((c) => {
            const meta = STATUS_META[c.status] ?? { color: "default", label: c.status };
            return (
              <StaggerItem key={c.id}>
                <Card styles={{ body: { padding: 16 } }}>
                  <div style={{ display: "flex", gap: 14, alignItems: "flex-start", flexWrap: "wrap" }}>
                    <CompanyLogo name={c.name} />
                    <div style={{ flex: 1, minWidth: 200 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                        <span style={{ fontFamily: "var(--font-display)", fontSize: 18, fontWeight: 600 }}>
                          {c.name}
                        </span>
                        <Tag color={meta.color}>{meta.label}</Tag>
                      </div>
                      <div className="muted" style={{ fontSize: 13, marginTop: 4 }}>
                        {c.admin_email
                          ? <>Admin: {c.admin_name ? `${c.admin_name} · ` : ""}{c.admin_email}</>
                          : "No admin assigned"}
                      </div>
                      <div className="muted" style={{ fontSize: 12.5, marginTop: 3 }}>
                        {c.member_count} member{c.member_count === 1 ? "" : "s"} ·{" "}
                        {c.farmhouse_count} estate{c.farmhouse_count === 1 ? "" : "s"} ·{" "}
                        Created {fmtDate(c.created_at)}
                      </div>
                    </div>
                    <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
                      {c.status === "pending" && (
                        <>
                          <Button
                            type="primary"
                            icon={<CheckOutlined />}
                            loading={busyId === c.id}
                            onClick={() => onApprove(c)}
                          >
                            Approve
                          </Button>
                          <Button
                            icon={<CloseOutlined />}
                            loading={busyId === c.id}
                            onClick={() => onReject(c)}
                          >
                            Reject
                          </Button>
                        </>
                      )}
                      {c.status === "rejected" && (
                        <Button
                          type="primary"
                          icon={<CheckOutlined />}
                          loading={busyId === c.id}
                          onClick={() => onApprove(c)}
                        >
                          Approve
                        </Button>
                      )}
                      <Popconfirm
                        title="Delete this company?"
                        description="This permanently removes the company and all of its bookings, estates and users."
                        okText="Delete"
                        okButtonProps={{ danger: true }}
                        onConfirm={() => onDelete(c)}
                      >
                        <Tooltip title="Delete company">
                          <Button danger icon={<DeleteOutlined />} loading={busyId === c.id} />
                        </Tooltip>
                      </Popconfirm>
                    </div>
                  </div>
                </Card>
              </StaggerItem>
            );
          })}
        </Stagger>
      )}

      <Modal
        title="Create a company"
        open={createOpen}
        onCancel={() => { form.resetFields(); setCreateOpen(false); }}
        onOk={() => form.submit()}
        okText="Create company"
        confirmLoading={creating}
        destroyOnHidden
      >
        <p className="muted" style={{ marginTop: 0 }}>
          The company is created already approved. Share the email and temporary
          password with its admin so they can sign in and change it.
        </p>
        <Form form={form} layout="vertical" onFinish={onCreate} requiredMark={false}>
          <Form.Item
            name="company_name"
            label="Company name"
            rules={[{ required: true, message: "Enter a company name" }]}
          >
            <Input placeholder="Green Acres Pvt Ltd" />
          </Form.Item>
          <Form.Item
            name="admin_name"
            label="Admin name"
            rules={[{ required: true, message: "Enter the admin's name" }]}
          >
            <Input placeholder="Jane Doe" />
          </Form.Item>
          <Form.Item
            name="admin_email"
            label="Admin email"
            rules={[
              { required: true, message: "Enter the admin's email" },
              { type: "email", message: "Enter a valid email" },
            ]}
          >
            <Input placeholder="jane@company.com" />
          </Form.Item>
          <Form.Item
            name="admin_password"
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
