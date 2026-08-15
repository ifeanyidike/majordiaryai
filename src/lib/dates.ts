/**
 * Date helpers. All ISO day strings (YYYY-MM-DD) are treated as LOCAL dates —
 * never `new Date(iso)` directly, which parses them as UTC and shifts day
 * counts around midnight.
 */

const DAY_MS = 86_400_000;

/** Parse a YYYY-MM-DD (or full ISO) string as a local date at midnight */
export function parseLocalDate(iso: string): Date {
  const [datePart] = iso.split('T');
  const [y, m, d] = datePart.split('-').map(Number);
  return new Date(y, (m ?? 1) - 1, d ?? 1);
}

/** Today as a local YYYY-MM-DD string — computed at call time, never cached at module load */
export function todayISO(): string {
  const now = new Date();
  const m = String(now.getMonth() + 1).padStart(2, '0');
  const d = String(now.getDate()).padStart(2, '0');
  return `${now.getFullYear()}-${m}-${d}`;
}

/** Whole days from `iso` until today (0 if missing or in the future) */
export function daysSince(iso?: string | null): number {
  if (!iso) return 0;
  const start = parseLocalDate(iso).getTime();
  const today = parseLocalDate(todayISO()).getTime();
  return Math.max(0, Math.round((today - start) / DAY_MS));
}

/** Whole days between two ISO dates (0 if either is missing) */
export function daysBetween(fromIso?: string | null, toIso?: string | null): number {
  if (!fromIso || !toIso) return 0;
  const from = parseLocalDate(fromIso).getTime();
  const to = parseLocalDate(toIso).getTime();
  return Math.max(0, Math.round((to - from) / DAY_MS));
}

/** ISO date `days` after the given ISO date */
export function addDays(iso: string, days: number): string {
  const d = parseLocalDate(iso);
  d.setDate(d.getDate() + days);
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${d.getFullYear()}-${m}-${day}`;
}

/** YYYY-MM-DD that is also a real day on the calendar (rejects 2026-02-31) */
export function isRealDate(iso: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(iso)) return false;
  const d = parseLocalDate(iso);
  if (Number.isNaN(d.getTime())) return false;
  const [y, m, day] = iso.split('-').map(Number);
  return d.getFullYear() === y && d.getMonth() === m - 1 && d.getDate() === day;
}

/** Loose YYYY-MM-DD validation + real-calendar check, not in the future */
export function isValidPastOrTodayDate(iso: string): boolean {
  if (!isRealDate(iso)) return false;
  return parseLocalDate(iso).getTime() <= parseLocalDate(todayISO()).getTime();
}

/**
 * A protocol start date the form will accept.
 *
 * Enrolment was gated on the YYYY-MM-DD shape alone, so 2026-13-45 passed and
 * so did a typo'd year. A protocol schedules ten days of injections off this
 * date, so a wrong one silently books a technician's route weeks out or lands
 * every step in the past where nothing is ever due.
 *
 * Yesterday is allowed (recording an enrolment the next morning is normal) and
 * so is roughly a month ahead, which covers the Mon/Tue/Sat push-forward and
 * planning a herd's next round.
 */
export const START_DATE_BACKDATE_DAYS = 1;
export const START_DATE_LOOKAHEAD_DAYS = 30;

export function isValidStartDate(iso: string): boolean {
  if (!isRealDate(iso)) return false;
  const t = parseLocalDate(iso).getTime();
  const today = parseLocalDate(todayISO()).getTime();
  return (
    t >= today - START_DATE_BACKDATE_DAYS * DAY_MS &&
    t <= today + START_DATE_LOOKAHEAD_DAYS * DAY_MS
  );
}
