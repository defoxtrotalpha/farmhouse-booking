const BASE = import.meta.env.VITE_API_BASE ?? "";

// ---------------------------------------------------------------------------
// Token storage helpers
// ---------------------------------------------------------------------------

export const tokens = {
  getAccess: () => localStorage.getItem("access_token"),
  getRefresh: () => localStorage.getItem("refresh_token"),
  set: (access, refresh) => {
    localStorage.setItem("access_token", access);
    if (refresh !== undefined) localStorage.setItem("refresh_token", refresh);
  },
  clear: () => {
    localStorage.removeItem("access_token");
    localStorage.removeItem("refresh_token");
  },
};

// ---------------------------------------------------------------------------
// Central fetch wrapper: attaches Bearer token; on 401 attempts one refresh
// ---------------------------------------------------------------------------

let _refreshing = null; // deduplicate concurrent refresh attempts

async function _doRefresh() {
  const rt = tokens.getRefresh();
  if (!rt) return false;
  const res = await fetch(`${BASE}/api/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: rt }),
  });
  if (!res.ok) {
    tokens.clear();
    return false;
  }
  const data = await res.json();
  tokens.set(data.access_token);
  return true;
}

export async function apiFetch(path, options = {}) {
  const headers = { ...(options.headers ?? {}) };
  const at = tokens.getAccess();
  if (at) headers["Authorization"] = `Bearer ${at}`;

  const res = await fetch(`${BASE}${path}`, { ...options, headers });

  if (res.status === 401) {
    // Attempt one transparent token refresh
    if (!_refreshing) _refreshing = _doRefresh().finally(() => { _refreshing = null; });
    const refreshed = await _refreshing;
    if (!refreshed) return res; // caller sees 401

    // Retry the original request with the new token
    const newAt = tokens.getAccess();
    headers["Authorization"] = `Bearer ${newAt}`;
    return fetch(`${BASE}${path}`, { ...options, headers });
  }

  return res;
}

// ---------------------------------------------------------------------------
// Auth endpoints
// ---------------------------------------------------------------------------

export async function login(tenant, identifier, password) {
  const res = await fetch(`${BASE}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tenant: tenant || null, identifier, password }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    const detail = err.detail;
    const msg = Array.isArray(detail)
      ? detail.map((e) => e.msg ?? String(e)).join("; ")
      : (detail ?? "Login failed");
    throw Object.assign(new Error(msg), { status: res.status });
  }
  const data = await res.json();
  tokens.set(data.access_token, data.refresh_token);
  return data;
}

/**
 * Request a new company. The request goes to the platform global admin for
 * approval — no tokens are returned and the user is NOT signed in.
 * Returns the SignupResponse `{ status, message }`.
 */
export async function signupCompany({ company_name, name, password, email }) {
  const res = await fetch(`${BASE}/api/auth/signup`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ company_name, name, email, password }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    const detail = err.detail;
    const msg = Array.isArray(detail)
      ? detail.map((e) => e.msg ?? String(e)).join("; ")
      : (detail ?? "Sign up failed");
    throw Object.assign(new Error(msg), { status: res.status });
  }
  return res.json();
}

/** Change the signed-in user's own password. */
export async function changePassword(current_password, new_password) {
  const res = await apiFetch("/api/auth/change-password", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ current_password, new_password }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw Object.assign(new Error(err.detail ?? "Failed to change password"), { status: res.status });
  }
  return res.json();
}

export async function getMe() {
  const res = await apiFetch("/api/auth/me");
  if (!res.ok) throw new Error("Not authenticated");
  return res.json();
}

// ---------------------------------------------------------------------------
// Health check (kept from walking skeleton)
// ---------------------------------------------------------------------------

export async function getHealth() {
  const res = await fetch(`${BASE}/api/health`);
  if (!res.ok) throw new Error(`Health check failed: ${res.status}`);
  return res.json();
}

// ---------------------------------------------------------------------------
// Farmhouse endpoints
// ---------------------------------------------------------------------------

export async function listFarmhouses({ includeDisabled = false } = {}) {
  const qs = includeDisabled ? "?include_disabled=true" : "";
  const res = await apiFetch(`/api/farmhouses${qs}`);
  if (!res.ok) throw new Error("Failed to load farmhouses");
  return res.json();
}

export async function createFarmhouse(data) {
  const res = await apiFetch("/api/farmhouses", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? "Failed to create farmhouse");
  }
  return res.json();
}

