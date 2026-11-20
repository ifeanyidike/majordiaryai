import { create } from 'zustand';
import { isSupabaseConfigured, supabase } from '@/lib/supabase';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { api, ApiError, errorMessage } from '@/lib/api';
import { deleteCopy } from '@/lib/offlineCopy';
import { friendlyAuthError } from '@/lib/authErrors';

/** The signed-in person's profile, kept on the phone so the app opens with
 *  no signal (offline mode, Josh's Part A platform tests). */
const PROFILE_KEY = 'profile-v1';

/**
 * Whose session is saved on this phone, read from storage directly. With no
 * signal and an access token over an hour old, the sign-in library reports
 * "no session" (it tries to refresh and cannot), though it keeps the session
 * to refresh when signal returns. A real sign-out removes it.
 */
async function savedSessionUserId(): Promise<string | undefined> {
  const key = (supabase.auth as unknown as { storageKey?: string }).storageKey;
  if (!key) return undefined;
  try {
    const raw = await AsyncStorage.getItem(key);
    return raw ? (JSON.parse(raw)?.user?.id as string | undefined) : undefined;
  } catch {
    return undefined;
  }
}

/** The profile kept on this phone, if it is the saved session's person. */
async function keptProfile(): Promise<UserProfile | null> {
  try {
    const [kept, userId] = await Promise.all([AsyncStorage.getItem(PROFILE_KEY), savedSessionUserId()]);
    const profile = kept ? (JSON.parse(kept) as UserProfile) : null;
    return profile && userId && profile.id === userId ? profile : null;
  } catch {
    return null;
  }
}

export type Role = 'technician' | 'admin' | 'farm' | 'vet';

export interface UserProfile {
  id: string;
  name: string;
  email: string;
  role: Role;
  phone?: string;
  farm_id?: string;
  /** False while a signed-up account waits for an admin to approve it. */
  is_active?: boolean;
}

export const AWAITING_APPROVAL_MSG =
  'Your account is waiting for an administrator to approve it. ' +
  "You'll be able to sign in as soon as they do.";

interface AuthState {
  user: UserProfile | null;
  loading: boolean;
  error: string | null;
  needsConfirmation: boolean;

  signIn: (email: string, password: string) => Promise<void>;
  signUp: (name: string, email: string, password: string, role: Role, phone?: string) => Promise<void>;
  signOut: () => Promise<void>;
  loadProfile: () => Promise<void>;
  /** The library reported no session: open as the person whose session is
   *  still saved on the phone (no signal, token expired). False when there is
   *  none, as after a real sign-out. */
  restoreSaved: () => Promise<boolean>;
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
const ROLES: readonly Role[] = ['technician', 'admin', 'farm', 'vet'];

async function createProfileFromMetadata(): Promise<UserProfile | null> {
  const { data } = await supabase.auth.getUser();
  const authUser = data.user;
  if (!authUser) return null;
  const meta = (authUser.user_metadata ?? {}) as Record<string, unknown>;

  // No fallback. This writes the role into the database, so defaulting a
  // missing or unrecognized value to 'technician' silently created a
  // technician account — with the daily route, the farm list and every
  // recording capability — for anyone whose signup metadata was incomplete.
  // A guess here is permanent in a way a guess in the UI is not.
  const role = meta.role as Role | undefined;
  if (!role || !ROLES.includes(role)) {
    throw new Error(
      'Your sign-up did not record which role you have. Ask an administrator ' +
      'to set it up for you.',
    );
  }

  return api.post<UserProfile>('/users/me', {
    name: (meta.name as string) ?? authUser.email ?? 'New user',
    email: authUser.email,
    role,
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
      set({ error: friendlyAuthError(e, 'Could not sign in — try again.'), loading: false });
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
      set({ error: friendlyAuthError(e, 'Could not create the account — try again.'), loading: false });
    }
  },

  signOut: async () => {
    // Before the session goes: the request that forgets this phone needs it.
    // Otherwise the next person to use the device keeps receiving the
    // previous account's alarms until they sign in themselves.
    const { unregisterPush } = await import('@/lib/push');
    await unregisterPush();
    const { error: outError } = await supabase.auth.signOut();
    if (outError) {
      // With no signal and an expired token the library stops before
      // removing its saved session, and would sign this person back in the
      // next time the app opens with signal. Remove it here.
      const key = (supabase.auth as unknown as { storageKey?: string }).storageKey;
      if (key) await AsyncStorage.multiRemove([key, `${key}-code-verifier`]).catch(() => {});
    }
    set({ user: null, error: null, needsConfirmation: false });
    // The next person on this phone must not open the app as this one, or
    // see their farms. (Saves still waiting stay, under this person's id,
    // and go when they next sign in here.)
    await AsyncStorage.removeItem(PROFILE_KEY).catch(() => {});
    deleteCopy();
    // Clear the previous account's herd data so the next login starts clean.
    const { useAppStore } = await import('./useAppStore');
    useAppStore.getState().reset();
  },

  restoreSaved: async () => {
    const profile = await keptProfile();
    if (profile) set({ user: profile, loading: false, error: null });
    return !!profile;
  },

  loadProfile: async () => {
    try {
      const profile = await api.get<UserProfile>('/users/me');
      // Signup is open, so a new account exists but reaches nothing until an
      // admin activates it. Say so here rather than letting them into an app
      // where every single request comes back 403 with no explanation.
      if (profile.is_active === false) {
        set({ user: null, loading: false, error: AWAITING_APPROVAL_MSG });
        return;
      }
      set({ user: profile, loading: false, error: null });
      AsyncStorage.setItem(PROFILE_KEY, JSON.stringify(profile)).catch(() => {});
    } catch (e: any) {
      // No signal: open the app as the person whose session this is, from the
      // profile kept the last time it loaded. Only theirs: the session's own
      // user id must match.
      if (e instanceof ApiError && e.noResponse) {
        const profile = await keptProfile();
        if (profile) {
          set({ user: profile, loading: false, error: null });
          return;
        }
      }
      if (e instanceof ApiError && e.status === 404) {
        // Fresh signup whose profile row doesn't exist yet — create it now.
        try {
          const created = await createProfileFromMetadata();
          if (created) {
            // A freshly created profile is always pending approval.
            set({
              user: created.is_active === false ? null : created,
              loading: false,
              error: created.is_active === false ? AWAITING_APPROVAL_MSG : null,
            });
            return;
          }
          set({ loading: false, error: 'Could not create your profile. Please try again.' });
        } catch (createErr: any) {
          set({ loading: false, error: errorMessage(createErr, 'Could not create your profile — try again.') });
        }
        return;
      }
      set({
        loading: false,
        error: errorMessage(e, 'Could not reach the server. Check your connection and try again.'),
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
      set({ user: current, error: errorMessage(e, 'Could not update your profile') });
      return false;
    }
  },

  clearError: () => set({ error: null }),
}));

/**
 * The signed-in user's role, or null while it is still unknown.
 *
 * Screens used to write `user?.role ?? 'technician'`. That is a capability
 * decision made from missing data: for the render before the auth guard
 * settles, a farm manager or vet is shown the technician's tab bar, dashboard
 * and actions — and every technician-scoped fetch fires on their behalf.
 *
 * Null means "we do not know yet", and the caller must render a neutral
 * loading state rather than guess. Never default it.
 */
export const useRole = (): Role | null => useAuthStore((s) => s.user?.role ?? null);
