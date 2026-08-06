import { create } from 'zustand';
import { api, isApiConfigured } from '@/lib/api';
import { daysBetween, daysSince } from '@/lib/dates';
import {
  Cow, CowStatus, Farm, HealthStatus, HistoryEvent, Vet,
  Worklist, WorklistCow, WorklistFarm, WorklistReport,
} from '@/data/types';
import {
  cows as demoCows,
  farms as demoFarms,
  demoWorklist,
  vets as demoVets,
} from '@/data/mock';

export type { Role } from './useAuthStore';

// ── API response shapes (snake_case) ─────────────────────────

interface ApiFarm {
  id: string; name: string; owner_name: string; address: string;
  city: string; province: string; postal_code?: string | null;
  phone: string; email: string;
  herd_size: number; cow_count?: number;
  assigned_technician_id?: string; assigned_technician_name?: string | null;
  notes?: string | null;
}

interface ApiCow {
  id: string; ear_tag: string; farm_id: string; farm_name?: string;
  status: string; breed?: string; date_of_birth?: string;
  lactation_number: number; current_program?: string;
  notes?: string | null;
  health_status?: string | null; recheck_due_date?: string | null;
  last_calving_date?: string; last_insemination_date?: string;
  last_insemination_id?: string; bull_used?: string;
  due_date?: string; dry_date?: string;
}

interface ApiNotification {
  id: string; farm_id: string; cow_id?: string | null;
  type: string; message: string; read: boolean; created_at: string;
}

interface ApiVet {
  id: string; name: string; clinic?: string | null;
  phone?: string | null; email?: string | null; farm_ids: string[];
  upcoming_visits?: number; pending_cases?: number;
}

interface ApiWorklistCow {
  cow_id: string; ear_tag: string; farm_id: string; status: string;
  action: string; detail: string;
  lactation_number?: number;
  days_in_milk?: number | null; days_post_ai?: number | null;
  last_insemination_id?: string | null; last_insemination_date?: string | null;
  last_calving_date?: string | null; health_status?: string | null;
  record_kind?: string | null;
  treatment?: string | null; protocol?: string | null; protocol_day?: number | null;
  needling_record_id?: string | null;
  needling_completed?: boolean;
  overdue?: boolean;
  missed_shots?: number;
  also_pending?: number;
}

interface ApiWorklistReport {
  type: string; title: string; icon: string; status_key: string;
  is_work_report: boolean; count: number; subtitle: string; can_record: boolean;
  cows?: ApiWorklistCow[];
}

interface ApiWorklistFarm {
  farm_id: string; farm_name: string;
  address?: string | null; city?: string | null;
  province?: string | null; phone?: string | null;
  schedule: string; schedule_label: string;
  covering_technician?: string | null; reassign_reason?: string | null;
  visit_interval_days?: number; next_visit_date?: string | null;
  total_cows?: number;
  reports?: ApiWorklistReport[];
}

interface ApiWorklist {
  date: string;
  farms?: ApiWorklistFarm[];
}

interface ApiHerdSummary {
  total?: number;
  pregnancy_rate?: number;
  conception_rate?: number;
  services_per_conception?: number | null;
  upcoming_calvings_30d?: number;
}

// ── Mappers ──────────────────────────────────────────────────

function mapFarm(f: ApiFarm): Farm {
  return {
    id: f.id, name: f.name, owner: f.owner_name,
    address: f.address ?? '', city: f.city ?? '',
    province: f.province ?? '',
    postalCode: f.postal_code ?? undefined,
    phone: f.phone ?? '',
    email: f.email ?? '',
    herdSize: f.cow_count ?? 0,
    reportedHerdSize: f.herd_size || undefined,
    // Display the technician's name, not the raw user id.
    assignedTechnician: f.assigned_technician_name ?? '',
    vetId: '', upcomingActivities: [],
    notes: f.notes ? [f.notes] : [],
  };
}

const KNOWN_STATUSES: CowStatus[] = [
  'calf', 'heifer', 'fresh', 'open', 'needling', 'inseminated',
  'pregnant', 'dry', 'calving', 'cull', 'sold', 'dead',
];

const NOT_MILKING: CowStatus[] = ['dry', 'cull', 'sold', 'dead', 'calf', 'heifer'];

