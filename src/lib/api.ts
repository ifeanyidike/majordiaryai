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
  /** No answer came back: no signal, or the time limit ran out. The request
   *  may or may not have reached the server. */
  noResponse: boolean;
  constructor(message: string, status: number, noResponse = false) {
    super(message);
    this.status = status;
    this.noResponse = noResponse;
  }
}

/** Josh's Part A platform tests: "Slow connections show loading, time out
 *  with a retry, and never freeze." Every request gives up after this long. */
const TIMEOUT_MS = 20_000;
// An import uploads a spreadsheet and the server reads every row before it
// answers; a large herd takes a while even on a good line.
const UPLOAD_TIMEOUT_MS = 120_000;

export const NO_SIGNAL_MESSAGE = 'No signal — check your connection and try again.';
export const TOO_SLOW_MESSAGE = 'The connection is too slow — try again.';

/** fetch with a time limit that covers reading the whole answer, not just
 *  its start: on a crawling connection the body can stall after the headers
 *  arrive. A dropped or slow connection becomes an ApiError with noResponse
 *  set, never a request that waits forever. */
interface Answer { status: number; ok: boolean; text: string }

async function send(url: string, init: RequestInit, timeoutMs: number): Promise<Answer> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(url, { ...init, signal: controller.signal });
    const text = await res.text();
    return { status: res.status, ok: res.ok, text };
  } catch {
    const timedOut = controller.signal.aborted;
    throw new ApiError(timedOut ? TOO_SLOW_MESSAGE : NO_SIGNAL_MESSAGE, 0, true);
  } finally {
    clearTimeout(timer);
  }
}

function parsed<T>(answer: Answer): T {
  if (answer.status === 204 || !answer.text) return undefined as T;
  return JSON.parse(answer.text) as T;
}

/** The sign-in token, within the same time limit: on a bad line an expired
 *  token's refresh is itself a request, and it has no limit of its own. */
function authHeaderInTime(): Promise<Record<string, string>> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(
      () => reject(new ApiError(TOO_SLOW_MESSAGE, 0, true)), TIMEOUT_MS);
    getAuthHeader().then(
      (h) => { clearTimeout(timer); resolve(h); },
      (e) => { clearTimeout(timer); reject(e); },
    );
  });
}

/** What to say for an error the server gave no plain message for. Shown as
 *  is in the app, so it must read as a sentence: never the raw reply, which
 *  can be a list of field codes or a proxy's HTML page. */
function plainFor(status: number): string {
  if (status === 401) return 'Your sign-in has run out — sign in again.';
  if (status === 403) return "You don't have permission to do that.";
  if (status === 404) return 'That could not be found — it may have been removed.';
  if (status === 413) return 'That file is too big.';
  if (status === 422) return 'Some details are missing or not valid — check them and try again.';
  if (status === 429) return 'Too many tries — wait a minute and try again.';
  if (status === 502 || status === 503 || status === 504) {
    return "The server isn't answering right now — try again in a moment.";
  }
  if (status >= 500) return 'Something went wrong on our side — try again in a moment.';
  return 'Something went wrong — try again.';
}

function failure(answer: Answer, label: string): ApiError {
  let detail: unknown;
  try {
    detail = JSON.parse(answer.text)?.detail;
  } catch {
    detail = undefined;   // not JSON: a proxy page, never shown
  }
  // The server's own sentences are shown; FastAPI's "Not authenticated" (no
  // token at all) and anything that is not a sentence get a plain one.
  const usable = typeof detail === 'string' && detail.trim() !== '' && detail !== 'Not authenticated';
  if (!usable && __DEV__) console.warn(`${label} failed (${answer.status}): ${answer.text.slice(0, 300)}`);
  return new ApiError(usable ? (detail as string) : plainFor(answer.status), answer.status);
}

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  extraHeaders?: Record<string, string>,
): Promise<T> {
  if (!API_URL) {
    throw new ApiError(API_NOT_CONFIGURED_MESSAGE, 0);
  }

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(await authHeaderInTime()),
    ...extraHeaders,
  };

  const answer = await send(`${API_URL}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  }, TIMEOUT_MS);

  if (!answer.ok) throw failure(answer, `${method} ${path}`);
  return parsed<T>(answer);
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

  const answer = await send(`${API_URL}${path}`, {
    method: 'POST',
    headers: await authHeaderInTime(), // let fetch set the multipart boundary
    body: form,
  }, UPLOAD_TIMEOUT_MS);

  if (!answer.ok) throw failure(answer, `upload ${path}`);
  return parsed<T>(answer);
}

/**
 * The message to show for a caught error. The server's sentences and our own
 * (new Error('...')) are shown; a programming error ("undefined is not an
 * object", a TypeError and the like) is not for the person holding the phone,
 * so the screen's plain fallback is shown instead.
 */
export function errorMessage(e: unknown, fallback: string): string {
  if (e instanceof ApiError) return e.message;
  if (e instanceof Error && e.name === 'Error' && e.message.trim()) return e.message;
  if (__DEV__ && e) console.warn('Unexpected error:', e);
  return fallback;
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
  // Optional body: forgetting a push token has to name WHICH device.
  delete: <T>(path: string, body?: unknown) => request<T>('DELETE', path, body),
  /** A save sent with a one-time code (offline mode, lib/outbox.ts): sent
   *  again with the same code, the server records it once. recordedAt is when
   *  it was made on the phone: the dates the server stamps itself follow it. */
  sendOnce: <T>(method: string, path: string, body: unknown, key: string, recordedAt: string) =>
    request<T>(method, path, body, { 'Idempotency-Key': key, 'Recorded-At': recordedAt }),
  upload,
};