export async function updateFarmhouse(id, data) {
  const res = await apiFetch(`/api/farmhouses/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? "Failed to update farmhouse");
  }
  return res.json();
}

// ---------------------------------------------------------------------------
// Invite endpoints
// ---------------------------------------------------------------------------

export async function inviteBookie(name, email, role = "bookie") {
  const res = await apiFetch("/api/invites", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, email, role }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw Object.assign(new Error(err.detail ?? "Failed to send invite"), { status: res.status });
  }
  return res.json();
}

/** Cancel a pending invite (admin only) — removes the unaccepted user + token. */
export async function cancelInvite(userId) {
  const res = await apiFetch(`/api/invites/${userId}`, { method: "DELETE" });
  if (!res.ok && res.status !== 204) {
    const err = await res.json().catch(() => ({}));
    throw Object.assign(new Error(err.detail ?? "Failed to cancel invite"), { status: res.status });
  }
  return true;
}

// setPassword deliberately does NOT attach an auth token (public endpoint).
export async function setPassword(token, password) {
  const res = await fetch(`${BASE}/api/invites/set-password`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token, password }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw Object.assign(new Error(err.detail ?? "Failed to set password"), { status: res.status });
  }
  return res.json();
}

// ---------------------------------------------------------------------------
// Policy endpoints
// ---------------------------------------------------------------------------

export async function listPolicies() {
  const res = await apiFetch("/api/policies");
  if (!res.ok) throw new Error("Failed to load policies");
  return res.json();
}

export async function createPolicy(data) {
  const res = await apiFetch("/api/policies", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? "Failed to create policy");
  }
  return res.json();
}

export async function updatePolicy(id, data) {
  const res = await apiFetch(`/api/policies/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? "Failed to update policy");
  }
  return res.json();
}

// ---------------------------------------------------------------------------
// Activity Log endpoints
// ---------------------------------------------------------------------------

export async function listActivity({ limit = 50, offset = 0 } = {}) {
  const res = await apiFetch(`/api/activity?limit=${limit}&offset=${offset}`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? "Failed to load activity log");
  }
  return res.json();
}

/** Clear all activity log entries for the current company (admin only). */
export async function clearActivity() {
  const res = await apiFetch("/api/activity", { method: "DELETE" });
  if (!res.ok && res.status !== 204) {
    const err = await res.json().catch(() => ({}));
    throw Object.assign(new Error(err.detail ?? "Failed to clear activity"), { status: res.status });
  }
  return true;
}

// ---------------------------------------------------------------------------
// Availability endpoints
// ---------------------------------------------------------------------------

/**
 * Fetch occupied bookings (hold/pending/booked) for a farmhouse
 * that intersect the half-open window [start, end).
 * @param {number} farmhouseId
 * @param {Date}   start  - window start (will be serialised as ISO8601 UTC)
 * @param {Date}   end    - window end
 * @returns {Promise<Array>} list of {id, status, start_at, end_at, bookie_id}
 */
export async function getAvailability(farmhouseId, start, end) {
  const params = new URLSearchParams({
    start: start.toISOString(),
    end:   end.toISOString(),
  });
  const res = await apiFetch(`/api/farmhouses/${farmhouseId}/availability?${params}`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? "Failed to load availability");
  }
  return res.json();
}

// ---------------------------------------------------------------------------
// Booking endpoints
// ---------------------------------------------------------------------------

/**
 * Approve a pending booking (admin only).
 * Resolves with the updated BookingRead on 200.
 * On 409 conflict, rejects with an error that has:
 *   err.message = the detail string
 *   err.conflict_booking_id = the conflicting booking id
 * @param {number} id
 */
export async function approveBooking(id) {
  const res = await apiFetch(`/api/bookings/${id}/approve`, { method: "POST" });
  if (res.ok) return res.json();
  const body = await res.json().catch(() => ({}));
  const err = Object.assign(
    new Error(body.detail ?? "Failed to approve booking"),
    { status: res.status, conflict_booking_id: body.conflict_booking_id ?? null },
  );
  throw err;
}

// ---------------------------------------------------------------------------
// Booking endpoints (slice #22)
// ---------------------------------------------------------------------------

/**
 * Place a hold on a farmhouse slot.
 * @param {number} farmhouseId
 * @param {Date}   startAt
 * @param {Date}   endAt
 * @returns {Promise<Object>} BookingRead
 */