function mapCow(c: ApiCow): Cow {
  const status: CowStatus = KNOWN_STATUSES.includes(c.status as CowStatus)
    ? (c.status as CowStatus)
    : 'open';

  // Days in milk runs from the last calving for every lactating status —
  // pregnant cows milk until dry-off (day 223), so they keep counting.
  const daysInMilk =
    c.last_calving_date && !NOT_MILKING.includes(status)
      ? daysSince(c.last_calving_date)
      : 0;

  // Days open is historical: calving → conception for pregnant/dry cows,
  // calving → today while the cow is still open.
  const daysOpen = !c.last_calving_date
    ? 0
    : ['pregnant', 'dry'].includes(status)
      ? daysBetween(c.last_calving_date, c.last_insemination_date)
      : daysSince(c.last_calving_date);

  // In-heat = inside the day 20–25 heat-check window after insemination
  const dsi = daysSince(c.last_insemination_date);
  const inHeat = status === 'inseminated' && dsi >= 20 && dsi <= 25;

  return {
    id: c.id, earTag: c.ear_tag, farmId: c.farm_id,
    status,
    inHeat,
    breed: c.breed ?? '', dateOfBirth: c.date_of_birth ?? '',
    lactationNumber: c.lactation_number ?? 0,
    currentProgram: c.current_program ?? '',
    currentLocation: c.farm_name ?? '',
    notes: c.notes ?? undefined,
    healthStatus: c.health_status === 'sick' ? 'sick' : c.health_status === 'healthy' ? 'healthy' : undefined,
    recheckDueDate: c.recheck_due_date ?? undefined,
    lastCalvingDate: c.last_calving_date,
    lastInseminationDate: c.last_insemination_date,
    lastInseminationId: c.last_insemination_id,
    bullUsed: c.bull_used,
    dueDate: c.due_date, dryDate: c.dry_date,
    daysInMilk, daysOpen,
    history: { inseminations: [], pregnancyChecks: [], vaccinations: [], treatments: [], calvings: [] },
  };
}

/**
 * The worklist arrives fully computed — this only renames snake_case to camel.
 * Deliberately no filtering, counting or rule evaluation: the moment the client
 * re-derives membership it becomes a second source of truth that can drift.
 */
function mapWorklist(w: ApiWorklist): Worklist {
  return {
    date: w.date,
    farms: (w.farms ?? []).map((f): WorklistFarm => ({
      farmId: f.farm_id,
      farmName: f.farm_name,
      address: f.address ?? undefined,
      city: f.city ?? undefined,
      province: f.province ?? undefined,
      phone: f.phone ?? undefined,
      schedule: (f.schedule as WorklistFarm['schedule']) ?? 'visit_today',
      scheduleLabel: f.schedule_label,
      coveringTechnician: f.covering_technician ?? undefined,
      reassignReason: f.reassign_reason ?? undefined,
      visitIntervalDays: f.visit_interval_days ?? 0,
      nextVisitDate: f.next_visit_date ?? undefined,
      totalCows: f.total_cows ?? 0,
      reports: (f.reports ?? []).map((r): WorklistReport => ({
        type: r.type,
        title: r.title,
        icon: r.icon,
        statusKey: r.status_key,
        isWorkReport: r.is_work_report,
        count: r.count,
        subtitle: r.subtitle,
        canRecord: r.can_record,
        cows: (r.cows ?? []).map((c) => ({
          cowId: c.cow_id,
          earTag: c.ear_tag,
          farmId: c.farm_id,
          status: c.status as CowStatus,
          action: c.action,
          detail: c.detail,
          lactationNumber: c.lactation_number ?? 0,
          daysInMilk: c.days_in_milk ?? null,
          daysPostAi: c.days_post_ai ?? null,
          lastInseminationId: c.last_insemination_id ?? undefined,
          lastInseminationDate: c.last_insemination_date ?? undefined,
          lastCalvingDate: c.last_calving_date ?? undefined,
          healthStatus: (c.health_status as HealthStatus | undefined) ?? undefined,
          recordKind: (c.record_kind as WorklistCow['recordKind']) ?? null,
          treatment: c.treatment ?? undefined,
          protocol: c.protocol ?? undefined,
          protocolDay: c.protocol_day ?? undefined,
          needlingRecordId: c.needling_record_id ?? undefined,
          needlingCompleted: c.needling_completed ?? false,
          overdue: c.overdue ?? false,
          missedShots: c.missed_shots ?? 0,
          alsoPending: c.also_pending ?? 0,
        })),
      })),
    })),
  };
}


