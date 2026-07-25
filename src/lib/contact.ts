import { Linking } from 'react-native';
import { useToast } from '@/components/Toast';

/**
 * Place a phone call. Falls back to a toast showing the number when the device
 * can't dial (e.g. the iOS Simulator has no Phone app) — instead of an uncaught
 * promise rejection.
 */
export function dial(phone: string) {
  const num = phone.replace(/[^+\d]/g, '');
  Linking.openURL(`tel:${num}`).catch(() =>
    useToast.getState().show(`Can't place a call here · ${phone}`, 'call'),
  );
}

/** Open an email draft, falling back to a toast showing the address. */
export function emailTo(address: string) {
  Linking.openURL(`mailto:${address}`).catch(() =>
    useToast.getState().show(`Can't open mail here · ${address}`, 'mail'),
  );
}