export async function createHold(farmhouseId, startAt, endAt) {
  const res = await apiFetch("/api/bookings/hold", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      farmhouse_id: farmhouseId,
      start_at: startAt.toISOString(),
      end_at:   endAt.toISOString(),
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw Object.assign(new Error(err.detail ?? "Failed to place hold"), { status: res.status });
  }
  return res.json();
}

/**
 * Submit a hold as a pending booking request with client details.
 * @param {number} bookingId
 * @param {Object} details  { client_name, client_contact, event_type?, event_info?, notes?, quoted_price? }
 * @returns {Promise<Object>} BookingRead
 */
export async function submitBooking(bookingId, details) {
  const res = await apiFetch(`/api/bookings/${bookingId}/submit`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(details),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw Object.assign(new Error(err.detail ?? "Failed to submit booking"), { status: res.status });
  }
  return res.json();
}

/**
 * List bookings (role-filtered: bookie sees own; admin sees all).
 * @param {{ status?: string, farmhouse_id?: number }} filters
 * @returns {Promise<Array>} [BookingRead]
 */
export async function listBookings({ status, farmhouse_id } = {}) {
  const params = new URLSearchParams();
  if (status)       params.set("status", status);
  if (farmhouse_id) params.set("farmhouse_id", String(farmhouse_id));
  const qs = params.toString() ? `?${params}` : "";
  const res = await apiFetch(`/api/bookings${qs}`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? "Failed to load bookings");
  }
  return res.json();
}

// ---------------------------------------------------------------------------
// Conflict resolution helpers (slice #24)
// ---------------------------------------------------------------------------

/**
 * Fetch overlapping hold/pending bookings for the given (typically booked) booking.
 * Admin only. Called after a successful approve to find the "losers".
 * @param {number} bookingId
 * @returns {Promise<Array>} [BookingRead]
 */
export async function getConflicts(bookingId) {
  const res = await apiFetch(`/api/bookings/${bookingId}/conflicts`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw Object.assign(new Error(err.detail ?? "Failed to load conflicts"), { status: res.status });
  }
  return res.json();
}

/**
 * Reject a single hold or pending booking (admin only).
 * @param {number} bookingId
 * @param {string} reason  Required, non-empty.
 * @returns {Promise<Object>} BookingRead with status='rejected'
 */
export async function rejectBooking(bookingId, reason) {
  const res = await apiFetch(`/api/bookings/${bookingId}/reject`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ reason }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw Object.assign(new Error(err.detail ?? "Failed to reject booking"), { status: res.status });
  }
  return res.json();
}

/**
 * Batch-reject multiple hold/pending bookings (admin only).
 * Bookings that are already terminal are skipped (reported in response.skipped).
 * @param {number[]} bookingIds
 * @param {string}   reason
 * @returns {Promise<{rejected: number[], skipped: {id:number, reason_skipped:string}[]}>}
 */
export async function rejectBatch(bookingIds, reason) {
  const res = await apiFetch("/api/bookings/reject-batch", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ booking_ids: bookingIds, reason }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw Object.assign(new Error(err.detail ?? "Failed to batch reject bookings"), { status: res.status });
  }
  return res.json();
}

// ---------------------------------------------------------------------------
// Cancellation helpers (slice #26)
// ---------------------------------------------------------------------------

/**
 * Admin cancels a pending or booked booking.
 * @param {number} bookingId
 * @param {string} reason  Required, non-empty.
 */
export async function cancelBooking(bookingId, reason) {
  const res = await apiFetch(`/api/bookings/${bookingId}/cancel`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ reason: reason || null }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw Object.assign(new Error(err.detail ?? "Failed to cancel booking"), { status: res.status });
  }
  return res.json();
}

/**
 * Owner (or admin) withdraws their own hold or pending booking.
 * @param {number} bookingId
 * @param {string} [reason]  Optional custom reason; defaults to 'withdrawn by bookie'.
 */
export async function withdrawBooking(bookingId, reason = "") {
  const res = await apiFetch(`/api/bookings/${bookingId}/withdraw`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ reason: reason || null }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw Object.assign(new Error(err.detail ?? "Failed to withdraw booking"), { status: res.status });
  }
  return res.json();
}

/**
 * Bookie (or admin) requests cancellation of their own BOOKED event.
 * Status stays 'booked' until admin confirms.
 * @param {number} bookingId
 * @param {string} reason  Required, non-empty.
 */