function mapVet(v: ApiVet): Vet {
  return {
    id: v.id, name: v.name,
    clinic: v.clinic ?? '', phone: v.phone ?? '',
    email: v.email ?? '', farmIds: v.farm_ids.map(String),
    notes: '',
    upcomingVisits: v.upcoming_visits ?? 0,
    pendingCases: v.pending_cases ?? 0,
  };
}

function toHistoryEvents(rows: any[] | undefined, describe: (r: any) => string): HistoryEvent[] {
  if (!Array.isArray(rows)) return [];
  return rows.map((r, i) => ({
    id: String(r.id ?? i),
    date: String(r.date ?? r.insemination_date ?? r.check_date ?? r.calving_date ?? r.scheduled_date ?? r.administered_at ?? '').slice(0, 10),
    detail: describe(r),
  }));
}

// ── Store ─────────────────────────────────────────────────────

export interface HerdKpis {
  pregnancyRate: number | null;
  conceptionRate: number | null;
  servicesPerConception: number | null;
  upcomingCalvings30d: number;
}

export interface AppNotification {
  id: string;
  farmId: string;
  cowId?: string;
  type: string;
  message: string;
  read: boolean;
  createdAt: string;
}

function mapNotification(n: ApiNotification): AppNotification {
  return {
    id: n.id, farmId: n.farm_id, cowId: n.cow_id ?? undefined,
    type: n.type, message: n.message, read: n.read, createdAt: n.created_at,
  };
}

interface AppState {
  farms: Farm[];
  cows: Cow[];
  vets: Vet[];
  /** The technician's day, exactly as the server computed it. */
  worklist: Worklist | null;
  /** Device-local date (YYYY-MM-DD) the worklist was last fetched on. */
  worklistFetchedOn: string | null;
  notifications: AppNotification[];
  kpis: HerdKpis | null;
  farmsLoading: boolean;
  cowsLoading: boolean;
  vetsLoading: boolean;
  worklistLoading: boolean;
  notificationsLoading: boolean;
  farmsError: string | null;
  cowsError: string | null;
  vetsError: string | null;
  worklistError: string | null;
  /** True when running from bundled demo data (no API configured) */
  demoMode: boolean;

  fetchFarms: () => Promise<void>;
  fetchCows: (farmId?: string) => Promise<void>;
  refreshCow: (id: string) => Promise<void>;
  fetchCowHistory: (id: string) => Promise<void>;
  fetchVets: () => Promise<void>;
  fetchWorklist: () => Promise<void>;
  /** Fetch the worklist if it's missing or from a previous calendar day. */
  ensureWorklist: () => void;
  /** Demo mode only: locally clear an actioned row so the demo stays usable. */
  completeWorklistCowDemo: (reportType: string, cowId: string) => void;
  fetchKpis: () => Promise<void>;
  fetchNotifications: () => Promise<void>;
  markNotificationRead: (id: string) => Promise<void>;
  addFarmNote: (farmId: string, note: string) => void;
  reset: () => void;
}

/** Compute KPIs locally from demo data */
function demoKpis(cows: Cow[]): HerdKpis {
  const breedable = cows.filter((c) => !['calf', 'cull', 'sold', 'dead'].includes(c.status));
  const pregnant = cows.filter((c) => ['pregnant', 'dry'].includes(c.status));
  const services = cows.reduce((n, c) => n + c.history.inseminations.length, 0);
  // due within the next 30 days
  const today = new Date();
  const in30 = new Date(today.getFullYear(), today.getMonth(), today.getDate() + 30);
  const upcomingCount = cows.filter((c) => {
    if (!c.dueDate) return false;
    const [y, m, d] = c.dueDate.split('-').map(Number);
    const due = new Date(y, m - 1, d);
    return due >= today && due <= in30;
  }).length;
  return {
    pregnancyRate: breedable.length ? Math.round((pregnant.length / breedable.length) * 100) : null,
    conceptionRate: services ? Math.round((pregnant.length / services) * 100) : null,
    servicesPerConception: pregnant.length ? Number((services / pregnant.length).toFixed(1)) : null,
    upcomingCalvings30d: upcomingCount,
  };
}

/** Synthesize demo notifications from the bundled herd so the screen isn't empty offline */
function demoNotifications(cows: Cow[]): AppNotification[] {
  const items: AppNotification[] = [];
  cows.forEach((c) => {
    if (c.status === 'dry') {
      items.push({
        id: `n-dry-${c.id}`, farmId: c.farmId, cowId: c.id, type: 'dry_off',
        message: `${c.earTag} has dried off — move her to the dry pen.`,
        read: false, createdAt: c.dryDate ?? '',
      });
    }
    if (c.status === 'fresh') {
      items.push({
        id: `n-fresh-${c.id}`, farmId: c.farmId, cowId: c.id, type: 'calving',
        message: `${c.earTag} just calved — now Fresh.`,
        read: true, createdAt: c.lastCalvingDate ?? '',
      });
    }
  });
  return items.sort((a, b) => (a.createdAt < b.createdAt ? 1 : -1));
}

