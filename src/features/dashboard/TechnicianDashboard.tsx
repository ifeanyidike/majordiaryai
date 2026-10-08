import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import React, { useEffect } from 'react';
import { StyleSheet, View } from 'react-native';
import {
  HeroHeader,
  IconCircle,
  PressableScale,
  Screen,
  Text,
  FocusedStatusBar,
} from '@/components';
import { colors, gradients, onDark, radius, shadows, spacing, tileTone, TileTone } from '@/theme';
import {
  farmsToVisit, unreadNotificationCount, useAppStore, worklistTotal,
} from '@/store/useAppStore';
import { useAuthStore } from '@/store/useAuthStore';

type IconName = keyof typeof Ionicons.glyphMap;

export function TechnicianDashboard() {
  const router = useRouter();
  const store = useAppStore();
  const unread = unreadNotificationCount(store);
  const { user, signOut } = useAuthStore();
  const today = new Date().toLocaleDateString('en-CA', {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
  });
  // Both figures come from the work list itself, so this caption and the To-Do
  // screen it links to always agree. "Farms" here means farms on today's route,
  // not every farm assigned to the technician.
  // Was hardcoded "Good morning", which read as a bug at 8pm — the first
  // words on the technician's home screen, every evening visit.
  const hour = new Date().getHours();
  const greeting =
    hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening';

  const route = farmsToVisit(store);
  const outstanding = worklistTotal(store);
  const alarms = store.unreadMessages.alarm;
  const officeAlerts = store.unreadMessages.office_alert;

  // Both badges in one call, so the two feed cards can show what is waiting
  // without pulling either feed.
  const { fetchUnreadMessageCounts } = store;
  useEffect(() => { fetchUnreadMessageCounts(); }, []);

  // The four the client asked for, verbatim: "Reports and Cow Search to
  // remove, and replace it with alarms and office alerts." Reports is reached
  // through a farm now, which is where per-farm reports belong.
  //
  // NOTE: /cow-search is left in the router but no longer linked from
  // anywhere. Raised with the client — finding a cow whose farm you cannot
  // remember has no other route in the app.
  const mainActions: {
    label: string; caption: string; icon: IconName; tone: TileTone; badge?: number;
    onPress: () => void;
  }[] = [
    // "All" matters: the hero above shows farms on TODAY'S route, and on a day
    // when every farm is scheduled the two numbers are identical. Without a
    // qualifier the pair reads as the same statistic printed twice.
    { label: 'Farms CRM', tone: tileTone.farms, caption: `All ${store.farms.length} farms`, icon: 'business', onPress: () => router.push('/(tabs)/farms') },
    {
      label: 'Alarms',
      tone: tileTone.alarms,
      // Short enough to stay on one line, or this card grows taller than its neighbour.
      caption: alarms ? `${alarms} from the barn` : 'From the farms',
      icon: 'alert-circle',
      badge: alarms,
      onPress: () => router.push({ pathname: '/messages/[channel]', params: { channel: 'alarm' } }),
    },
    {
      label: 'Office Alerts',
      tone: tileTone.officeAlerts,
      caption: officeAlerts ? `${officeAlerts} from the office` : 'From the office',
      icon: 'briefcase',
      badge: officeAlerts,
      onPress: () => router.push({ pathname: '/messages/[channel]', params: { channel: 'office_alert' } }),
    },
    { label: 'To Do List', tone: tileTone.todo, caption: route.length ? `${route.length} farms · ${outstanding} cows` : 'All clear', icon: 'checkbox', onPress: () => router.push('/(tabs)/tasks') },
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
            {greeting},
          </Text>
          <Text variant="display" color={onDark.text}>
            {(user?.name ?? 'there').split(' ')[0]}
          </Text>
        </View>
      </HeroHeader>

      {/* Action cards overlapping the hero */}
      <View style={styles.body}>
        <View style={styles.grid}>
          {mainActions.map((a) => (
            <View key={a.label} style={styles.gridItem}>
              <PressableScale onPress={a.onPress} style={styles.actionCard}>
                <View>
                  <IconCircle name={a.icon} size={52} color={a.tone.fg} bg={a.tone.bg} />
                  {/* Unread count sits on the icon, not beside the label: two
                      of these four cards are feeds, and the number is the
                      reason to tap before the words are read. */}
                  {a.badge && a.badge > 0 ? (
                    <View style={styles.cardBadge}>
                      <Text variant="label" color={onDark.text}>
                        {a.badge > 99 ? '99+' : a.badge}
                      </Text>
                    </View>
                  ) : null}
                </View>
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
  cardBadge: {
    position: 'absolute',
    top: -4,
    right: -6,
    minWidth: 22,
    height: 22,
    borderRadius: 11,
    paddingHorizontal: 6,
    backgroundColor: colors.danger,
    alignItems: 'center',
    justifyContent: 'center',
    // Lifts the count clear of the icon circle behind it.
    borderWidth: 2,
    borderColor: colors.surface,
  },
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
