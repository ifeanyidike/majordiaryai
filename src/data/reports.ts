import { daysSince, parseLocalDate, todayISO } from '@/lib/dates';
import { PREGNANCY_REPORT_DAY, PREGNANCY_WARNING_DAY, pregnancyCheckDue } from '@/lib/pregnancy';
import { Cow, TechTask } from './types';

/**
 * Report catalog — the 9 program reports + 3 lists from the Phase 1 spec.
 * One definition drives both the Reports hub and the report detail screen so
 * counts and rows can never disagree.
 */

export interface ReportRowInfo {
  /** Doc-specified columns, rendered as the row subtitle */
  detail: (cow: Cow, farmName: string) => string;
}

export interface ReportDef {
  type: string;
  title: string;
  icon: string;
  /** Key into theme status colors for the hub row */
  statusKey: string;
  filter: (cows: Cow[], tasks: TechTask[]) => Cow[];
  detail: (cow: Cow, farmName: string) => string;
}

const dsi = (c: Cow) => daysSince(c.lastInseminationDate);
const dim = (c: Cow) => (c.lastCalvingDate ? daysSince(c.lastCalvingDate) : null);

const withinDays = (iso: string | undefined, days: number) => {
  if (!iso) return false;
  const target = parseLocalDate(iso).getTime();
  const today = parseLocalDate(todayISO()).getTime();
  return target <= today + days * 86_400_000;
};

const fmt = (iso?: string) => iso ?? '—';

export const REPORT_DEFS: ReportDef[] = [
  {
    type: 'heat',
    title: 'Heat Report',
    icon: 'flame',
    statusKey: 'heat',
    // Cows inseminated 20–25 days ago — checked daily inside the window only
    filter: (cows) => cows.filter((c) => c.status === 'inseminated' && dsi(c) >= 20 && dsi(c) <= 25),
    detail: (c, farm) => `${farm} · AI ${fmt(c.lastInseminationDate)} · Day ${dsi(c)} of 20–25`,
  },
  {
    type: 'timed-breeding',
    title: 'Timed Breeding',
    icon: 'flask',
    statusKey: 'inseminated',
    // Cows due for insemination today — final protocol day
    filter: (cows, tasks) => {
      const ids = new Set(
        tasks.filter((t) => t.kind === 'insemination' || (t.kind === 'needling' && t.isFinalDay)).map((t) => t.cowId),
      );
      return cows.filter((c) => ids.has(c.id));
    },
    detail: (c, farm) => `${farm} · ${c.currentProgram || 'Protocol'} — inseminate today`,
  },
  {
    type: 'needling',
    title: 'Needling Report',
    icon: 'fitness',
    statusKey: 'needling',
    // Cows with an injection scheduled today
    filter: (cows, tasks) => {
      const ids = new Set(tasks.filter((t) => t.kind === 'needling').map((t) => t.cowId));
      return cows.filter((c) => ids.has(c.id));
    },
    detail: (c, farm) => `${farm} · ${c.currentProgram || 'Protocol'} — injection due today`,
  },
  {
    type: 'pregnancy-check',
    title: 'Pregnancy Report',
    icon: 'medkit',
    statusKey: 'inseminated',
    // Inseminated cows on the Pregnancy Report: Day 30+ approaching/due,
    // Day 50+ overdue (warning). The vet enters a result on their next visit.
    filter: (cows) => pregnancyCheckDue(cows),
    detail: (c, farm) => {
      const d = dsi(c);
      const state = d >= PREGNANCY_WARNING_DAY ? '⚠ Overdue — ready for diagnosis' : 'Due for check';
      return `${farm} · AI ${fmt(c.lastInseminationDate)} · Day ${d} · ${state}`;
    },
  },
  {
    type: 'vaccination',
    title: 'Vaccination Report',
    icon: 'shield-checkmark',
    statusKey: 'fresh',
    // Fresh cows in the 30–50 day post-calving window
    filter: (cows) => cows.filter((c) => {
      const d = dim(c);
      return c.status === 'fresh' && d !== null && d >= 30 && d <= 50;
    }),
    detail: (c, farm) => `${farm} · Day ${dim(c)} post calving · complete by day 50`,
  },
  {
    type: 'post-calving',
    title: 'Post Calving Report',
    icon: 'bandage',
    statusKey: 'fresh',
    // Same 30–50 day window — the 2cc vaccine shot report
    filter: (cows) => cows.filter((c) => {
      const d = dim(c);
      return c.status === 'fresh' && d !== null && d >= 30 && d <= 50;
    }),
    detail: (c, farm) => `${farm} · Day ${dim(c)} post calving · 2cc vaccine due`,
  },
  {
    type: 'dry-report',
    title: 'Dry Report',
    icon: 'moon',
    statusKey: 'dry',
    // Pregnant cows at/near day 223 post insemination (due within a week or overdue)
    filter: (cows) => cows.filter((c) => c.status === 'pregnant' && withinDays(c.dryDate, 7)),
    detail: (c, farm) => `${farm} · Dry ${fmt(c.dryDate)} · Due ${fmt(c.dueDate)} — notify farmer to change pen`,
  },
  {
    type: 'fresh',
    title: 'Fresh / Calving Report',
    icon: 'heart',
    statusKey: 'fresh',
    filter: (cows) => cows.filter((c) => c.status === 'fresh'),
    detail: (c, farm) => `${farm} · Calved ${fmt(c.lastCalvingDate)} · Day ${dim(c) ?? 0}`,
  },
  {
    type: 'open-report',
    title: 'Open Cow Report',
    icon: 'ellipse-outline',
    statusKey: 'open',
    // Open cows awaiting a protocol decision (70+ days post calving or failed check)
    filter: (cows) => cows.filter((c) => c.status === 'open'),
    detail: (c, farm) =>
      c.healthStatus === 'sick'
        ? `${farm} · ${c.daysOpen} days open · Sick — recheck ${fmt(c.recheckDueDate)}`
        : `${farm} · ${c.daysOpen} days open · Healthy — ready to breed`,
  },
  // ── Lists ──
  {
    type: 'pregnant',
    title: 'Pregnant Cow List',
    icon: 'heart-circle',
    statusKey: 'pregnant',
    filter: (cows) => cows.filter((c) => ['pregnant', 'dry'].includes(c.status)),
    detail: (c, farm) =>
      `${farm} · Due ${fmt(c.dueDate)} · Dry ${fmt(c.dryDate)} · ${dsi(c)} days pregnant`,
  },
  {
    type: 'open',
    title: 'Open Cow List',
    icon: 'list-circle',
    statusKey: 'open',
    // Open + needling — enrolling in a protocol doesn't leave the open list
    filter: (cows) => cows.filter((c) => ['open', 'needling'].includes(c.status)),
    detail: (c, farm) =>
      `${farm} · ${c.daysOpen} days open · Calved ${fmt(c.lastCalvingDate)}${c.status === 'needling' ? ` · ${c.currentProgram}` : ''}`,
  },
  {
    type: 'cull',
    title: 'Cull Cow List',
    icon: 'alert-circle',
    statusKey: 'cull',
    filter: (cows) => cows.filter((c) => c.status === 'cull'),
    detail: (c, farm) =>
      `${farm} · Culled ${fmt(c.cullDate)}${c.cullReason ? ` · ${c.cullReason}` : ''}`,
  },
];

export const reportByType = (type: string) => REPORT_DEFS.find((r) => r.type === type);
