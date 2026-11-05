const BASE = import.meta.env.VITE_API_URL ?? '';
const TOKEN_KEY = 'tts_token';
const USER_KEY = 'tts_user';

// Browser storage can be unavailable (private mode, blocked site data), so every access is guarded.
export function getToken() {
  try { return localStorage.getItem(TOKEN_KEY); } catch { return null; }
}
export function readUser() {
  try { return JSON.parse(localStorage.getItem(USER_KEY)); } catch { return null; }
}
export function saveSession(token, user) {
  try {
    if (token) {
      localStorage.setItem(TOKEN_KEY, token);
      localStorage.setItem(USER_KEY, JSON.stringify(user));
    } else {
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(USER_KEY);
    }
  } catch { /* the session then lasts only until the page is reloaded */ }
}

export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

let onUnauthorized = () => {};
export function setUnauthorizedHandler(fn) {
  onUnauthorized = fn;
}

export async function api(path, { method = 'GET', body } = {}) {
  const headers = { 'Content-Type': 'application/json' };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  let res;
  try {
    res = await fetch(`${BASE}/api${path}`, { method, headers, body: body ? JSON.stringify(body) : undefined });
  } catch {
    throw new ApiError(0, 'Cannot reach the server. Check your connection.');
  }
  if (res.status === 204) return null;

  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    if (res.status === 401 && token) onUnauthorized(); // expired or invalid session: sign out
    const details = data.details?.map((d) => d.message).join('; ');
    throw new ApiError(res.status, details || data.error || `Request failed (${res.status})`);
  }
  return data;
}