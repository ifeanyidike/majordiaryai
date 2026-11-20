import { File, Paths } from 'expo-file-system';

/**
 * The last data the phone loaded, kept on the phone (Josh's Part A platform
 * tests: "The app opens offline and shows when it last synced").
 *
 * A file, not AsyncStorage: Android's AsyncStorage holds 6 MB in all by
 * default (its config.gradle), shared with everything else the app keeps, and
 * the herd alone is over a thousand cows. One person's copy only, removed on
 * sign-out, so a phone handed to someone else does not show them the last
 * person's farms.
 */

export interface OfflineCopy {
  v: 1;
  userId: string;
  /** When the server last answered with fresh data (shown as "last synced"). */
  lastSyncedAt: number;
  farms: unknown[];
  cows: unknown[];
  worklist: unknown | null;
  worklistFetchedOn: string | null;
  bulls: Record<string, unknown[]>;
}

const file = () => new File(Paths.document, 'offline-copy.json');

export async function readCopy(userId: string): Promise<OfflineCopy | null> {
  try {
    const f = file();
    if (!f.exists) return null;
    const copy = JSON.parse(await f.text()) as OfflineCopy;
    return copy.v === 1 && copy.userId === userId ? copy : null;
  } catch {
    return null;   // a damaged copy is no copy; the next sync writes a new one
  }
}

export function writeCopy(copy: OfflineCopy): void {
  try {
    const f = file();
    if (!f.exists) f.create();
    f.write(JSON.stringify(copy));
  } catch {
    // Out of space or similar: the app still works online; nothing to lose.
  }
}

export function deleteCopy(): void {
  try {
    const f = file();
    if (f.exists) f.delete();
  } catch {
    // nothing to remove
  }
}
