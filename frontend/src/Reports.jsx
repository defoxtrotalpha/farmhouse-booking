import { useCallback, useEffect, useState } from "react";
import {
  App as AntApp,
  Button,
  Card,
  DatePicker,
  Dropdown,
  Progress,
  Segmented,
  Skeleton,
  Statistic,
  Table,
} from "antd";
import { DownloadOutlined, ReloadOutlined } from "@ant-design/icons";
import dayjs from "dayjs";

import {
  getReportSummary,
  getOccupancy,
  getBookiePerformance,
  getReportFinances,
  downloadReportExport,
} from "./api.js";
import { PageHeader } from "./ui.jsx";
import { statusOf } from "./theme.js";

const { RangePicker } = DatePicker;

const STAT_ORDER = ["booked", "pending", "hold", "rejected", "canceled"];

const PKR = new Intl.NumberFormat("en-PK", { style: "currency", currency: "PKR", maximumFractionDigits: 0 });
const fmtPKR = (n) => PKR.format(Number(n) || 0);

export default function ReportsPage() {
  const { message } = AntApp.useApp();
  const [range, setRange] = useState([dayjs().subtract(90, "day"), dayjs()]);
  const [summary, setSummary] = useState(null);
  const [occupancy, setOccupancy] = useState([]);
  const [performance, setPerformance] = useState([]);
  const [finances, setFinances] = useState(null);
  const [finGranularity, setFinGranularity] = useState("month");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    const params = { start: range[0].toISOString(), end: range[1].toISOString() };
    try {
      const [s, o, p, f] = await Promise.all([
        getReportSummary(params),
        getOccupancy(params),
        getBookiePerformance(params),
        getReportFinances({ ...params, granularity: finGranularity }),
      ]);
      setSummary(s);
      setOccupancy(o);
      setPerformance(p);
      setFinances(f);
    } catch (e) {
      message.error(e.message);
    } finally {
      setLoading(false);
    }
  }, [range, finGranularity, message]);

  useEffect(() => {
    load();
  }, [load]);

  async function exp(report, format) {
    try {
      await downloadReportExport({
        report,
        format,
        start: range[0].toISOString(),
        end: range[1].toISOString(),
      });
    } catch (e) {
      message.error(e.message);
    }
  }

  const exportMenu = (report) => ({
    items: [
      { key: "xlsx", label: "Excel (.xlsx)" },
      { key: "pdf", label: "PDF (.pdf)" },
    ],
    onClick: ({ key }) => exp(report, key),
  });

  return (
    <div>
      <PageHeader
        eyebrow="Admin"
        title="Reports"
        subtitle="Occupancy, throughput, and bookie performance across any window."
        extra={
          <>
            <RangePicker
              value={range}
              onChange={(v) => v && setRange(v)}
              allowClear={false}
              format="DD MMM YYYY"
              placement="bottomLeft"
              getPopupContainer={(t) => t.parentElement}
            />
            <Button icon={<ReloadOutlined />} onClick={load} />
          </>
        }
      />

      {/* Summary tiles */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))", gap: 12, marginBottom: 18 }}>
        {loading || !summary ? (
          <Card><Skeleton active paragraph={false} /></Card>
        ) : (
          STAT_ORDER.map((st) => {
            const meta = statusOf(st);
            return (
              <Card key={st} styles={{ body: { padding: 16 } }}>
                <Statistic
                  title={<span style={{ color: meta.color, fontWeight: 600 }}>{meta.label}</span>}
                  value={summary.counts?.[st] ?? 0}
                  styles={{ content: { fontFamily: "var(--font-display)", color: "var(--ink)" } }}
                />
              </Card>
            );
          })
        )}
      </div>

      {/* Finances */}
      <Card
        style={{ marginBottom: 18 }}
        title="Finances"
        extra={
          <Segmented
            value={finGranularity}
            onChange={setFinGranularity}
            options={[
              { label: "Weekly", value: "week" },
              { label: "Monthly", value: "month" },
              { label: "Yearly", value: "year" },
            ]}
            size="small"
          />
        }
      >
        {loading || !finances ? (
          <Skeleton active />
        ) : (
          <>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 12, marginBottom: 18 }}>
              <Statistic
                title={<span style={{ color: "var(--brass)", fontWeight: 600 }}>Total revenue</span>}
                value={fmtPKR(finances.totals?.total_revenue)}
                styles={{ content: { fontFamily: "var(--font-display)", color: "var(--ink)" } }}
              />
              <Statistic
                title="Confirmed bookings"
                value={finances.totals?.booked_count ?? 0}
                styles={{ content: { fontFamily: "var(--font-display)", color: "var(--ink)" } }}
              />
              <Statistic
                title="Priced bookings"
                value={finances.totals?.priced_count ?? 0}
                styles={{ content: { fontFamily: "var(--font-display)", color: "var(--ink)" } }}
              />
              <Statistic
                title="Average value"
                value={fmtPKR(finances.totals?.average_value)}
                styles={{ content: { fontFamily: "var(--font-display)", color: "var(--ink)" } }}
              />
            </div>

            <div className="eyebrow" style={{ marginBottom: 8 }}>Revenue by estate</div>
            <Table
              rowKey="farmhouse_id"
              dataSource={finances.per_farmhouse ?? []}
              pagination={false}
              size="middle"
              scroll={{ x: true }}
              style={{ marginBottom: 18 }}
              locale={{ emptyText: "No confirmed revenue in this window" }}
              columns={[
                { title: "Estate", dataIndex: "farmhouse_name" },
                { title: "Confirmed", dataIndex: "booked_count", align: "right" },
                {
                  title: "Revenue",
                  dataIndex: "revenue",
                  align: "right",
                  render: (v) => fmtPKR(v),
                  sorter: (a, b) => a.revenue - b.revenue,
                  defaultSortOrder: "descend",
                },
              ]}
            />

            <div className="eyebrow" style={{ marginBottom: 8 }}>
              Revenue by {finGranularity === "week" ? "week" : finGranularity === "year" ? "year" : "month"}
            </div>
            <Table
              rowKey="period"
              dataSource={finances.breakdown ?? []}
              pagination={false}
              size="middle"
              scroll={{ x: true }}
              locale={{ emptyText: "No periods in this window" }}
              columns={[
                { title: "Period", dataIndex: "period" },
                { title: "Confirmed", dataIndex: "booked_count", align: "right" },
                { title: "Revenue", dataIndex: "revenue", align: "right", render: (v) => fmtPKR(v) },
              ]}
            />
          </>
        )}
      </Card>

      {/* Occupancy */}
      <Card
        style={{ marginBottom: 18 }}
        title="Occupancy by estate"
        extra={
          <Dropdown menu={exportMenu("occupancy")}>
            <Button size="small" icon={<DownloadOutlined />}>Export</Button>
          </Dropdown>
        }
      >
        {loading ? (
          <Skeleton active />
        ) : (
          <Table
            rowKey="farmhouse_id"
            dataSource={occupancy}
            pagination={false}
            size="middle"
            scroll={{ x: true }}
            columns={[
              { title: "Estate", dataIndex: "farmhouse_name" },
              {
                title: "Occupancy",
                dataIndex: "occupancy_percent",
                render: (v) => (
                  <div style={{ minWidth: 160 }}>
                    <Progress
                      percent={v}
                      size="small"
                      strokeColor="var(--brass)"
                      format={(p) => `${p}%`}
                    />
                  </div>
                ),
                sorter: (a, b) => a.occupancy_percent - b.occupancy_percent,
                defaultSortOrder: "descend",
              },
            ]}
          />
        )}
      </Card>

      {/* Bookie performance */}
      <Card
        title="Bookie performance"
        extra={
          <Dropdown menu={exportMenu("bookie-performance")}>
            <Button size="small" icon={<DownloadOutlined />}>Export</Button>
          </Dropdown>
        }
      >
        {loading ? (
          <Skeleton active />
        ) : (
          <Table
            rowKey="bookie_id"
            dataSource={performance}
            pagination={false}
            size="middle"
            scroll={{ x: true }}
            columns={[
              { title: "Bookie", dataIndex: "bookie_name" },
              { title: "Submitted", dataIndex: "submitted", align: "right" },
              { title: "Approved", dataIndex: "approved", align: "right", sorter: (a, b) => a.approved - b.approved, defaultSortOrder: "descend" },
              { title: "Rejected", dataIndex: "rejected", align: "right" },
              { title: "Canceled", dataIndex: "canceled", align: "right" },
            ]}
          />
        )}
      </Card>

      <div style={{ marginTop: 18, display: "flex", gap: 10, flexWrap: "wrap" }}>
        <Dropdown menu={exportMenu("bookings")}>
          <Button icon={<DownloadOutlined />}>Export all bookings</Button>
        </Dropdown>
      </div>
    </div>
  );
}