export async function requestCancel(bookingId, reason) {
  const res = await apiFetch(`/api/bookings/${bookingId}/request-cancel`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ reason }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw Object.assign(new Error(err.detail ?? "Failed to request cancellation"), { status: res.status });
  }
  return res.json();
}

/**
 * Admin confirms a pending cancellation request on a booked event.
 * @param {number} bookingId
 */
export async function confirmCancel(bookingId) {
  const res = await apiFetch(`/api/bookings/${bookingId}/confirm-cancel`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw Object.assign(new Error(err.detail ?? "Failed to confirm cancellation"), { status: res.status });
  }
  return res.json();
}

// ---------------------------------------------------------------------------
// Settings endpoints (slice #29)
// ---------------------------------------------------------------------------

/** Fetch system settings (any authenticated user). */
export async function getSettings() {
  const res = await apiFetch("/api/settings");
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? "Failed to load settings");
  }
  return res.json();
}

/**
 * Partially update system settings (admin only).
 * @param {Object} patch  Any subset of SettingsPatch fields.
 * @returns {Promise<Object>} Updated SettingsRead
 */
export async function updateSettings(patch) {
  const res = await apiFetch("/api/settings", {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    const detail = err.detail;
    const msg = Array.isArray(detail)
      ? detail.map((e) => e.msg ?? String(e)).join("; ")
      : (detail ?? "Failed to update settings");
    throw Object.assign(new Error(msg), { status: res.status });
  }
  return res.json();
}

// ---------------------------------------------------------------------------
// Notifications (#27)
// ---------------------------------------------------------------------------

/** List the current user's notifications, newest first. */
export async function listNotifications({ unread, limit = 50 } = {}) {
  const params = new URLSearchParams();
  if (unread !== undefined) params.set("unread", String(unread));
  if (limit) params.set("limit", String(limit));
  const qs = params.toString();
  const res = await apiFetch(`/api/notifications${qs ? `?${qs}` : ""}`);
  if (!res.ok) throw new Error("Failed to load notifications");
  return res.json();
}

/** Get the unread notification count for the current user. */
export async function unreadCount() {
  const res = await apiFetch("/api/notifications/unread-count");
  if (!res.ok) throw new Error("Failed to load unread count");
  return res.json();
}

/** Mark a single notification read. */
export async function markNotificationRead(id) {
  const res = await apiFetch(`/api/notifications/${id}/read`, { method: "POST" });
  if (!res.ok) throw new Error("Failed to mark notification read");
  return res.json();
}

/** Mark all of the current user's notifications read. */
export async function markAllNotificationsRead() {
  const res = await apiFetch("/api/notifications/read-all", { method: "POST" });
  if (!res.ok) throw new Error("Failed to mark all read");
  return res.json();
}

// ---------------------------------------------------------------------------
// Blackout date endpoints (slice #29)
// ---------------------------------------------------------------------------

/**
 * List blackout dates.
 * @param {{ farmhouseId?: number }} [opts]
 * @returns {Promise<Array>} [BlackoutRead]
 */
export async function listBlackouts({ farmhouseId } = {}) {
  const qs = farmhouseId != null ? `?farmhouse_id=${farmhouseId}` : "";
  const res = await apiFetch(`/api/blackouts${qs}`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? "Failed to load blackouts");
  }
  return res.json();
}

/**
 * Create a blackout date range (admin only).
 * @param {{ farmhouse_id?: number|null, start_date: string, end_date: string, reason?: string }} data
 * @returns {Promise<Object>} BlackoutRead
 */
export async function createBlackout(data) {
  const res = await apiFetch("/api/blackouts", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    const detail = err.detail;
    const msg = Array.isArray(detail)
      ? detail.map((e) => e.msg ?? String(e)).join("; ")
      : (detail ?? "Failed to create blackout");
    throw Object.assign(new Error(msg), { status: res.status });
  }
  return res.json();
}

/**
 * Delete a blackout date by id (admin only).
 * @param {number} id
 */
export async function deleteBlackout(id) {
  const res = await apiFetch(`/api/blackouts/${id}`, { method: "DELETE" });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw Object.assign(new Error(err.detail ?? "Failed to delete blackout"), { status: res.status });
  }
}

// ---------------------------------------------------------------------------
// Reports & analytics endpoints (slice #30)
// ---------------------------------------------------------------------------

function _reportsQs(params) {
  const qs = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v != null && v !== "") qs.set(k, v);
  });
  const s = qs.toString();
  return s ? `?${s}` : "";
}

