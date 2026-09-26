import Constants from 'expo-constants';
import * as Device from 'expo-device';
import * as Notifications from 'expo-notifications';
import { Platform } from 'react-native';
import { api, isApiConfigured } from '@/lib/api';

/**
 * Push notifications for Alarms and Office Alerts.
 *
 * Both used to be in-app only, so an owner raising "the cow in pen 4 is down"
 * reached the technician whenever he next opened the app. This registers the
 * device with the API so a new message can wake it, and creates the Android
 * channels the server addresses by name.
 *
 * Everything here fails SOFT. A phone without permission, a simulator, or a
 * build with no Firebase project connected simply gets no token — the app
 * works exactly as before and the messages are still in the feeds.
 */

// The server addresses these by id (services/push.py CHANNEL_FOR). An alarm
// is loud; an office alert is ordinary.
const CHANNELS: { id: string; name: string; importance: Notifications.AndroidImportance }[] = [
  { id: 'alarms', name: 'Alarms', importance: Notifications.AndroidImportance.MAX },
  { id: 'office-alerts', name: 'Office Alerts', importance: Notifications.AndroidImportance.DEFAULT },
];

// Show the alert even when the app is open — otherwise an alarm that arrives
// while he is looking at the To-Do list is swallowed silently.
Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowBanner: true,
    shouldShowList: true,
    shouldPlaySound: true,
    shouldSetBadge: false,
  }),
});

let registeredToken: string | null = null;

async function ensureChannels(): Promise<void> {
  if (Platform.OS !== 'android') return;
  for (const c of CHANNELS) {
    await Notifications.setNotificationChannelAsync(c.id, {
      name: c.name,
      importance: c.importance,
      sound: 'default',
      vibrationPattern: c.id === 'alarms' ? [0, 400, 200, 400] : undefined,
    });
  }
}

/**
 * Ask for permission (once), get this device's Expo push address and give it
 * to the API. Safe to call on every start: the server treats it as an upsert,
 * and a token that moved to a new person follows them.
 */
export async function registerForPush(): Promise<void> {
  if (!isApiConfigured) return;
  try {
    await ensureChannels();

    // Permission first, on every device. Whether the user allows alerts has
    // nothing to do with being a physical phone — and asking on a simulator
    // is what lets a simulated alarm (`xcrun simctl push`) actually appear.
    const current = await Notifications.getPermissionsAsync();
    let granted = current.granted;
    if (!granted && current.canAskAgain) {
      granted = (await Notifications.requestPermissionsAsync()).granted;
    }
    if (!granted) return;

    // Only the push ADDRESS needs real hardware: Expo cannot issue a token to
    // a simulator or emulator.
    if (!Device.isDevice) return;

    const projectId =
      Constants.expoConfig?.extra?.eas?.projectId ?? Constants.easConfig?.projectId;
    const { data: token } = await Notifications.getExpoPushTokenAsync({ projectId });
    await api.post('/users/me/push-token', { token, platform: Platform.OS });
    registeredToken = token;
  } catch (e) {
    // Most often: an Android build with no Firebase project connected, where
    // no token can be issued at all. Not fatal — the feeds still work.
    console.warn('Push registration unavailable:', (e as Error)?.message ?? e);
  }
}

/**
 * Sign-out: this device stops waking for the account leaving it. Must run
 * BEFORE the session is cleared, because the request needs its token.
 */
export async function unregisterPush(): Promise<void> {
  const token = registeredToken;
  registeredToken = null;
  if (!token || !isApiConfigured) return;
  try {
    await api.delete('/users/me/push-token', { token });
  } catch {
    // Best effort. If it fails, the next person to sign in on this phone
    // re-registers it, which moves the token to them anyway.
  }
}