const initialData = {
  farms: [] as Farm[],
  cows: [] as Cow[],
  vets: [] as Vet[],
  worklist: null as Worklist | null,
  worklistFetchedOn: null as string | null,
  notifications: [] as AppNotification[],
  kpis: null as HerdKpis | null,
  farmsLoading: false,
  cowsLoading: false,
  vetsLoading: false,
  worklistLoading: false,
  notificationsLoading: false,
  farmsError: null as string | null,
  cowsError: null as string | null,
  vetsError: null as string | null,
  worklistError: null as string | null,
  demoMode: !isApiConfigured,
};

export const useAppStore = create<AppState>((set, get) => ({
  ...initialData,

  fetchFarms: async () => {
    if (!isApiConfigured) {
      set({ farms: demoFarms, farmsError: null, demoMode: true });
      return;
    }
    set({ farmsLoading: true, farmsError: null });
    try {
      const raw = await api.get<ApiFarm[]>('/farms/');
      set({ farms: raw.map(mapFarm), farmsLoading: false });
    } catch (e: any) {
      set({ farmsLoading: false, farmsError: e.message ?? 'Could not load farms' });
    }
  },

  fetchCows: async (farmId) => {
    if (!isApiConfigured) {
      set({ cows: demoCows, cowsError: null, demoMode: true });
      return;
    }
    set({ cowsLoading: true, cowsError: null });
    try {
      const path = farmId ? `/cows/?farm_id=${farmId}` : '/cows/';
      const raw = await api.get<ApiCow[]>(path);
      const fetched = raw.map(mapCow);
      set((s) => ({
        // A farm-scoped fetch merges into the herd — it must never wipe
        // other farms' cows out of the global list.
        cows: farmId
          ? [...s.cows.filter((c) => c.farmId !== farmId), ...fetched]
          : fetched,
        cowsLoading: false,
      }));
    } catch (e: any) {
      set({ cowsLoading: false, cowsError: e.message ?? 'Could not load cows' });
    }
  },

  refreshCow: async (id) => {
    if (!isApiConfigured) return;
    try {
      const raw = await api.get<ApiCow>(`/cows/${id}`);
      const updated = mapCow(raw);
      set((s) => ({
        cows: s.cows.map((c) =>
          c.id === id
            ? { ...updated, history: c.history } // keep loaded history
            : c,
        ),
      }));
    } catch {
      // non-fatal: profile keeps showing the cached cow
    }
  },

  fetchCowHistory: async (id) => {
    if (!isApiConfigured) return;
    try {
      const h = await api.get<any>(`/cows/${id}/history`);
      const history = {
        inseminations: toHistoryEvents(h.inseminations, (r) =>
          `AI — ${r.bull_name ?? 'bull n/a'}${r.semen_type ? ` (${r.semen_type})` : ''}`),
        pregnancyChecks: toHistoryEvents(h.pregnancy_checks, (r) =>
          r.result === 'pregnant' ? 'Confirmed pregnant' : 'Open'),
        vaccinations: toHistoryEvents(h.vaccinations, (r) =>
          r.vaccine_name ?? 'Vaccination'),
        treatments: toHistoryEvents(h.needling_records, (r) =>
          `${r.treatment ?? 'Injection'}${r.protocol_day ? ` (Day ${r.protocol_day})` : ''}`),
        calvings: toHistoryEvents(h.calvings, (r) => {
          const sex = r.calf_sex ? `${r.calf_sex} calf` : 'Calving';
          return r.still_birth ? `${sex} — stillborn` : sex;
        }),
      };
      set((s) => ({ cows: s.cows.map((c) => (c.id === id ? { ...c, history } : c)) }));
    } catch {
      // history stays empty; the profile shows its empty states
    }
  },

  fetchVets: async () => {
    if (!isApiConfigured) {
      set({ vets: demoVets, vetsError: null, demoMode: true });
      return;
    }
    set({ vetsLoading: true, vetsError: null });
    try {
      const raw = await api.get<ApiVet[]>('/vets/');
      set({ vets: raw.map(mapVet), vetsLoading: false });
    } catch (e: any) {
      set({ vetsLoading: false, vetsError: e.message ?? 'Could not load vets' });
    }
  },

  fetchWorklist: async () => {
    // Always the FULL worklist. A farm-scoped fetch here once replaced the
    // whole store slice with a one-farm payload, collapsing the To-Do list and
    // every dashboard count until an unscoped refetch happened.
    const fetchedOn = new Date().toLocaleDateString('en-CA');
    if (!isApiConfigured) {
      set({ worklist: demoWorklist, worklistFetchedOn: fetchedOn, worklistError: null, demoMode: true });
      return;
    }
    set({ worklistLoading: true, worklistError: null });
    try {
      const raw = await api.get<ApiWorklist>('/reports/worklist');
      set({ worklist: mapWorklist(raw), worklistFetchedOn: fetchedOn, worklistLoading: false });
    } catch (e: any) {
      set({ worklistLoading: false, worklistError: e.message ?? 'Could not load your work list' });
    }
  },

  ensureWorklist: () => {
    const { worklist, worklistFetchedOn, worklistLoading, fetchWorklist } = get();
    // Compare against the DEVICE date the payload was fetched on, not the
    // server's payload date — a server in another timezone would never match
    // the device's calendar and every check would refetch forever.
    const today = new Date().toLocaleDateString('en-CA');
    if (!worklistLoading && (!worklist || worklistFetchedOn !== today)) fetchWorklist();
  },

  completeWorklistCowDemo: (reportType, cowId) =>
    // Demo mode has no API to record against; this keeps the bundled demo
    // interactive by removing the actioned row the way a refetch would.
    set((s) => {
      if (!s.worklist) return s;
      const farms = s.worklist.farms.map((farm) => {
        const reports = farm.reports
          .map((r) =>
            r.type === reportType
              ? { ...r, cows: r.cows.filter((c) => c.cowId !== cowId) }
              : r,
          )
          .map((r) => ({ ...r, count: r.cows.length }))
          .filter((r) => r.cows.length > 0);
        const totalCows = new Set(
          reports.filter((r) => r.isWorkReport).flatMap((r) => r.cows.map((c) => c.cowId)),
        ).size;
        return { ...farm, reports, totalCows };
      });
      return { worklist: { ...s.worklist, farms } };
    }),

  fetchKpis: async () => {
    if (!isApiConfigured) {
      set({ kpis: demoKpis(demoCows) });
      return;
    }
    try {
      const s = await api.get<ApiHerdSummary>('/reports/herd-summary');
      set({
        kpis: {
          pregnancyRate: s.pregnancy_rate ?? null,
          conceptionRate: s.conception_rate ?? null,
          servicesPerConception: s.services_per_conception ?? null,
          upcomingCalvings30d: s.upcoming_calvings_30d ?? 0,
        },
      });
    } catch {
      // KPI strip renders placeholders when unavailable
    }
  },

  fetchNotifications: async () => {
    if (!isApiConfigured) {
      set({ notifications: demoNotifications(get().cows.length ? get().cows : demoCows) });
      return;
    }
    set({ notificationsLoading: true });
    try {
      const raw = await api.get<ApiNotification[]>('/notifications/');
      set({ notifications: raw.map(mapNotification), notificationsLoading: false });
    } catch {
      set({ notificationsLoading: false });
    }
  },

  markNotificationRead: async (id) => {
    // Optimistic — the bell badge shouldn't lag the tap.
    set((s) => ({
      notifications: s.notifications.map((n) => (n.id === id ? { ...n, read: true } : n)),
    }));
    if (!isApiConfigured) return;
    try {
      await api.patch(`/notifications/${id}/read`, {});
    } catch {
      // non-fatal; a refetch will reconcile
    }
  },

  addFarmNote: (farmId, note) =>
    set((s) => ({
      farms: s.farms.map((f) => (f.id === farmId ? { ...f, notes: [note, ...(f.notes ?? [])] } : f)),
    })),

  reset: () => set({ ...initialData, demoMode: !isApiConfigured }),
}));