/**
 * Fetch summary report: booking counts by status + monthly + yearly breakdowns.
 * @param {{ start?: string, end?: string }} [opts]
 * @returns {Promise<{counts: Object, monthly: Array, yearly: Array}>}
 */
export async function getReportSummary({ start, end } = {}) {
  const res = await apiFetch(`/api/reports/summary${_reportsQs({ start, end })}`);
  if (!res.ok) throw new Error("Failed to load summary");
  return res.json();
}

/**
 * Fetch occupancy % per farmhouse.
 * @param {{ start?: string, end?: string, farmhouse_id?: number }} [opts]
 * @returns {Promise<Array>}
 */
export async function getOccupancy({ start, end, farmhouse_id } = {}) {
  const res = await apiFetch(`/api/reports/occupancy${_reportsQs({ start, end, farmhouse_id })}`);
  if (!res.ok) throw new Error("Failed to load occupancy");
  return res.json();
}

/**
 * Fetch bookie performance metrics.
 * @param {{ start?: string, end?: string }} [opts]
 * @returns {Promise<Array>}
 */
export async function getBookiePerformance({ start, end } = {}) {
  const res = await apiFetch(`/api/reports/bookie-performance${_reportsQs({ start, end })}`);
  if (!res.ok) throw new Error("Failed to load bookie performance");
  return res.json();
}

/**
 * Fetch booking trends time-series.
 * @param {{ start?: string, end?: string, granularity?: string }} [opts]
 * @returns {Promise<Array>}
 */
export async function getTrends({ start, end, granularity = "month" } = {}) {
  const res = await apiFetch(`/api/reports/trends${_reportsQs({ start, end, granularity })}`);
  if (!res.ok) throw new Error("Failed to load trends");
  return res.json();
}

/**
 * Fetch revenue / finances analytics: totals, per-farmhouse revenue, and a
 * per-period (week/month/year) revenue breakdown.
 * @param {{ start?: string, end?: string, granularity?: string }} [opts]
 * @returns {Promise<{totals: Object, per_farmhouse: Array, granularity: string, breakdown: Array}>}
 */
export async function getReportFinances({ start, end, granularity = "month" } = {}) {
  const res = await apiFetch(`/api/reports/finances${_reportsQs({ start, end, granularity })}`);
  if (!res.ok) throw new Error("Failed to load finances");
  return res.json();
}

/**
 * Search/filter the bookings list (admin report view).
 * @param {{ farmhouse_id?, status?, start?, end?, bookie_id?, client? }} [opts]
 * @returns {Promise<Array>}
 */
export async function searchBookingsReport({
  farmhouse_id, status, start, end, bookie_id, client,
} = {}) {
  const res = await apiFetch(
    `/api/reports/bookings${_reportsQs({ farmhouse_id, status, start, end, bookie_id, client })}`,
  );
  if (!res.ok) throw new Error("Failed to search bookings");
  return res.json();
}

/**
 * Download an export file (xlsx or pdf) and trigger browser save.
 * @param {{ report: string, format: string, start?, end?, farmhouse_id?, status?, bookie_id?, client? }} opts
 */
export async function downloadReportExport({
  report, format, start, end, farmhouse_id, status, bookie_id, client,
} = {}) {
  const res = await apiFetch(
    `/api/reports/export${_reportsQs({ report, format, start, end, farmhouse_id, status, bookie_id, client })}`,
  );
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? "Export failed");
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${report}.${format}`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

// ---------------------------------------------------------------------------
// Users / bookies (admin) — roster + invite-acceptance status
// ---------------------------------------------------------------------------

/** List users (admin only). Pass {role:'bookie'} to filter. */
export async function listUsers({ role } = {}) {
  const qs = role ? `?role=${encodeURIComponent(role)}` : "";
  const res = await apiFetch(`/api/users${qs}`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? "Failed to load users");
  }
  return res.json();
}

/** Enable/disable a user (admin only). */
export async function updateUser(id, patch) {
  const res = await apiFetch(`/api/users/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw Object.assign(new Error(err.detail ?? "Failed to update user"), { status: res.status });
  }
  return res.json();
}

/** Admin creates an active user with username + password (no invite needed). */
export async function createUserDirect({ name, username, password, role = "bookie", email }) {
  const res = await apiFetch("/api/users/direct", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, username, password, role, email: email || null }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    const detail = err.detail;
    const msg = Array.isArray(detail)
      ? detail.map((e) => e.msg ?? String(e)).join("; ")
      : (detail ?? "Failed to create user");
    throw Object.assign(new Error(msg), { status: res.status });
  }
  return res.json();
}

