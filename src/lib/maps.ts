import { Linking, Platform } from 'react-native';

/** Join address parts, skipping missing ones (all are optional on Farm). */
export function formatAddress(...parts: (string | null | undefined)[]): string {
  return parts.map((p) => p?.trim()).filter(Boolean).join(', ');
}

/** Open the platform-native maps app for an address (geo: on Android, Apple Maps on iOS). */
export function openDirections(address: string) {
  if (!address.trim()) return;
  const q = encodeURIComponent(address);
  const url = Platform.select({
    android: `geo:0,0?q=${q}`,
    default: `https://maps.apple.com/?daddr=${q}`,
  });
  Linking.openURL(url).catch(() => {
    Linking.openURL(`https://www.google.com/maps/search/?api=1&query=${q}`);
  });
}