// ── Selectors ─────────────────────────────────────────────────

export const farmById = (s: AppState, id: string) => s.farms.find((f) => f.id === id);
export const cowById = (s: AppState, id: string) => s.cows.find((c) => c.id === id);
export const cowsByFarm = (s: AppState, farmId: string) => s.cows.filter((c) => c.farmId === farmId);
export const vetById = (s: AppState, id: string) => s.vets.find((v) => v.id === id) ?? null;

export const unreadNotificationCount = (s: AppState) =>
  s.notifications.filter((n) => !n.read).length;

/** API already scopes by role, so just return all cows */
export const visibleCows = (s: AppState) => s.cows;

/** API already scopes by role, so just return all farms */
export const visibleFarms = (s: AppState) => s.farms;

export interface HerdSummary {
  total: number; pregnant: number; open: number;
  dry: number; fresh: number; cull: number; heat: number;
  inseminated: number; needling: number;
}

export const summarize = (list: Cow[]): HerdSummary => ({
  total: list.filter((c) => !['sold', 'dead'].includes(c.status)).length,
  pregnant: list.filter((c) => c.status === 'pregnant').length,
  open: list.filter((c) => c.status === 'open').length,
  dry: list.filter((c) => c.status === 'dry').length,
  fresh: list.filter((c) => c.status === 'fresh').length,
  cull: list.filter((c) => c.status === 'cull').length,
  inseminated: list.filter((c) => c.status === 'inseminated').length,
  needling: list.filter((c) => c.status === 'needling').length,
  heat: list.filter((c) => c.inHeat).length,
});

