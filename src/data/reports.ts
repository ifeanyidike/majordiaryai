import { WorklistReport } from './types';

/**
 * Presentation helpers for reports.
 *
 * This file used to hold a second implementation of every report rule — which
 * cows are on the Heat Report, when a cow is overdue, and so on — alongside the
 * backend's. Two copies of a membership rule drift, and a drifted rule makes a
 * cow silently disappear from a technician's day. The rules now live in
 * `backend/app/services/report_catalog.py` and only there; the client renders
 * the server's rows and owns nothing but their appearance.
 */

/** Reports that read as a daily route, shown first on the Reports hub. */
export const DAILY_REPORT_TYPES = ['heat', 'timed-breeding', 'needling', 'insemination'];

/** Program reports — event- or day-triggered rather than daily. */
export const PROGRAM_REPORT_TYPES = [
  'pregnancy-check', 'vaccination', 'post-calving', 'dry-report', 'fresh', 'open-report',
];

/** Reference lists: never work, never counted in a workload. */
export const LIST_REPORT_TYPES = ['calving-due', 'pregnant', 'open', 'cull'];

/**
 * Titles and icons for reports with no rows today. When the server returns a
 * report it wins — these only fill the gap so an empty report still has a name.
 */
const REPORT_TITLES: Record<string, string> = {
  heat: 'Heat Report',
  'timed-breeding': 'Timed Breeding',
  needling: 'Needling Report',
  insemination: 'Insemination Program',
  'pregnancy-check': 'Pregnancy Report',
  vaccination: 'Vaccination Report',
  'dry-report': 'Dry Report',
  'post-calving': 'Post Calving Report',
  'calving-due': 'Upcoming Calvings',
  fresh: 'Fresh / Calving Report',
  'open-report': 'Open Cow Report',
  pregnant: 'Pregnant Cow List',
  open: 'Open Cow List',
  cull: 'Cull Cow List',
};

const REPORT_ICONS: Record<string, string> = {
  heat: 'flame',
  'timed-breeding': 'flask',
  needling: 'fitness',
  insemination: 'git-branch',
  'pregnancy-check': 'medkit',
  vaccination: 'shield-checkmark',
  'dry-report': 'moon',
  'post-calving': 'bandage',
  'calving-due': 'alarm',
  fresh: 'heart',
  'open-report': 'ellipse-outline',
  pregnant: 'heart-circle',
  open: 'list-circle',
  cull: 'alert-circle',
};

export const knownReportType = (type: string) => type in REPORT_TITLES;

/** Reports of the given types that currently have rows, in the order listed. */
export function reportsIn(reports: WorklistReport[], types: string[]): WorklistReport[] {
  return types
    .map((type) => reports.find((r) => r.type === type))
    .filter((r): r is WorklistReport => r !== undefined);
}

/** A report the server didn't return has no cows — render the zero state. */
export function emptyReport(type: string): WorklistReport {
  return {
    type,
    title: REPORT_TITLES[type] ?? 'Report',
    icon: REPORT_ICONS[type] ?? 'document-text',
    statusKey: 'open',
    isWorkReport: !LIST_REPORT_TYPES.includes(type),
    count: 0,
    subtitle: '0 cows',
    canRecord: false,
    cows: [],
  };
}
