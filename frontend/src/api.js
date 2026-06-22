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
    throw Object.assign(new Error(err.detail ?? "Login failed"), { status: res.status });
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

