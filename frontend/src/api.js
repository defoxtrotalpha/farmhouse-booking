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

export async function login(email, password) {
  const res = await fetch(`${BASE}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
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

export async function inviteBookie(name, email) {
  const res = await apiFetch("/api/invites", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, email }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw Object.assign(new Error(err.detail ?? "Failed to send invite"), { status: res.status });
  }
  return res.json();
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
    body: JSON.stringify({ reason }),
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

