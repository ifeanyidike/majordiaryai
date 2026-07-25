import { create } from 'zustand';
import { api, isApiConfigured } from '@/lib/api';
import { daysBetween, daysSince } from '@/lib/dates';
import { Cow, CowStatus, Farm, HistoryEvent, TaskStatus, TechTask, Vet } from '@/data/types';
import {
  cows as demoCows,
  farms as demoFarms,
  initialTasks as demoTasks,
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

interface ApiCowReportRow {
  id: string; ear_tag: string; farm_id: string; farm_name: string;
}

interface ApiNeedlingRecord {
  id: string; cow_id: string; treatment: string;
  protocol_day: number; scheduled_date: string;
  farm_id?: string;
  is_final_day?: boolean; is_final?: boolean;
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
  tasks: TechTask[];
  notifications: AppNotification[];
  kpis: HerdKpis | null;
  farmsLoading: boolean;
  cowsLoading: boolean;
  vetsLoading: boolean;
  tasksLoading: boolean;
  notificationsLoading: boolean;
  farmsError: string | null;
  cowsError: string | null;
  vetsError: string | null;
  tasksError: string | null;
  /** True when running from bundled demo data (no API configured) */
  demoMode: boolean;

  fetchFarms: () => Promise<void>;
  fetchCows: (farmId?: string) => Promise<void>;
  refreshCow: (id: string) => Promise<void>;
  fetchCowHistory: (id: string) => Promise<void>;
  fetchVets: () => Promise<void>;
  fetchTasks: () => Promise<void>;
  fetchKpis: () => Promise<void>;
  fetchNotifications: () => Promise<void>;
  markNotificationRead: (id: string) => Promise<void>;
  setTaskStatus: (taskId: string, status: TaskStatus) => void;
  addTaskNote: (taskId: string, note: string) => void;
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
  tasks: [] as TechTask[],
  notifications: [] as AppNotification[],
  kpis: null as HerdKpis | null,
  farmsLoading: false,
  cowsLoading: false,
  vetsLoading: false,
  tasksLoading: false,
  notificationsLoading: false,
  farmsError: null as string | null,
  cowsError: null as string | null,
  vetsError: null as string | null,
  tasksError: null as string | null,
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

  fetchTasks: async () => {
    if (!isApiConfigured) {
      set({ tasks: demoTasks, tasksError: null, demoMode: true });
      return;
    }
    set({ tasksLoading: true, tasksError: null });
    try {
      const [heatCows, needlingRecs, calvingCows, pregDue, breedingRows, vaccRows] = await Promise.all([
        api.get<ApiCowReportRow[]>('/reports/heat-check').catch(() => [] as ApiCowReportRow[]),
        api.get<ApiNeedlingRecord[]>('/needling/today').catch(() => [] as ApiNeedlingRecord[]),
        api.get<ApiCowReportRow[]>('/reports/due-to-calve?days_ahead=3').catch(() => [] as ApiCowReportRow[]),
        // Returns { next_check_date, cows } — tolerate a bare array too
        api.get<{ cows?: ApiCowReportRow[] } | ApiCowReportRow[]>('/reports/pregnancy-check-due')
          .then((r) => (Array.isArray(r) ? r : r.cows ?? []))
          .catch(() => [] as ApiCowReportRow[]),
        api.get<{ cow_id: string; ear_tag: string; farm_id: string }[]>('/reports/timed-breeding')
          .catch(() => [] as { cow_id: string; ear_tag: string; farm_id: string }[]),
        api.get<{ id: string; cow_id: string; ear_tag: string; farm_id: string }[]>('/vaccinations/due')
          .catch(() => [] as { id: string; cow_id: string; ear_tag: string; farm_id: string }[]),
      ]);

      const { cows, tasks: oldTasks } = get();
      // Keep locally-completed state across refetches: rebuilt tasks with the
      // same id inherit their previous status and note.
      const prior = new Map(oldTasks.map((t) => [t.id, t]));
      const carry = (t: TechTask): TechTask => {
        const old = prior.get(t.id);
        return old ? { ...t, status: old.status, note: old.note } : t;
      };

      const calvingTasks: TechTask[] = calvingCows.map((c) => carry({
        id: `calving-${c.id}`, cowId: c.id, kind: 'calving',
        time: '07:00 AM', farmId: c.farm_id,
        title: `Due to Calve: ${c.ear_tag}`, status: 'pending',
      }));

      const heatTasks: TechTask[] = heatCows.map((c) => carry({
        id: `heat-${c.id}`, cowId: c.id, kind: 'heat',
        time: '08:00 AM', farmId: c.farm_id,
        title: `Heat Check: ${c.ear_tag}`, status: 'pending',
      }));

      const pregTasks: TechTask[] = pregDue.map((c) => carry({
        id: `preg-${c.id}`, cowId: c.id, kind: 'preg',
        time: '10:00 AM', farmId: c.farm_id,
        title: `Preg Check: ${c.ear_tag}`, status: 'pending',
      }));

      const breedingTasks: TechTask[] = breedingRows.map((r) => carry({
        id: `breeding-${r.cow_id}`, cowId: r.cow_id, kind: 'insemination',
        time: '09:30 AM', farmId: r.farm_id,
        title: `Inseminate: ${r.ear_tag}`, status: 'pending',
      }));

      const vaccinationTasks: TechTask[] = vaccRows.map((r) => carry({
        id: `vacc-${r.id}`, cowId: r.cow_id, kind: 'vaccination',
        time: '11:00 AM', farmId: r.farm_id,
        title: `Vaccinate: ${r.ear_tag}`, status: 'pending',
      }));

      const needlingTasks: TechTask[] = needlingRecs.map((r) => {
        const cow = cows.find((c) => c.id === r.cow_id);
        return carry({
          id: `needling-${r.id}`, cowId: r.cow_id, kind: 'needling',
          isFinalDay: Boolean(r.is_final_day ?? r.is_final ?? /insemin/i.test(r.treatment)),
          time: '09:00 AM', farmId: r.farm_id ?? cow?.farmId ?? '',
          title: `Needling: ${r.treatment} (Day ${r.protocol_day})`,
          status: 'pending' as TaskStatus,
        });
      });

      set({
        tasks: [
          ...calvingTasks, ...heatTasks, ...breedingTasks,
          ...needlingTasks, ...pregTasks, ...vaccinationTasks,
        ],
        tasksLoading: false,
      });
    } catch (e: any) {
      set({ tasksLoading: false, tasksError: e.message ?? 'Could not load tasks' });
    }
  },

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

  setTaskStatus: (taskId, status) =>
    set((s) => ({ tasks: s.tasks.map((t) => (t.id === taskId ? { ...t, status } : t)) })),

  addTaskNote: (taskId, note) =>
    set((s) => ({ tasks: s.tasks.map((t) => (t.id === taskId ? { ...t, note } : t)) })),

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
