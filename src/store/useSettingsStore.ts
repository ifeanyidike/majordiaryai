import AsyncStorage from '@react-native-async-storage/async-storage';
import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';

/**
 * Local, device-persisted app preferences. These gate which in-app
 * notifications the user cares about and general app behavior. No server
 * round-trip — they live on the device via AsyncStorage.
 */
export interface NotificationPrefs {
  dryOff: boolean;
  calving: boolean;
  heat: boolean;
  pregnancyCheck: boolean;
  tasks: boolean;
}

export const NOTIFICATION_TOPICS: { key: keyof NotificationPrefs; label: string; hint: string }[] = [
  { key: 'dryOff', label: 'Dry-off reminders', hint: 'Cows reaching day 223 — time to change pen' },
  { key: 'calving', label: 'Calvings', hint: 'Fresh events and upcoming due dates' },
  { key: 'heat', label: 'Heat detection', hint: 'Cows entering the 20–25 day heat window' },
  { key: 'pregnancyCheck', label: 'Pregnancy checks', hint: 'Cows due for a vet pregnancy check' },
  { key: 'tasks', label: 'Daily tasks', hint: 'New needling, breeding and vaccination tasks' },
];

/**
 * Which server notification types each toggle covers.
 *
 * The toggles persisted a preference nothing ever read: switching off
 * "Dry-off reminders" changed nothing at all. This is the mapping that makes
 * them mean something — a type absent from the table is never hidden, so a
 * new notification type is visible by default rather than silently
 * suppressed by a toggle that predates it.
 */
const TOPIC_FOR_TYPE: Record<string, keyof NotificationPrefs> = {
  dry_off: 'dryOff',
  calving: 'calving',
  fresh: 'calving',
  heat: 'heat',
  pregnancy: 'pregnancyCheck',
  breeding: 'tasks',
  vaccination: 'tasks',
};

/** True when the user still wants to see this notification type in-app. */
export function notificationTypeEnabled(
  type: string,
  prefs: NotificationPrefs,
): boolean {
  const topic = TOPIC_FOR_TYPE[type];
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
  calving: true,
  heat: true,
  pregnancyCheck: true,
  tasks: true,
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
      onRehydrateStorage: () => (state) => {
        if (state) state._hydrated = true;
      },
    },
  ),
);
