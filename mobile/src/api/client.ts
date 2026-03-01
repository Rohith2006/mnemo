import { getItem, setItem, removeItem } from "../storage";

const SERVER_URL_KEY = "mnemo_server_url";
const TOKEN_KEY = "mnemo_token";

let cachedServerUrl: string | null = null;
let cachedToken: string | null = null;

export async function getServerUrl(): Promise<string | null> {
  if (cachedServerUrl === null) cachedServerUrl = await getItem(SERVER_URL_KEY);
  return cachedServerUrl;
}

export async function setServerUrl(url: string, persist: boolean = true): Promise<void> {
  // persist=false: update the in-memory value so the imminent login/signup call
  // actually hits this URL, without writing an unconfirmed address to storage:
  // a failed attempt shouldn't leave a broken default behind for next time.
  const trimmed = url.trim().replace(/\/+$/, "");
  cachedServerUrl = trimmed;
  if (persist) await setItem(SERVER_URL_KEY, trimmed);
}

export async function getToken(): Promise<string | null> {
  if (cachedToken === null) cachedToken = await getItem(TOKEN_KEY);
  return cachedToken;
}

export async function setToken(token: string): Promise<void> {
  cachedToken = token;
  await setItem(TOKEN_KEY, token);
}

export async function clearToken(): Promise<void> {
  cachedToken = null;
  await removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, options: RequestInit = {}, withAuth = true): Promise<T> {
  const base = await getServerUrl();
  if (!base) throw new ApiError(0, "No server URL configured yet.");

  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (withAuth) {
    const token = await getToken();
    if (token) headers.Authorization = `Bearer ${token}`;
  }

  let res: Response;
  try {
    res = await fetch(`${base}${path}`, { ...options, headers: { ...headers, ...(options.headers as object) } });
  } catch {
    throw new ApiError(0, `Couldn't reach the server at ${base}. Check it's running and on the same network.`);
  }

  if (res.status === 204) return undefined as T;

  const isJson = res.headers.get("content-type")?.includes("application/json");
  const body = isJson ? await res.json().catch(() => null) : null;

  if (!res.ok) {
    throw new ApiError(res.status, body?.detail || `Request failed (${res.status})`);
  }
  return body as T;
}

export const api = {
  get: <T>(path: string) => request<T>(path, { method: "GET" }),
  post: <T>(path: string, body?: unknown, withAuth = true) =>
    request<T>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined }, withAuth),
  patch: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "PATCH", body: JSON.stringify(body) }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
};
