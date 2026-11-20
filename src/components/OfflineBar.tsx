import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import React from 'react';
import { Pressable, StyleSheet } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { colors, radius, shadows, spacing } from '@/theme';
import { useNet } from '@/lib/net';
import { useOutbox } from '@/lib/outbox';
import { useAppStore } from '@/store/useAppStore';
import { useAuthStore } from '@/store/useAuthStore';
import { Text } from './Text';

/** "10:42" today, "19 Nov 17:40" before today. */
export function syncedLabel(at: number | null): string {
  if (at == null) return 'not synced yet';
  const d = new Date(at);
  const time = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  if (d.toDateString() === new Date().toDateString()) return time;
  return `${d.toLocaleDateString([], { day: 'numeric', month: 'short' })} ${time}`;
}

/**
 * Offline mode, on every screen (Josh's Part A platform tests: "The app opens
 * offline and shows when it last synced"). Shown only when there is something
 * to say: no signal, saves waiting, or saves the server refused. Tapping it
 * opens the Sync screen.
 */
export function OfflineBar() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const online = useNet((s) => s.online);
  const userId = useAuthStore((s) => s.user?.id);
  const lastSyncedAt = useAppStore((s) => s.lastSyncedAt);
  const items = useOutbox((s) => s.items);
  const syncing = useOutbox((s) => s.syncing);
  if (!userId) return null;

  const mine = items.filter((i) => i.userId === userId);
  const waiting = mine.filter((i) => !i.failed).length;
  const failed = mine.length - waiting;
  const plural = (n: number) => `${n} ${n === 1 ? 'record' : 'records'}`;

  let text: string | null = null;
  let tone: string = colors.text;
  let icon: keyof typeof Ionicons.glyphMap = 'cloud-offline';
  if (!online) {
    text = `No signal · last synced ${syncedLabel(lastSyncedAt)}`
      + (waiting ? ` · ${plural(waiting)} waiting` : '');
  } else if (failed) {
    text = `${plural(failed)} could not be saved — tap to see`;
    tone = colors.danger;
    icon = 'alert-circle';
  } else if (waiting) {
    text = syncing ? `Syncing ${plural(waiting)}…` : `${plural(waiting)} waiting to sync`;
    icon = 'cloud-upload';
  }
  if (!text) return null;

  return (
    <Pressable
      onPress={() => router.push('/sync')}
      style={[styles.bar, { bottom: insets.bottom + 72 }]}
      accessibilityRole="button"
      accessibilityLabel={text}
    >
      <Ionicons name={icon} size={16} color={tone} />
      <Text variant="caption" color={tone} numberOfLines={1} style={styles.text}>{text}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  bar: {
    position: 'absolute', alignSelf: 'center', maxWidth: '92%',
    flexDirection: 'row', alignItems: 'center', gap: spacing.xs,
    paddingHorizontal: spacing.md, paddingVertical: spacing.sm,
    backgroundColor: colors.surface, borderRadius: radius.pill,
    borderWidth: 1, borderColor: colors.border, ...shadows.raised,
  },
  text: { flexShrink: 1 },
});
