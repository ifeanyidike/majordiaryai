import { create } from 'zustand';
import { isSupabaseConfigured, supabase } from '@/lib/supabase';
import { api, ApiError } from '@/lib/api';

export type Role = 'technician' | 'admin' | 'farm' | 'vet';

export interface UserProfile {
  id: string;
  name: string;
  email: string;
  role: Role;
  phone?: string;
  farm_id?: string;
}

interface AuthState {
  user: UserProfile | null;
  loading: boolean;
  error: string | null;
  needsConfirmation: boolean;

  signIn: (email: string, password: string) => Promise<void>;
  signUp: (name: string, email: string, password: string, role: Role, phone?: string) => Promise<void>;
  signOut: () => Promise<void>;
  loadProfile: () => Promise<void>;
  updateProfile: (patch: { name?: string; phone?: string }) => Promise<boolean>;
  clearError: () => void;
}

const AUTH_UNCONFIGURED_MSG =
  'Authentication is not configured for this build. Set EXPO_PUBLIC_SUPABASE_URL and EXPO_PUBLIC_SUPABASE_ANON_KEY.';

/**
 * Create the backend profile row for a confirmed Supabase user.
 * Profile data (name/role/phone) travels in Supabase user_metadata so it
 * survives the email-confirmation round trip.
 */
async function createProfileFromMetadata(): Promise<UserProfile | null> {
  const { data } = await supabase.auth.getUser();
  const authUser = data.user;
  if (!authUser) return null;
  const meta = (authUser.user_metadata ?? {}) as Record<string, unknown>;
  return api.post<UserProfile>('/users/me', {
    name: (meta.name as string) ?? authUser.email ?? 'New user',
    email: authUser.email,
    role: (meta.role as Role) ?? 'technician',
    phone: (meta.phone as string) ?? null,
  });
}

export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  loading: false,
  error: null,
  needsConfirmation: false,

  signIn: async (email, password) => {
    if (!isSupabaseConfigured) {
      set({ error: AUTH_UNCONFIGURED_MSG });
      return;
    }
    set({ loading: true, error: null });
    try {
      const { error } = await supabase.auth.signInWithPassword({ email, password });
      if (error) throw error;
      await get().loadProfile();
      if (!get().user) {
        throw new Error(get().error ?? 'Could not load your profile. Please try again.');
      }
      set({ loading: false });
    } catch (e: any) {
      set({ error: e.message ?? 'Login failed', loading: false });
    }
  },

  signUp: async (name, email, password, role, phone) => {
    if (!isSupabaseConfigured) {
      set({ error: AUTH_UNCONFIGURED_MSG });
      return;
    }
    set({ loading: true, error: null, needsConfirmation: false });
    try {
      // Profile fields ride along in user_metadata so the profile can be
      // created after email confirmation, not just in the instant-session flow.
      const { data, error } = await supabase.auth.signUp({
        email,
        password,
        options: { data: { name, role, phone: phone ?? null } },
      });
      if (error) throw error;

      if (!data.session) {
        // Email confirmation enabled — profile gets created on first sign-in
        set({ loading: false, needsConfirmation: true });
        return;
      }

      await api.post('/users/me', { name, email, role, phone: phone ?? null });
      await get().loadProfile();
      set({ loading: false });
    } catch (e: any) {
      set({ error: e.message ?? 'Registration failed', loading: false });
    }
  },

  signOut: async () => {
    await supabase.auth.signOut();
    set({ user: null, error: null, needsConfirmation: false });
    // Clear the previous account's herd data so the next login starts clean.
    const { useAppStore } = await import('./useAppStore');
    useAppStore.getState().reset();
  },

  loadProfile: async () => {
    try {
      const profile = await api.get<UserProfile>('/users/me');
      set({ user: profile, loading: false, error: null });
    } catch (e: any) {
      if (e instanceof ApiError && e.status === 404) {
        // Fresh signup whose profile row doesn't exist yet — create it now.
        try {
          const created = await createProfileFromMetadata();
          if (created) {
            set({ user: created, loading: false, error: null });
            return;
          }
          set({ loading: false, error: 'Could not create your profile. Please try again.' });
        } catch (createErr: any) {
          set({ loading: false, error: createErr.message ?? 'Could not create your profile.' });
        }
        return;
      }
      set({
        loading: false,
        error: e.message ?? 'Could not reach the server. Check your connection and try again.',
      });
    }
  },

  updateProfile: async (patch) => {
    const current = get().user;
    if (!current) return false;
    // Optimistic update; revert on failure.
    set({ user: { ...current, ...patch } });
    if (!isSupabaseConfigured) return true;
    try {
      const updated = await api.patch<UserProfile>('/users/me', patch);
      set({ user: updated });
      return true;
    } catch (e: any) {
      set({ user: current, error: e.message ?? 'Could not update your profile' });
      return false;
    }
  },

  clearError: () => set({ error: null }),
}));
