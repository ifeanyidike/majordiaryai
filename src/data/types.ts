export type CowStatus =
  | 'calf' | 'heifer' | 'fresh' | 'open' | 'needling'
  | 'inseminated' | 'pregnant' | 'dry' | 'calving' | 'cull'
  | 'sold' | 'dead';

export type HealthStatus = 'healthy' | 'sick';

export interface HistoryEvent {
  id: string;
  date: string; // ISO
  detail: string;
}

export interface Cow {
  id: string;
  earTag: string;
  farmId: string;
  status: CowStatus;
  inHeat?: boolean;
  breed: string;
  dateOfBirth: string;
  lactationNumber: number;
  currentProgram: string;
  currentLocation: string;
  notes?: string;
  healthStatus?: HealthStatus;
  recheckDueDate?: string;
  lastCalvingDate?: string;
  lastInseminationDate?: string;
  lastInseminationId?: string;
  bullUsed?: string;
  dueDate?: string;
  dryDate?: string;
  cullDate?: string;
  cullReason?: string;
  daysInMilk: number;
  daysOpen: number;
  history: {
    inseminations: HistoryEvent[];
    pregnancyChecks: HistoryEvent[];
    vaccinations: HistoryEvent[];
    treatments: HistoryEvent[];
    calvings: HistoryEvent[];
  };
}

export interface Farm {
  id: string;
  name: string;
  owner: string;
  address: string;
  city: string;
  province: string;
  postalCode?: string;
  phone: string;
  email: string;
  /** Cows tracked in the system (computed) — the number KPIs use */
  herdSize: number;
  /** Owner-reported total herd size, when it differs from tracked cows */
  reportedHerdSize?: number;
  assignedTechnician: string;
  /** FK for editing; `assignedTechnician` above is the resolved display name. */
  assignedTechnicianId?: string;
  /** Weekdays this farm is visited, Mon=0 … Sun=6 (5-day = Mon–Fri). */
  visitWeekdays: number[];
  /** Display label for the schedule, e.g. "Mon–Sat". */
  visitScheduleLabel?: string;
  vetId: string;
  upcomingActivities: { id: string; icon: string; label: string; date: string }[];
  notes: string[];
}

export interface Vet {
  id: string;
  name: string;
  clinic: string;
  phone: string;
  email: string;
  farmIds: string[];
  notes: string;
  upcomingVisits: number;
  pendingCases: number;
}

/**
 * The technician's work list, exactly as the server computed it.
 *
 * Report membership rules live in the backend (app/services/report_catalog.py)
 * and nowhere else. The client renders this — it derives no "which cows are on
 * the Heat Report" logic of its own, because two copies of that rule drift and
 * a drifted rule makes a cow silently vanish from someone's day.
 */

/** Which inline form records this row's outcome; null = read-only for this user. */
export type RecordKind =
  | 'heat'
  | 'preg'
  | 'needling'
  | 'insemination'
  | 'vaccination'
  | 'calving'
  | 'enroll'
  | 'dry_off';

export interface WorklistCow {
  cowId: string;
  earTag: string;
  farmId: string;
  status: CowStatus;
  /** "Action Required" — the imperative instruction for this cow today. */
  action: string;
  detail: string;
  lactationNumber: number;
  daysInMilk: number | null;
  daysPostAi: number | null;
  /** Carried so a row can open its recording form without refetching the cow. */
  lastInseminationId?: string;
  lastInseminationDate?: string;
  lastCalvingDate?: string;
  healthStatus?: HealthStatus;
  recordKind: RecordKind | null;
  treatment?: string;
  protocol?: string;
  protocolDay?: number;
  needlingRecordId?: string;
  needlingCompleted: boolean;
  overdue: boolean;
  /** Timed Breeding: shots hidden by the overlap rule that were never given. */
  missedShots: number;
  /** Needling: pending injections beyond the one shown. */
  alsoPending: number;
}

export interface WorklistReport {
  type: string;
  title: string;
  icon: string;
  statusKey: string;
  isWorkReport: boolean;
  count: number;
  subtitle: string;
  canRecord: boolean;
  cows: WorklistCow[];
}

/** Why a farm is (or isn't) on this technician's route today. `not_due` farms
 * are in scope but off-rotation — hidden from the route, kept for herd views. */
export type VisitSchedule = 'visit_today' | 'covering' | 'reassigned' | 'skipped' | 'not_due';

export interface WorklistFarm {
  farmId: string;
  farmName: string;
  address?: string;
  city?: string;
  province?: string;
  phone?: string;
  schedule: VisitSchedule;
  /** "Visit Today" / "Reassigned to Relief Tech — Skip" */
  scheduleLabel: string;
  coveringTechnician?: string;
  reassignReason?: string;
  /** Weekdays this farm is visited, Mon=0 … Sun=6. */
  visitWeekdays: number[];
  /** Display label for the schedule, e.g. "Mon–Sat". */
  visitScheduleLabel?: string;
  nextVisitDate?: string;
  totalCows: number;
  reports: WorklistReport[];
}

export interface Worklist {
  date: string;
  farms: WorklistFarm[];
}

export interface Technician {
  name: string;
  role: string;
  employeeId?: string;
  phone: string;
  email: string;
  region: string;
  activeFarms?: number;
}

/** A staff member the admin can assign to a farm. */
export interface StaffUser {
  id: string;
  name: string;
  email: string;
  role: string;
}
