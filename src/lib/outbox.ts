import AsyncStorage from '@react-native-async-storage/async-storage';
import { Alert } from 'react-native';
import { randomUUID } from 'expo-crypto';
import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';
import { api, ApiError, errorMessage } from './api';
import { canTry } from './net';

/**
 * Outcomes saved with no signal (Josh's Part A platform tests):
 *
 *   "Outcomes recorded offline are saved as pending"
 *   "Pending records sync automatically when the connection returns, with no
 *    duplicates"
 *   "Losing signal mid-save leaves no half-saved record"
 *
 * Every outcome gets a one-time code. With signal it is sent at once; with
 * none, or when no answer comes back (the save may or may not have reached the
 * server), it waits here and is sent again with the SAME code. The server
 * records a code once (backend app/core/idempotency.py), so a save that did
 * get through before the signal dropped is not recorded twice.
 *
 * Sent in the order they were made: a cow's heat check must not reach the
 * server before the insemination it checks. A save the server refuses (the
 * cow changed meanwhile) is kept, marked failed, and shown on the Sync screen;
 * later saves for the same cow wait behind it.
 */

export interface PendingSave {
  key: string;
  userId: string;
  method: 'POST' | 'PATCH';
  path: string;
  body: unknown;
  cowId?: string;
  /** What it was, in words, for the Sync screen ("Seen in heat — 1234"). */
  label: string;
  createdAt: string;
  /** Set when the server refused it; the reason, as the server gave it. */
  failed?: string;
}

interface OutboxState {
  items: PendingSave[];
  syncing: boolean;
}

export const useOutbox = create<OutboxState>()(
  persist((): OutboxState => ({ items: [], syncing: false }), {
    name: 'outbox-v1',
    storage: createJSONStorage(() => AsyncStorage),
    partialize: (s) => ({ items: s.items }),
    // The stored list arrives a moment after start; a save made in that
    // moment must not be overwritten by it.
    merge: (stored, current) => {
      const kept = ((stored as Partial<OutboxState>)?.items ?? []);
      const keys = new Set(kept.map((i) => i.key));
      return { ...current, items: [...kept, ...current.items.filter((i) => !keys.has(i.key))] };
    },
  }),
);

/** No answer came back: the save may or may not have reached the server. A
 *  proxy that could not reach the server answers 502/503/504. */
const noAnswer = (e: unknown) =>
  e instanceof ApiError && (e.noResponse || [502, 503, 504].includes(e.status));

function currentUserId(): string | undefined {
  // Required lazily: the auth store imports the app store, which imports this.
  const { useAuthStore } = require('@/store/useAuthStore');
  return useAuthStore.getState().user?.id;
}

function add(item: PendingSave) {
  useOutbox.setState((s) => ({ items: [...s.items, item] }));
}

/** Waiting, or refused, for this cow (for "Pending" on her row and page). */
export const pendingFor = (items: PendingSave[], cowId: string) =>
  items.filter((i) => i.cowId === cowId);

export interface SaveResult<T> {
  /** True when it is waiting to be sent; `data` is then undefined. */
  queued: boolean;
  data?: T;
}

/**
 * Save an outcome. Returns the server's answer when it went through, or
 * { queued: true } when it is waiting for signal. A refusal (4xx) throws, as
 * before, so the form shows the reason.
 */
export async function saveOutcome<T = unknown>(input: {
  method?: 'POST' | 'PATCH';
  path: string;
  body: unknown;
  cowId?: string;
  label: string;
}): Promise<SaveResult<T>> {
  const userId = currentUserId();
  // Kept under nobody's name it would never be sent, nor shown.
  if (!userId) throw new Error('Sign in again to save this.');
  const item: PendingSave = {
    key: randomUUID(), userId, method: input.method ?? 'POST',
    path: input.path, body: input.body, cowId: input.cowId, label: input.label,
    createdAt: new Date().toISOString(),
  };
  // Behind an earlier save for this cow that has not gone yet: order matters.
  const waitingBehind = !!input.cowId &&
    useOutbox.getState().items.some((i) => i.cowId === input.cowId && i.userId === userId);
  if (!canTry() || waitingBehind) {
    add(item);
    if (waitingBehind) syncPending();
    return { queued: true };
  }
  try {
    const data = await api.sendOnce<T>(item.method, item.path, item.body, item.key, item.createdAt);
    return { queued: false, data };
  } catch (e) {
    if (!noAnswer(e)) throw e;
    add(item);
    return { queued: true };
  }
}

