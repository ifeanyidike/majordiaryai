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
 * These are the `create_notification` calls in the backend
 * (services/status_engine.py) and nothing else. Kept as a const tuple so the
 * map below is exhaustive by construction, and pinned to the backend by
 * tests/test_migrations.py — the earlier version of this file was built from
 * the SCREEN'S ICON TABLE instead, which listed aspirational types nothing
 * had ever emitted, so four of the five toggles filtered nothing at all.
 */
export const NOTIFICATION_TYPES = [
  'dry_off',
  'breeding_due',
  'open',
  'calving',
  'preg_check',
  'self_inject',
] as const;
export type NotificationType = (typeof NOTIFICATION_TYPES)[number];

export interface NotificationPrefs {
  dryOff: boolean;
  readyToBreed: boolean;
  needsDecision: boolean;
  calving: boolean;
  pregChecks: boolean;
  selfInject: boolean;
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
    hint: "A cow was seen in heat and is on Today's Breed Report",
  },
  {
    key: 'needsDecision',
    label: 'Needs a breeding decision',
    hint: 'A cow went Open — finished a protocol, lost a pregnancy, or came of age',
  },
  {
    key: 'calving',
    label: 'Calving',
    hint: 'A cow calved and is Fresh — she goes back into the milking herd',
  },
  {
    key: 'pregChecks',
    label: 'Pregnancy checks due',
    hint: 'A cow reached day 30 since insemination and is due for her check',
  },
  {
    key: 'selfInject',
    label: 'Injections you give yourself',
    hint: 'Which cow needs which hormone, on a farm that does its own needling',
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
  calving: 'calving',
  preg_check: 'pregChecks',
  self_inject: 'selfInject',
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
  calving: true,
  pregChecks: true,
  selfInject: true,
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
       * Bump this version every time a key is ADDED to NotificationPrefs.
       *
       * persist merges what is stored over the defaults, so a key the stored
       * object does not have arrives `undefined` — and
       * `notificationTypeEnabled` reads `undefined` as OFF. An upgrading
       * device therefore stops seeing the new notifications and has a toggle
       * that says they are on. It is invisible on a fresh install, which is
       * where anyone would look.
       *
       * v1 stored {dryOff, calving, heat, pregnancyCheck, tasks}, of which
       * only dryOff was ever wired to anything — so that is the one real
       * preference to carry across, and every later topic starts on.
       */
      version: 3,
      migrate: (persisted: any, from: number) => {
        const old = persisted?.notifications ?? {};
        // Every key must be filled in, not just the ones a given version
        // added. An absent key reads as `undefined`, which
        // `notificationTypeEnabled` treats as OFF — so adding calving,
        // pregnancy-check and self-inject to the interface WITHOUT bumping
        // the version silently hid all three on every device that already had
        // the app. They would have been visible only on a fresh install,
        // which is exactly where nobody would think to look for the bug.
        const keep = (value: unknown) => (typeof value === 'boolean' ? value : true);
        return {
          ...persisted,
          notifications: {
            // v1 wired only dryOff to anything, so it is the only stored
            // preference from before v2 worth carrying across.
            dryOff: keep(old.dryOff),
            readyToBreed: from >= 2 ? keep(old.readyToBreed) : true,
            needsDecision: from >= 2 ? keep(old.needsDecision) : true,
            calving: keep(old.calving),
            pregChecks: keep(old.pregChecks),
            selfInject: keep(old.selfInject),
          },
        };
      },
      onRehydrateStorage: () => (state) => {
        if (state) state._hydrated = true;
      },
    },
  ),
);
