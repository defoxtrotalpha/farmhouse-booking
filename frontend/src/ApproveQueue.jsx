import { useEffect, useMemo, useState } from "react";
import {
  App as AntApp,
  Button,
  Card,
  Checkbox,
  Input,
  Modal,
  Popconfirm,
  Skeleton,
  Tabs,
} from "antd";
import { CheckOutlined, CloseOutlined, ReloadOutlined } from "@ant-design/icons";

import {
  listBookings,
  approveBooking,
  getConflicts,
  rejectBatch,
  rejectBooking,
  cancelBooking,
  confirmCancel,
} from "./api.js";
import {
  PageHeader,
  Stagger,
  StaggerItem,
  LedgerCard,
  EmptyNote,
} from "./ui.jsx";
import { bookingNo, fmtDateTime, fmtTime, fmtDate } from "./theme.js";

export default function ApproveQueue() {
  const { message } = AntApp.useApp();
  const [pending, setPending] = useState(null);
  const [cancelReqs, setCancelReqs] = useState([]);
  const [busyId, setBusyId] = useState(null);

  // conflict resolution modal
  const [conflictModal, setConflictModal] = useState(null); // { bookedId, losers, selected, reason }
  // 409 reject offer
  const [rejectOffer, setRejectOffer] = useState(null); // { pendingId, conflictId, reason }
  // manual reject
  const [rejectModal, setRejectModal] = useState(null); // { booking, reason }

  async function load() {
    try {
      const [p, booked] = await Promise.all([
        listBookings({ status: "pending" }),
        listBookings({ status: "booked" }),
      ]);
      setPending(p);
      setCancelReqs(booked.filter((b) => b.cancel_requested_at != null));
    } catch (e) {
      message.error(e.message);
      setPending([]);
    }
  }

  useEffect(() => {
    load();
  }, []); // eslint-disable-line

  async function handleApprove(b) {
    setBusyId(b.id);
    try {
      const approved = await approveBooking(b.id);
      message.success(`${bookingNo(b.id)} confirmed.`);
      // find overlapping losers to optionally reject
      const losers = await getConflicts(approved.id).catch(() => []);
      if (losers.length) {
        setConflictModal({ bookedId: approved.id, losers, selected: losers.map((l) => l.id), reason: "" });
      }
      load();
    } catch (e) {
      if (e.status === 409 && e.conflict_booking_id) {
        setRejectOffer({ pendingId: b.id, conflictId: e.conflict_booking_id, reason: "" });
      } else {
        message.error(e.message ?? "Approval failed");
      }
    } finally {
      setBusyId(null);
    }
  }

  async function doRejectBatch() {
    const { selected, reason } = conflictModal;
    if (!reason.trim()) return message.warning("Add a rejection reason.");
    if (!selected.length) return message.warning("Select at least one request.");
    try {
      const res = await rejectBatch(selected, reason);
      message.success(`Rejected ${res.rejected.length} request(s).`);
      setConflictModal(null);
      load();
    } catch (e) {
      message.error(e.message);
    }
  }

  async function doRejectOffer() {
    const { pendingId, reason } = rejectOffer;
    if (!reason.trim()) return message.warning("Add a rejection reason.");
    try {
      await rejectBooking(pendingId, reason);
      message.success(`${bookingNo(pendingId)} rejected.`);
      setRejectOffer(null);
      load();
    } catch (e) {
      message.error(e.message);
    }
  }

  async function doReject() {
    const { booking, reason } = rejectModal;
    if (!reason.trim()) return message.warning("Add a rejection reason.");
    try {
      await rejectBooking(booking.id, reason);
      message.success(`${bookingNo(booking.id)} rejected.`);
      setRejectModal(null);
      load();
    } catch (e) {
      message.error(e.message);
    }
  }

  async function handleConfirmCancel(b) {
    setBusyId(b.id);
    try {
      await confirmCancel(b.id);
      message.success("Cancellation confirmed.");
      load();
    } catch (e) {
      message.error(e.message);
    } finally {
      setBusyId(null);
    }
  }

  const pendingTab = (
    <>
      {pending === null ? (
        <Card><Skeleton active /></Card>
      ) : pending.length === 0 ? (
        <EmptyNote icon={<CheckOutlined />} title="Inbox zero" hint="No requests are waiting for approval." />
      ) : (
        <Stagger>
          {pending.map((b) => (
            <StaggerItem key={b.id}>
              <LedgerCard
                booking={b}
                footer={
                  <div style={{ display: "flex", gap: 8 }}>
                    <Popconfirm
                      title="Approve & confirm this booking?"
                      okText="Approve"
                      onConfirm={() => handleApprove(b)}
                    >
                      <Button type="primary" icon={<CheckOutlined />} loading={busyId === b.id}>
                        Approve
                      </Button>
                    </Popconfirm>
                    <Button icon={<CloseOutlined />} onClick={() => setRejectModal({ booking: b, reason: "" })}>
                      Reject
                    </Button>
                  </div>
                }
              />
            </StaggerItem>
          ))}
        </Stagger>
      )}
    </>
  );

  const cancelTab = (
    <>
      {cancelReqs.length === 0 ? (
        <EmptyNote title="No cancellation requests" hint="Booked events with a pending cancellation appear here." />
      ) : (
        <Stagger>
          {cancelReqs.map((b) => (
            <StaggerItem key={b.id}>
              <LedgerCard
                booking={b}
                footer={
                  <div>
                    {b.cancel_reason && <p className="muted" style={{ fontSize: 13, margin: "0 0 8px" }}>“{b.cancel_reason}”</p>}
                    <Popconfirm title="Confirm cancellation?" description="This frees the slot." okButtonProps={{ danger: true }} onConfirm={() => handleConfirmCancel(b)}>
                      <Button danger loading={busyId === b.id}>Confirm cancellation</Button>
                    </Popconfirm>
                  </div>
                }
              />
            </StaggerItem>
          ))}
        </Stagger>
      )}
    </>
  );

  const pendingCount = pending?.length ?? 0;

  return (
    <div>
      <PageHeader
        eyebrow="Admin"
        title="Approvals"
        subtitle="Approve exactly one request per slot. Overlapping requests are flagged so you can clear them in one step."
        extra={<Button icon={<ReloadOutlined />} onClick={load}>Refresh</Button>}
      />

      <Tabs
        items={[
          { key: "pending", label: `Requests${pendingCount ? ` (${pendingCount})` : ""}`, children: pendingTab },
          { key: "cancel", label: `Cancellations${cancelReqs.length ? ` (${cancelReqs.length})` : ""}`, children: cancelTab },
        ]}
      />

      {/* Conflict resolution after approval */}
      <Modal
        open={!!conflictModal}
        title="Clear overlapping requests"
        okText="Reject selected"
        okButtonProps={{ danger: true }}
        onOk={doRejectBatch}
        onCancel={() => setConflictModal(null)}
      >
        {conflictModal && (
          <>
            <p className="muted" style={{ marginTop: 0 }}>
              These holds and requests overlap the booking you just confirmed. Reject the ones that can no longer happen.
            </p>
            <div className="stack" style={{ marginBottom: 12 }}>
              {conflictModal.losers.map((l) => (
                <label key={l.id} style={{ display: "flex", gap: 10, alignItems: "center", border: "1px solid var(--hairline)", borderRadius: 10, padding: "8px 10px" }}>
                  <Checkbox
                    checked={conflictModal.selected.includes(l.id)}
                    onChange={(e) =>
                      setConflictModal((m) => ({
                        ...m,
                        selected: e.target.checked ? [...m.selected, l.id] : m.selected.filter((x) => x !== l.id),
                      }))
                    }
                  />
                  <span className="mono">{bookingNo(l.id)}</span>
                  <span className="muted" style={{ fontSize: 13 }}>
                    {fmtDate(l.start_at)} · {fmtTime(l.start_at)}–{fmtTime(l.end_at)}
                  </span>
                </label>
              ))}
            </div>
            <Input.TextArea
              rows={2}
              placeholder="Rejection reason (sent to the affected bookies)"
              value={conflictModal.reason}
              onChange={(e) => setConflictModal((m) => ({ ...m, reason: e.target.value }))}
            />
          </>
        )}
      </Modal>

      {/* 409 conflict on approve */}
      <Modal
        open={!!rejectOffer}
        title="Slot already confirmed"
        okText="Reject this request"
        okButtonProps={{ danger: true }}
        onOk={doRejectOffer}
        onCancel={() => setRejectOffer(null)}
      >
        {rejectOffer && (
          <>
            <p className="muted" style={{ marginTop: 0 }}>
              This slot was just confirmed as {bookingNo(rejectOffer.conflictId)}. Reject the request you tried to approve?
            </p>
            <Input.TextArea rows={2} placeholder="Rejection reason" value={rejectOffer.reason} onChange={(e) => setRejectOffer((m) => ({ ...m, reason: e.target.value }))} />
          </>
        )}
      </Modal>

      {/* Manual reject */}
      <Modal
        open={!!rejectModal}
        title={rejectModal ? `Reject ${bookingNo(rejectModal.booking.id)}` : ""}
        okText="Reject"
        okButtonProps={{ danger: true }}
        onOk={doReject}
        onCancel={() => setRejectModal(null)}
      >
        {rejectModal && (
          <>
            <p className="muted" style={{ marginTop: 0 }}>{rejectModal.booking.client_name} · {fmtDateTime(rejectModal.booking.start_at)}</p>
            <Input.TextArea rows={2} placeholder="Rejection reason" value={rejectModal.reason} onChange={(e) => setRejectModal((m) => ({ ...m, reason: e.target.value }))} />
          </>
        )}
      </Modal>
    </div>
  );
}