/**
 * Send what is waiting, oldest first. Stops at the first save that gets no
 * answer (still no signal). Safe to call any time; one run at a time.
 */
export async function syncPending(): Promise<number> {
  const userId = currentUserId();
  if (!userId || !canTry() || useOutbox.getState().syncing) return 0;
  useOutbox.setState({ syncing: true });
  let sent = 0;
  let stopped = false;
  try {
    // Cows whose saves wait: behind a refused one (until it is discarded), or
    // behind one the server failed on this time (retried on the next pass).
    const blocked = new Set<string>();
    for (const item of useOutbox.getState().items) {
      // Another person's saves wait for them to sign in on this phone.
      if (item.userId !== userId) continue;
      if (item.cowId && blocked.has(item.cowId)) continue;
      if (item.failed) {
        if (item.cowId) blocked.add(item.cowId);
        continue;
      }
      try {
        await api.sendOnce(item.method, item.path, item.body, item.key, item.createdAt);
        useOutbox.setState((s) => ({ items: s.items.filter((i) => i.key !== item.key) }));
        sent += 1;
      } catch (e) {
        // No answer, or signed out on the server: try everything later.
        if (noAnswer(e) || (e instanceof ApiError && e.status === 401)) {
          stopped = true;
          break;
        }
        // The server fell over: nothing was saved (one transaction). Not this
        // save's fault; keep it, and its cow's later saves, for next time.
        if (e instanceof ApiError && e.status >= 500) {
          stopped = true;
          if (item.cowId) blocked.add(item.cowId);
          continue;
        }
        const reason = errorMessage(e, 'The server refused it');
        useOutbox.setState((s) => ({
          items: s.items.map((i) => (i.key === item.key ? { ...i, failed: reason } : i)),
        }));
        if (item.cowId) blocked.add(item.cowId);
      }
    }
  } finally {
    useOutbox.setState({ syncing: false });
  }
  if (sent > 0) {
    // What was sent can move cows between reports; show the server's view.
    const { useAppStore } = require('@/store/useAppStore');
    const app = useAppStore.getState();
    app.fetchWorklist();
    app.fetchCows();
    // Saves made while this pass ran are behind it; send them now.
    if (!stopped) syncPending();
  }
  return sent;
}

/** Drop a save the server refused (from the Sync screen). */
export function discardSave(key: string) {
  useOutbox.setState((s) => ({ items: s.items.filter((i) => i.key !== key) }));
}

/**
 * Before signing out: saves still waiting stay on this phone, under this
 * person, and go when they sign in here again. Say so, and let them stay
 * signed in to let the saves go first. Resolves true to sign out.
 */
export function okToSignOut(): Promise<boolean> {
  const userId = currentUserId();
  const n = useOutbox.getState().items.filter((i) => i.userId === userId).length;
  if (n === 0) return Promise.resolve(true);
  const records = `${n} ${n === 1 ? 'record' : 'records'}`;
  return new Promise((resolve) => {
    Alert.alert(
      'Not sent yet',
      `${records} saved on this phone ${n === 1 ? 'has' : 'have'} not reached the server. `
        + (n === 1
          ? 'It stays on this phone and is sent when you sign in here again.'
          : 'They stay on this phone and are sent when you sign in here again.'),
      [
        { text: 'Stay signed in', style: 'cancel', onPress: () => resolve(false) },
        { text: 'Sign out', style: 'destructive', onPress: () => resolve(true) },
      ],
      { cancelable: true, onDismiss: () => resolve(false) },
    );
  });
}
