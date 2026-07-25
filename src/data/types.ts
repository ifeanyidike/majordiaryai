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

export type TaskStatus = 'pending' | 'in_progress' | 'done';

export type TaskKind =
  | 'heat'
  | 'needling'
  | 'preg'
  | 'calving'
  | 'insemination'
  | 'vaccination'
  | 'other';

export interface TechTask {
  id: string;
  time: string;
  farmId: string;
  title: string;
  status: TaskStatus;
  kind: TaskKind;
  /** Needling only — this is the protocol's final (insemination) day */
  isFinalDay?: boolean;
  note?: string;
  cowId?: string;
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
