import AsyncStorage from '@react-native-async-storage/async-storage';
import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';

/**
 * Local, device-persisted app preferences. These gate which in-app
 * notifications the user cares about and general app behavior. No server
 * round-trip — they live on the device via AsyncStorage.
 */
/**
 * The notifications this system actually sends.
 *
 * There are exactly three, and they are the three `create_notification` calls
 * in the backend (services/status_engine.py). Kept as a const tuple so the
 * map below is exhaustive by construction, and pinned to the backend by
 * tests/test_migrations.py — the earlier version of this file was built from
 * the SCREEN'S ICON TABLE instead, which lists aspirational types like `heat`
 * and `calving` that nothing has ever emitted. Four of the five toggles
 * therefore filtered nothing at all.
 */
export const NOTIFICATION_TYPES = ['dry_off', 'breeding_due', 'open'] as const;
export type NotificationType = (typeof NOTIFICATION_TYPES)[number];

export interface NotificationPrefs {
  dryOff: boolean;
  readyToBreed: boolean;
  needsDecision: boolean;
}

export const NOTIFICATION_TOPICS: {
  key: keyof NotificationPrefs; label: string; hint: string;
}[] = [
  {
    key: 'dryOff',
    label: 'Dry-off',
    hint: 'A cow reached day 223 and needs her pen changed',
  },
  {
    key: 'readyToBreed',
    label: 'Ready to breed',
    hint: 'A cow was seen in heat and moved to the Insemination Program',
  },
  {
    key: 'needsDecision',
    label: 'Needs a breeding decision',
    hint: 'A cow went Open — finished a protocol, lost a pregnancy, or came of age',
  },
];

/**
 * Which toggle governs each type. Exhaustive: TypeScript fails the build if a
 * new notification type is added without deciding where it belongs, which is
 * how the last set drifted out of step silently.
 */
const TOPIC_FOR_TYPE: Record<NotificationType, keyof NotificationPrefs> = {
  dry_off: 'dryOff',
  breeding_due: 'readyToBreed',
  open: 'needsDecision',
};

/** True when the user still wants to see this notification type in-app. */
export function notificationTypeEnabled(
  type: string,
  prefs: NotificationPrefs,
): boolean {
  const topic = TOPIC_FOR_TYPE[type as NotificationType];
  // An unrecognized type is shown, never hidden: a notification the app does
  // not know about is exactly the one nobody should be quietly denied.
  return topic === undefined ? true : prefs[topic];
}

interface SettingsState {
  notifications: NotificationPrefs;
  hapticsEnabled: boolean;
  /** Hydration flag so the UI can wait for persisted values */
  _hydrated: boolean;
  setNotificationPref: (key: keyof NotificationPrefs, value: boolean) => void;
  setHaptics: (value: boolean) => void;
}

const DEFAULT_NOTIFICATIONS: NotificationPrefs = {
  dryOff: true,
  readyToBreed: true,
  needsDecision: true,
};

export const useSettingsStore = create<SettingsState>()(
  persist(
    (set) => ({
      notifications: DEFAULT_NOTIFICATIONS,
      hapticsEnabled: true,
      _hydrated: false,
      setNotificationPref: (key, value) =>
        set((s) => ({ notifications: { ...s.notifications, [key]: value } })),
      setHaptics: (value) => set({ hapticsEnabled: value }),
    }),
    {
      name: 'majordairy-settings',
      storage: createJSONStorage(() => AsyncStorage),
      partialize: (s) => ({ notifications: s.notifications, hapticsEnabled: s.hapticsEnabled }),
      /**
       * v1 stored {dryOff, calving, heat, pregnancyCheck, tasks}. Without a
       * migration, persist merges that over the new defaults and the two new
       * keys arrive `undefined` — which reads as "off", so anyone upgrading
       * would silently stop seeing two thirds of their notifications and have
       * no toggle to explain it.
       *
       * dryOff is the one topic that survived, so it carries across; the rest
       * were never wired to anything, so there is no real preference to
       * preserve and the new topics start on.
       */
      version: 2,
      migrate: (persisted: any, from: number) => {
        if (from >= 2) return persisted;
        const old = persisted?.notifications ?? {};
        return {
          ...persisted,
          notifications: {
            dryOff: typeof old.dryOff === 'boolean' ? old.dryOff : true,
            readyToBreed: true,
            needsDecision: true,
          },
        };
      },
      onRehydrateStorage: () => (state) => {
        if (state) state._hydrated = true;
      },
    },
  ),
);