/** Permanently remove a user and their bookings (admin only). */
export async function deleteUser(id) {
  const res = await apiFetch(`/api/users/${id}`, { method: "DELETE" });
  if (!res.ok && res.status !== 204) {
    const err = await res.json().catch(() => ({}));
    throw Object.assign(new Error(err.detail ?? "Failed to remove user"), { status: res.status });
  }
  return true;
}

// ---------------------------------------------------------------------------
// Admin direct booking — create a confirmed booking in one step
// ---------------------------------------------------------------------------

/**
 * Admin creates a confirmed booking directly (no hold/submit/approve).
 * @param {{ farmhouse_id, start_at: Date, end_at: Date, client_name, client_contact,
 *           event_type?, event_info?, notes?, quoted_price? }} data
 * On 409 conflict: throws err with err.conflict_booking_id set.
 */
export async function directBook(data) {
  const body = {
    ...data,
    start_at: data.start_at.toISOString(),
    end_at: data.end_at.toISOString(),
  };
  const res = await apiFetch("/api/bookings/direct", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (res.ok) return res.json();
  const err = await res.json().catch(() => ({}));
  const detail = err.detail;
  const msg = Array.isArray(detail)
    ? detail.map((e) => e.msg ?? String(e)).join("; ")
    : (detail ?? "Failed to create booking");
  throw Object.assign(new Error(msg), {
    status: res.status,
    conflict_booking_id: err.conflict_booking_id ?? null,
  });
}

// ---------------------------------------------------------------------------
// Platform administration (global admin only)
// ---------------------------------------------------------------------------

/** List every company on the platform with status + admin + counts. */
export async function listCompanies() {
  const res = await apiFetch("/api/companies");
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? "Failed to load companies");
  }
  return res.json();
}

/** Create an approved company together with its first admin. */
export async function createCompany({ company_name, admin_name, admin_email, admin_password }) {
  const res = await apiFetch("/api/companies", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ company_name, admin_name, admin_email, admin_password }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    const detail = err.detail;
    const msg = Array.isArray(detail)
      ? detail.map((e) => e.msg ?? String(e)).join("; ")
      : (detail ?? "Failed to create company");
    throw Object.assign(new Error(msg), { status: res.status });
  }
  return res.json();
}

/** Approve a pending company. */
export async function approveCompany(id) {
  const res = await apiFetch(`/api/companies/${id}/approve`, { method: "POST" });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw Object.assign(new Error(err.detail ?? "Failed to approve company"), { status: res.status });
  }
  return res.json();
}

/** Reject a pending company. */
export async function rejectCompany(id) {
  const res = await apiFetch(`/api/companies/${id}/reject`, { method: "POST" });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw Object.assign(new Error(err.detail ?? "Failed to reject company"), { status: res.status });
  }
  return res.json();
}

/** Permanently delete a company and all of its data. */
export async function deleteCompany(id) {
  const res = await apiFetch(`/api/companies/${id}`, { method: "DELETE" });
  if (!res.ok && res.status !== 204) {
    const err = await res.json().catch(() => ({}));
    throw Object.assign(new Error(err.detail ?? "Failed to delete company"), { status: res.status });
  }
  return true;
}

/** List all platform global admins. */
export async function listGlobalAdmins() {
  const res = await apiFetch("/api/global-admins");
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? "Failed to load global admins");
  }
  return res.json();
}

/** Add another global admin. */
export async function createGlobalAdmin({ name, email, password }) {
  const res = await apiFetch("/api/global-admins", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, email, password }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    const detail = err.detail;
    const msg = Array.isArray(detail)
      ? detail.map((e) => e.msg ?? String(e)).join("; ")
      : (detail ?? "Failed to add global admin");
    throw Object.assign(new Error(msg), { status: res.status });
  }
  return res.json();
}

/** Remove a global admin (at least one must remain). */
export async function deleteGlobalAdmin(id) {
  const res = await apiFetch(`/api/global-admins/${id}`, { method: "DELETE" });
  if (!res.ok && res.status !== 204) {
    const err = await res.json().catch(() => ({}));
    throw Object.assign(new Error(err.detail ?? "Failed to remove global admin"), { status: res.status });
  }
  return true;
}

