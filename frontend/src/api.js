// Thin API client. The base URL comes from VITE_API_BASE (empty means same origin, via the dev proxy).
const BASE = import.meta.env.VITE_API_BASE ?? "";
const KEY_STORAGE = "neobank.apiKey";

export function getStoredApiKey() {
  return localStorage.getItem(KEY_STORAGE) ?? "";
}

export function storeApiKey(key) {
  if (key) localStorage.setItem(KEY_STORAGE, key);
  else localStorage.removeItem(KEY_STORAGE);
}

function describeError(detail) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map((d) => `${d.loc?.slice(1).join(".") ?? "field"}: ${d.msg}`).join("; ");
  }
  return "Request failed";
}

export async function api(path, { method = "GET", body } = {}) {
  const headers = { "Content-Type": "application/json" };
  const key = getStoredApiKey();
  if (key) headers["X-API-Key"] = key;

  let response;
  try {
    response = await fetch(`${BASE}/v1${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new Error("Could not reach the API. Check the API base URL.");
  }

  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(describeError(data.detail) || `Request failed (${response.status})`);
  }
  return data;
}

export const money = (minor, currency = "USD") =>
  new Intl.NumberFormat(undefined, { style: "currency", currency }).format(minor / 100);
