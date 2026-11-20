import { AppState } from 'react-native';
import { useAppStore } from '@/store/useAppStore';
import { useAuthStore } from '@/store/useAuthStore';
import { isDemoMode } from './api';
import { onReconnect } from './net';
import { readCopy, writeCopy } from './offlineCopy';
import { syncPending, useOutbox } from './outbox';

/**
 * Offline mode for one signed-in person (Josh's Part A platform tests). Fills
 * the screens from the copy kept on the phone, keeps that copy up to date,
 * and sends waiting saves whenever there may be signal again. Returns the
 * stop function, for sign-out.
 */
export function startOfflineMode(userId: string): () => void {
  if (isDemoMode) return () => {};

  readCopy(userId).then((copy) => {
    if (copy) useAppStore.getState().fillFromCopy(copy);
  });

  // Keep the copy current, a moment after the data settles.
  let timer: ReturnType<typeof setTimeout> | null = null;
  const stopCopy = useAppStore.subscribe((s, prev) => {
    if (s.lastSyncedAt == null) return;
    if (s.farms === prev.farms && s.cows === prev.cows && s.worklist === prev.worklist
        && s.bulls === prev.bulls && s.lastSyncedAt === prev.lastSyncedAt) return;
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => {
      const now = useAppStore.getState();
      // Signed out meanwhile: their copy was just removed; do not write it back.
      if (now.lastSyncedAt == null || useAuthStore.getState().user?.id !== userId) return;
      writeCopy({
        v: 1, userId, lastSyncedAt: now.lastSyncedAt,
        farms: now.farms, cows: now.cows, worklist: now.worklist,
        worklistFetchedOn: now.worklistFetchedOn, bulls: now.bulls,
      });
    }, 2000);
  });

  // Send waiting saves when signal comes back, when the app returns to the
  // front, and every minute while any are waiting.
  syncPending();
  // The waiting list is read from the phone a moment after start.
  const stopHydrated = useOutbox.persist.onFinishHydration(() => syncPending());
  // Signal back: send what is waiting, then load fresh data, so the screens
  // drop yesterday's list and their "No signal" banners without a pull, and
  // "last synced" moves on. (A sync that sent something reloads by itself.)
  const stopNet = onReconnect(() => {
    syncPending().then((sent) => {
      if (sent > 0) return;   // the sync reloaded already
      const app = useAppStore.getState();
      app.fetchWorklist();
      app.fetchFarms();
      app.fetchCows();
    });
  });
  const appState = AppState.addEventListener('change', (next) => {
    if (next === 'active') syncPending();
  });
  const every = setInterval(() => {
    if (useOutbox.getState().items.some((i) => i.userId === userId && !i.failed)) syncPending();
  }, 60_000);

  return () => {
    if (timer) clearTimeout(timer);
    stopCopy();
    stopHydrated();
    stopNet();
    appState.remove();
    clearInterval(every);
  };
}
