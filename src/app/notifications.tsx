import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import React, { useEffect, useMemo } from 'react';
import { ActivityIndicator, FlatList, Pressable, RefreshControl, StyleSheet, View } from 'react-native';
import { EmptyState, Header, Screen, Text } from '@/components';
import { colors, radius, spacing, status } from '@/theme';
import { daysSince } from '@/lib/dates';
import { AppNotification, useAppStore } from '@/store/useAppStore';
import { notificationTypeEnabled, useSettingsStore } from '@/store/useSettingsStore';

/** Notification type → icon + accent, drawn from the semantic status palette. */
const TYPE_META: Record<string, { icon: keyof typeof Ionicons.glyphMap; color: string }> = {
  dry_off:        { icon: 'moon', color: status.dry.fg },
  calving:        { icon: 'heart', color: status.fresh.fg },
  fresh:          { icon: 'heart', color: status.fresh.fg },
  open:           { icon: 'ellipse-outline', color: status.open.fg },
  heat:           { icon: 'flame', color: status.heat.fg },
  pregnancy:      { icon: 'medkit', color: status.pregnant.fg },
  breeding:       { icon: 'flask', color: status.inseminated.fg },
  vaccination:    { icon: 'shield-checkmark', color: status.fresh.fg },
};

function metaFor(type: string) {
  return TYPE_META[type] ?? { icon: 'notifications' as const, color: colors.primary };
}

function relativeTime(iso: string): string {
  if (!iso) return '';
  const d = daysSince(iso);
  if (d === 0) return 'Today';
  if (d === 1) return 'Yesterday';
  if (d < 7) return `${d} days ago`;
  return new Date(iso).toLocaleDateString('en-CA', { month: 'short', day: 'numeric' });
}

export default function NotificationsScreen() {
  const router = useRouter();
  const {
    notifications: allNotifications, notificationsLoading, farms,
    fetchNotifications, markNotificationRead,
  } = useAppStore();
  const prefs = useSettingsStore((s) => s.notifications);

  useEffect(() => { fetchNotifications(); }, []);

  // Settings' notification toggles used to write to a store nothing read, so
  // switching a topic off changed nothing. This is the list they control.
  const notifications = useMemo(
    () => allNotifications.filter((n) => notificationTypeEnabled(n.type, prefs)),
    [allNotifications, prefs],
  );
  const hiddenCount = allNotifications.length - notifications.length;

  const farmName = (id: string) => farms.find((f) => f.id === id)?.name;

  const onPress = (n: AppNotification) => {
    if (!n.read) markNotificationRead(n.id);
    if (n.cowId) router.push({ pathname: '/cow/[id]', params: { id: n.cowId } });
    else if (n.farmId) router.push({ pathname: '/farm/[id]', params: { id: n.farmId } });
  };

  const unread = notifications.filter((n) => !n.read).length;

  return (
    <Screen scroll={false} padded={false}>
      <FlatList
        data={notifications}
        keyExtractor={(n) => n.id}
        contentContainerStyle={{ paddingHorizontal: spacing.xl, paddingBottom: spacing.huge }}
        refreshControl={
          <RefreshControl
            refreshing={notificationsLoading}
            onRefresh={fetchNotifications}
            tintColor={colors.primary}
            colors={[colors.primary]}
          />
        }
        ListHeaderComponent={
          <>
            <Header
              back
              title="Notifications"
              subtitle={unread > 0 ? `${unread} unread` : 'All caught up'}
            />
            {notificationsLoading && notifications.length === 0 ? (
              <ActivityIndicator color={colors.primary} style={{ marginTop: spacing.xxl }} />
            ) : null}
            {hiddenCount > 0 ? (
              <Pressable onPress={() => router.push('/settings')} style={styles.hiddenNote}>
                <Ionicons name="filter" size={14} color={colors.textSecondary} />
                <Text variant="caption" color={colors.textSecondary}>
                  {hiddenCount} hidden by your notification settings
                </Text>
              </Pressable>
            ) : null}
          </>
        }
        ListEmptyComponent={
          notificationsLoading ? null : (
            <EmptyState
              icon="notifications-off-outline"
              title="No notifications"
              message="Program events like dry-offs and calvings will show up here."
            />
          )
        }
        renderItem={({ item: n }) => {
          const meta = metaFor(n.type);
          return (
            <Pressable
              onPress={() => onPress(n)}
              style={[styles.row, !n.read && styles.rowUnread]}
              accessibilityRole="button"
              accessibilityLabel={n.message}
            >
              <View style={[styles.iconWrap, { backgroundColor: `${meta.color}1A` }]}>
                <Ionicons name={meta.icon} size={20} color={meta.color} />
              </View>
              <View style={styles.body}>
                <Text variant="body" numberOfLines={3}>
                  {n.message}
                </Text>
                <Text variant="caption" color={colors.textMuted}>
                  {[farmName(n.farmId), relativeTime(n.createdAt)].filter(Boolean).join(' · ')}
                </Text>
              </View>
              {!n.read ? <View style={styles.dot} /> : null}
            </Pressable>
          );
        }}
      />
    </Screen>
  );
}

const styles = StyleSheet.create({
  hiddenNote: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    marginBottom: spacing.md,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: spacing.md,
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.lg,
    marginBottom: spacing.sm + 2,
  },
  rowUnread: {
    borderColor: colors.primary,
    backgroundColor: colors.primarySoft,
  },
  iconWrap: {
    width: 40,
    height: 40,
    borderRadius: radius.pill,
    alignItems: 'center',
    justifyContent: 'center',
  },
  body: { flex: 1, gap: 3 },
  dot: {
    width: 9,
    height: 9,
    borderRadius: 5,
    backgroundColor: colors.primary,
    marginTop: 6,
  },
});
