import { supabase } from './supabase';

const API_URL = process.env.EXPO_PUBLIC_API_URL ?? (__DEV__ ? 'http://localhost:8000' : null);

/** False when no API base URL is available. */
export const isApiConfigured = API_URL != null;

/**
 * Bundled demo data — an explicit choice, never an accident.
 *
 * The store used to fall back to demo data whenever the API was
 * unconfigured. In a release build that means one missing EAS environment
 * variable ships an app that shows a real farmer a herd of invented cows,
 * with invented pregnancies and dry-off dates, and no indication that any of
 * it is fake — while every save silently does nothing.
 *
 * So demo data now requires either a development build or an explicit opt-in.
 * A release build with no API URL is a broken build, and says so.
 */
export const isDemoMode =
  process.env.EXPO_PUBLIC_DEMO_MODE === '1' || (__DEV__ && !isApiConfigured);

/** A release build that shipped without an API URL: not demo, just broken. */
export const isMisconfigured = !isApiConfigured && !isDemoMode;

export const API_NOT_CONFIGURED_MESSAGE =
  'This app was built without a server address. Contact your administrator — ' +
  'no data can be loaded or saved.';

async function getAuthHeader(): Promise<Record<string, string>> {
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
): Promise<T> {
  if (!API_URL) {
    throw new ApiError(API_NOT_CONFIGURED_MESSAGE, 0);
  }

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(await getAuthHeader()),
  };

  const res = await fetch(`${API_URL}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (!res.ok) {
    const raw = await res.text();
    let message = raw;
    try {
      const parsed = JSON.parse(raw);
      if (typeof parsed?.detail === 'string') message = parsed.detail;
    } catch {
      // keep raw text
    }
    throw new ApiError(message || `${method} ${path} failed (${res.status})`, res.status);
  }

  if (res.status === 204) return undefined as T;
  return res.json();
}

/** Multipart file upload (React Native file objects: {uri, name, type}). */
async function upload<T>(
  path: string,
  file: { uri: string; name: string; type: string },
  field = 'file',
): Promise<T> {
  if (!API_URL) {
    throw new ApiError(API_NOT_CONFIGURED_MESSAGE, 0);
  }
  const form = new FormData();
  // React Native's FormData accepts this file descriptor shape.
  form.append(field, { uri: file.uri, name: file.name, type: file.type } as any);

  const res = await fetch(`${API_URL}${path}`, {
    method: 'POST',
    headers: await getAuthHeader(), // let fetch set the multipart boundary
    body: form,
  });

  if (!res.ok) {
    const raw = await res.text();
    let message = raw;
    try {
      const parsed = JSON.parse(raw);
      if (typeof parsed?.detail === 'string') message = parsed.detail;
    } catch {
      // keep raw text
    }
    throw new ApiError(message || `upload ${path} failed (${res.status})`, res.status);
  }
  return res.json();
}

export const api = {
  get: <T>(path: string) => request<T>('GET', path),
  /**
   * Fetch every page of a paginated list endpoint.
   *
   * The API bounds list responses (see X-Total-Count), but herd statistics are
   * computed from the full set, so a partially-loaded list would silently show
   * wrong counts. This walks the pages and returns the whole thing. `maxItems`
   * is a safety valve: a herd larger than that is a signal to move the screen
   * to lazy loading rather than to raise the cap.
   */
  getAll: async <T>(path: string, pageSize = 200, maxItems = 5000): Promise<T[]> => {
    const out: T[] = [];
    let offset = 0;
    for (;;) {
      const sep = path.includes('?') ? '&' : '?';
      const page = await request<T[]>('GET', `${path}${sep}limit=${pageSize}&offset=${offset}`);
      out.push(...page);
      if (page.length < pageSize || out.length >= maxItems) break;
      offset += pageSize;
    }
    return out;
  },
  post: <T>(path: string, body: unknown) => request<T>('POST', path, body),
  patch: <T>(path: string, body: unknown) => request<T>('PATCH', path, body),
  put: <T>(path: string, body: unknown) => request<T>('PUT', path, body),
  delete: <T>(path: string) => request<T>('DELETE', path),
  upload,
};
