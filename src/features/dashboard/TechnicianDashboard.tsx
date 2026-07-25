import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import React from 'react';
import { StyleSheet, View } from 'react-native';
import {
  HeroHeader,
  HeroStats,
  IconCircle,
  PressableScale,
  Screen,
  Text,
  FocusedStatusBar,
} from '@/components';
import { colors, gradients, onDark, radius, shadows, spacing } from '@/theme';
import { summarize, unreadNotificationCount, useAppStore } from '@/store/useAppStore';
import { useAuthStore } from '@/store/useAuthStore';

type IconName = keyof typeof Ionicons.glyphMap;

export function TechnicianDashboard() {
  const router = useRouter();
  const store = useAppStore();
  const { farms, tasks, cows } = store;
  const unread = unreadNotificationCount(store);
  const { user, signOut } = useAuthStore();
  const today = new Date().toLocaleDateString('en-CA', {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
  });
  const summary = summarize(cows);
  const pendingTasks = tasks.filter((t) => t.status !== 'done').length;
  const doneTasks = tasks.length - pendingTasks;

  const heroStats = [
    { value: farms.length, label: 'Farms' },
    { value: pendingTasks, label: 'Tasks left' },
    { value: summary.total, label: 'Cows' },
  ];

  const mainActions: { label: string; caption: string; icon: IconName; onPress: () => void }[] = [
    { label: 'Farms CRM', caption: `${farms.length} farms`, icon: 'business', onPress: () => router.push('/(tabs)/farms') },
    { label: 'To Do List', caption: `${doneTasks}/${tasks.length} done`, icon: 'checkbox', onPress: () => router.push('/(tabs)/tasks') },
    { label: 'Reports', caption: `${summary.total} cows tracked`, icon: 'bar-chart', onPress: () => router.push('/(tabs)/reports') },
    { label: 'Cow Search', caption: 'Find any cow', icon: 'search', onPress: () => router.push('/cow-search') },
  ];

  const quickLinks: { label: string; icon: IconName; badge?: number; onPress: () => void }[] = [
    { label: 'Notifications', icon: 'notifications-outline', badge: unread, onPress: () => router.push('/notifications') },
    { label: 'Settings', icon: 'settings-outline', onPress: () => router.push('/settings') },
    { label: 'My Profile', icon: 'person-outline', onPress: () => router.push('/(tabs)/profile') },
    {
      label: 'Logout',
      icon: 'log-out-outline',
      onPress: async () => {
        await signOut();
        router.replace('/');
      },
    },
  ];

  return (
    <Screen padded={false} topInset={false}>
      <FocusedStatusBar style="light" />
      {/* Command-center hero */}
      <HeroHeader gradient={gradients.primary}>
        <View>
          <Text variant="caption" color={onDark.textSecondary}>
            {today}
          </Text>
          <Text variant="display" color={onDark.text}>
            Good morning,
          </Text>
          <Text variant="display" color={onDark.text}>
            {(user?.name ?? 'there').split(' ')[0]}
          </Text>
        </View>

        <HeroStats tone="scrim" items={heroStats} style={styles.heroStats} />
      </HeroHeader>

      {/* Action cards overlapping the hero */}
      <View style={styles.body}>
        <View style={styles.grid}>
          {mainActions.map((a) => (
            <View key={a.label} style={styles.gridItem}>
              <PressableScale onPress={a.onPress} style={styles.actionCard}>
                <IconCircle name={a.icon} size={52} />
                <View>
                  <Text variant="heading">{a.label}</Text>
                  <Text variant="caption" color={colors.textSecondary}>
                    {a.caption}
                  </Text>
                </View>
              </PressableScale>
            </View>
          ))}
        </View>

        <View style={styles.links}>
          {quickLinks.map((l, i) => (
            <PressableScale
              key={l.label}
              onPress={l.onPress}
              style={[styles.linkRow, i === quickLinks.length - 1 && styles.linkRowLast]}
              scaleTo={0.98}
            >
              <Ionicons
                name={l.icon}
                size={22}
                color={l.label === 'Logout' ? colors.danger : colors.textSecondary}
              />
              <Text
                variant="subheading"
                color={l.label === 'Logout' ? colors.danger : colors.text}
                style={styles.linkLabel}
              >
                {l.label}
              </Text>
              {l.badge && l.badge > 0 ? (
                <View style={styles.badge}>
                  <Text variant="label" color={colors.textOnPrimary}>
                    {l.badge > 99 ? '99+' : l.badge}
                  </Text>
                </View>
              ) : null}
              <Ionicons name="chevron-forward" size={16} color={colors.textMuted} />
            </PressableScale>
          ))}
        </View>
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  heroStats: {
    marginTop: spacing.xxl,
  },
  body: {
    paddingHorizontal: spacing.xl,
    marginTop: -spacing.xxxl,
  },
  grid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.md,
  },
  gridItem: { width: '47%', flexGrow: 1 },
  actionCard: {
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.xl,
    gap: spacing.lg,
    minHeight: 150,
    justifyContent: 'space-between',
    ...shadows.raised,
  },
  links: {
    marginTop: spacing.xxl,
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    paddingHorizontal: spacing.lg,
    ...shadows.card,
  },
  linkRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    paddingVertical: spacing.lg,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.border,
  },
  linkRowLast: { borderBottomWidth: 0 },
  linkLabel: { flex: 1 },
  badge: {
    minWidth: 22,
    height: 22,
    borderRadius: 11,
    paddingHorizontal: 6,
    backgroundColor: colors.primary,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