// ── Worklist selectors ───────────────────────────────────────
// Pure reads over the server's payload. None of these decide which cows belong
// on a report — that rule lives in the backend catalog and only there.

/** Farms on the technician's route today, in server order (busiest first). */
export const worklistFarms = (s: AppState): WorklistFarm[] => s.worklist?.farms ?? [];

/** Farms he should actually walk into — reassigned/skipped days excluded. */
export const farmsToVisit = (s: AppState): WorklistFarm[] =>
  worklistFarms(s).filter((f) => f.schedule === 'visit_today' || f.schedule === 'covering');

export const farmWorklist = (s: AppState, farmId?: string): WorklistFarm | undefined =>
  farmId ? worklistFarms(s).find((f) => f.farmId === farmId) : undefined;

/** Work reports with cows at this farm — layer 2 of the To-Do list. */
export const farmWorkReports = (s: AppState, farmId?: string): WorklistReport[] =>
  (farmWorklist(s, farmId)?.reports ?? []).filter((r) => r.isWorkReport);

/** Total cows needing work today across the farms he is visiting. */
export const worklistTotal = (s: AppState): number =>
  farmsToVisit(s).reduce((n, f) => n + f.totalCows, 0);

/**
 * One report merged across every farm — the Reports hub and any unscoped report
 * screen. Counts stay consistent with the per-farm view because both come from
 * the same rows.
 */
export function mergedReports(s: AppState): WorklistReport[] {
  const byType = new Map<string, WorklistReport>();
  const farmCount = new Map<string, number>();
  for (const farm of worklistFarms(s)) {
    for (const report of farm.reports) {
      farmCount.set(report.type, (farmCount.get(report.type) ?? 0) + 1);
      const existing = byType.get(report.type);
      if (existing) {
        existing.cows = [...existing.cows, ...report.cows];
        existing.count = existing.cows.length;
        // The per-farm subtitle ("3 cows require injection") is wrong for a
        // merged list — restate it over the merged rows.
        existing.subtitle = `${existing.count} ${existing.count === 1 ? 'cow' : 'cows'} across ${
          farmCount.get(report.type)
        } farms`;
      } else {
        byType.set(report.type, { ...report, cows: [...report.cows] });
      }
    }
  }
  return [...byType.values()];
}

export const reportFromWorklist = (
  s: AppState,
  type: string,
  farmId?: string,
): WorklistReport | undefined =>
  farmId
    ? farmWorklist(s, farmId)?.reports.find((r) => r.type === type)
    : mergedReports(s).find((r) => r.type === type);

export interface PregnancyCounts {
  /** On the Pregnancy Report (day 30+). */
  due: number;
  /** Past the Pregnancy Check Warning threshold (day 50+). */
  warning: number;
}

/**
 * Pregnancy-check counts for a farm, or the whole scope when no farm is given.
 *
 * Derived from the work list rather than re-deriving "day 30 / day 50" here:
 * those thresholds are the backend catalog's, and a second copy in the client
 * is how the vet's dashboard and the vet's report end up disagreeing.
 */
export function pregnancyCounts(s: AppState, farmId?: string): PregnancyCounts {
  const report = reportFromWorklist(s, 'pregnancy-check', farmId);
  const cows = report?.cows ?? [];
  return { due: cows.length, warning: cows.filter((c) => c.overdue).length };
}
