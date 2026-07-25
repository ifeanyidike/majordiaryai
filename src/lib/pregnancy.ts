import { Cow } from '@/data/types';
import { daysSince } from './dates';

/**
 * Pregnancy-check workflow thresholds (vet area — pregnancy diagnosis only).
 * The app does NOT schedule vet visits; it surfaces which cows are approaching
 * or ready for pregnancy diagnosis so the farm/vet can act on their own cadence.
 *
 *   Day 30 → cow appears on the Pregnancy Report (approaching / due)
 *   Day 50 → Pregnancy Check Warning (overdue, needs attention)
 */
export const PREGNANCY_REPORT_DAY = 30;
export const PREGNANCY_WARNING_DAY = 50;

export function daysPostAI(cow: Cow): number | null {
  return cow.lastInseminationDate ? daysSince(cow.lastInseminationDate) : null;
}

/** Inseminated cows 30+ days post-AI — the Pregnancy Report. */
export function pregnancyCheckDue(cows: Cow[]): Cow[] {
  return cows.filter((c) => {
    const d = daysPostAI(c);
    return c.status === 'inseminated' && d !== null && d >= PREGNANCY_REPORT_DAY;
  });
}

/** True once a due cow crosses the Day-50 warning threshold. */
export function isPregnancyWarning(cow: Cow): boolean {
  const d = daysPostAI(cow);
  return d !== null && d >= PREGNANCY_WARNING_DAY;
}

/** Overdue subset (Day 50+) of the Pregnancy Report. */
export function pregnancyWarnings(cows: Cow[]): Cow[] {
  return pregnancyCheckDue(cows).filter(isPregnancyWarning);
}

export interface PregnancyCounts {
  due: number;      // total on the report (30+)
  warning: number;  // overdue (50+)
}

export function pregnancyCounts(cows: Cow[]): PregnancyCounts {
  const due = pregnancyCheckDue(cows);
  return { due: due.length, warning: due.filter(isPregnancyWarning).length };
}
