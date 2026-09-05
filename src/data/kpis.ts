/**
 * Reproduction KPIs — types mirroring backend/app/schemas/reports.py, and the
 * plain-language definitions shown on the KPI screen.
 *
 * Thresholds are NOT here. The backend judges every figure against published
 * benchmarks and returns the status and the target sentence; this file only
 * explains what each number means and why a farmer should care.
 */

export type KpiStatus = 'good' | 'fair' | 'poor' | 'na' | 'info';

export interface KpiValue {
  value: number | null;
  n: number;
  unit: string;
  status: KpiStatus;
  target: string | null;
}

export interface KpiCycle {
  start: string; end: string;
  eligible: number; served: number; conceived: number; unchecked: number;
  service_rate: number | null; conception_rate: number | null; pregnancy_rate: number | null;
  pending: boolean;
}

export interface KpiMonth {
  month: string; checked: number; pregnant: number; unchecked: number; rate: number | null;
}

export interface KpiReport {
  as_of: string;
  period_days: number;
  cycle_days: number;
  assumptions: Record<string, number>;
  pregnancy_rate_21d: KpiValue;
  service_rate_21d: KpiValue;
  cycles: KpiCycle[];
  conception: {
    rate: KpiValue;
    first_service_rate: KpiValue;
    services_per_conception: KpiValue;
    unchecked_breedings: number;
    by_month: KpiMonth[];
  };
  timing: {
    days_open: KpiValue & { mean: number | null; buckets: Record<string, number> };
    days_to_first_service: KpiValue;
    calving_interval_months: KpiValue;
  };
  outcomes: {
    stillbirth_rate: KpiValue;
    calvings: number;
    sexed_semen_heifer_rate: KpiValue;
    conventional_heifer_rate: KpiValue;
    cull_rate: KpiValue;
    culls: number;
    overdue_pregnancy_checks: KpiValue;
  };
  compliance: {
    protocol_on_time_rate: KpiValue & { on_time: number; late: number; missed: number };
    protocol_completion_rate: KpiValue & { completed: number; cancelled: number; active: number };
    heat_check_coverage: KpiValue;
  };
}

export interface KpiDefinition {
  title: string;
  formula: string;
  why: string;
}

export const KPI_DEFINITIONS: KpiDefinition[] = [
  {
    title: '21-day pregnancy rate',
    formula: 'Cows that became pregnant in a 21-day cycle ÷ cows eligible to be bred at the start of it. Eligible = 70+ days since calving (or 395+ days old for a heifer), not already pregnant, still in the herd.',
    why: 'The single best measure of a breeding programme. It combines how many eligible cows you actually breed with how many of those conceive. Cycles from the last 50 days are shown as pending because their pregnancy checks are not in yet. A breeding with no result counts as not pregnant, so a late check lowers the rate until it is entered — each bar shows how many are still awaiting checks.',
  },
  {
    title: 'Service rate',
    formula: 'Eligible cows bred in the cycle ÷ eligible cows.',
    why: 'How well heats are being caught and acted on. A low service rate caps the pregnancy rate no matter how good conception is.',
  },
  {
    title: 'Conception rate',
    formula: 'Breedings confirmed pregnant ÷ breedings with a pregnancy check result, last 12 months. Unchecked breedings are counted separately.',
    why: 'Semen, timing and technique. First-service conception isolates the first breeding after calving.',
  },
  {
    title: 'Services per conception',
    formula: 'All breedings ÷ pregnancies, last 12 months.',
    why: 'The straw cost of each pregnancy.',
  },
  {
    title: 'Days open',
    formula: 'Calving to the breeding that produced the pregnancy, for cows confirmed pregnant in the last 12 months. The median is shown; heifers have no days open.',
    why: 'Every day open past ~120 costs milk and lengthens the calving interval.',
  },
  {
    title: 'Days to first service',
    formula: 'Calving to the first breeding after it.',
    why: 'How quickly cows are put back to work after the 70-day waiting period.',
  },
  {
    title: 'Calving interval',
    formula: 'Time between consecutive calvings, for second calvings in the last 24 months.',
    why: 'The long-run result of everything above. Needs at least two calvings per cow, so it fills in over time.',
  },
  {
    title: 'Stillbirth rate',
    formula: 'Stillbirths ÷ calvings, last 12 months.',
    why: 'Calving management and sire selection.',
  },
  {
    title: 'Sexed-semen heifer rate',
    formula: 'Heifer calves ÷ live calves from breedings with sexed semen. Each calf is matched to the breeding nearest 283 days before it. Conventional semen is shown beside it as the control.',
    why: 'Whether the sexed product is delivering the ~90% heifers it is sold on.',
  },
  {
    title: 'Cull rate',
    formula: 'Cows culled in the last 12 months ÷ (current herd + those culls).',
    why: 'Turnover. Reproductive failure is the biggest single reason cows leave a herd.',
  },
  {
    title: 'Protocol shots on time',
    formula: 'Needling injections given on their scheduled day ÷ all injections that were due. Late and missed are counted separately.',
    why: 'Synchronisation protocols only work when every shot lands on the day. This system knows which did.',
  },
  {
    title: 'Heat-check coverage',
    formula: 'Breedings that got a heat check in the day 20–25 window ÷ breedings whose window has passed.',
    why: 'A missed heat check is a missed chance to catch a failed breeding three weeks early.',
  },
];
