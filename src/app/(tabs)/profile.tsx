import { useRouter } from 'expo-router';
import React, { useState } from 'react';
import { StyleSheet, View } from 'react-native';
import {
  Button,
  Card,
  HeroHeader,
  InfoRow,
  Monogram,
  Screen,
  SectionHeader,
  StatCard,
  Text,
  FocusedStatusBar,
} from '@/components';
import { colors, gradients, onDark, spacing, status } from '@/theme';
import { summarize, unreadNotificationCount, useAppStore } from '@/store/useAppStore';
import { useAuthStore } from '@/store/useAuthStore';

export default function ProfileScreen() {
  const router = useRouter();
  const { user, signOut } = useAuthStore();
  const store = useAppStore();
  const { tasks, farms, cows } = store;
  const unread = unreadNotificationCount(store);
  const [signingOut, setSigningOut] = useState(false);

  const role = user?.role ?? 'technician';
  const done = tasks.filter((t) => t.status === 'done').length;

  const gradient =
    role === 'admin' ? gradients.charcoal
    : role === 'farm' ? gradients.primary
    : role === 'vet' ? gradients.vet
    : gradients.charcoal;

  const caption =
    role === 'admin' ? 'System Administrator'
    : role === 'farm' ? 'Farm Manager'
    : role === 'vet' ? 'Veterinarian'
    : 'Field Technician';

  const contact = [
    { label: 'Email', value: user?.email ?? '—' },
    ...(user?.phone ? [{ label: 'Phone', value: user.phone }] : []),
    { label: 'Role', value: caption },
  ];

  const herdSummary = summarize(cows);
  const stats =
    role === 'admin'
      ? [
          { value: farms.length, label: 'Farms', accent: colors.primary },
          { value: herdSummary.total, label: 'Cows in System', accent: status.fresh.fg },
        ]
      : role === 'farm'
        ? [
            { value: herdSummary.total, label: 'Total Cows', accent: colors.primary },
            { value: herdSummary.pregnant, label: 'Pregnant', accent: status.pregnant.fg },
          ]
        : [
            { value: farms.length, label: 'Assigned Farms', accent: colors.primary },
            { value: `${done}/${tasks.length}`, label: 'Tasks Done', accent: status.pregnant.fg },
          ];

  const handleLogout = async () => {
    setSigningOut(true);
    await signOut();
    router.replace('/');
  };

  return (
    <Screen padded={false} topInset={false}>
      <FocusedStatusBar style="light" />
      <HeroHeader gradient={gradient}>
        <View style={styles.heroRow}>
          <Monogram
            name={user?.name ?? 'U'}
            size={72}
            bg={onDark.panelBorder}
            color={colors.cream.base}
          />
          <View style={styles.heroText}>
            <Text variant="title" color={onDark.text}>{user?.name ?? 'User'}</Text>
            <Text variant="caption" color={onDark.textSecondary}>{caption}</Text>
            <Text variant="caption" color={onDark.textSecondary}>{user?.email ?? ''}</Text>
          </View>
        </View>
      </HeroHeader>

      <View style={styles.body}>
        <View style={styles.statRow}>
          {stats.map((s) => (
            <StatCard key={s.label} value={s.value} label={s.label} accent={s.accent} />
          ))}
        </View>

        <SectionHeader title="Contact" />
        <Card style={styles.infoCard}>
          {contact.map((c) => (
            <InfoRow key={c.label} label={c.label} value={c.value} />
          ))}
        </Card>

        <SectionHeader title="Account" />
        <View style={styles.actions}>
          <Button
            variant="secondary"
            label="Settings"
            icon="settings-outline"
            onPress={() => router.push('/settings')}
          />
          <Button
            variant="secondary"
            label={unread > 0 ? `Notifications (${unread})` : 'Notifications'}
            icon="notifications-outline"
            onPress={() => router.push('/notifications')}
          />
          <Button label="Logout" icon="log-out-outline" onPress={handleLogout} loading={signingOut} />
        </View>
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  heroRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.lg },
  heroText: { flex: 1, gap: 2 },
  body: { paddingHorizontal: spacing.xl, marginTop: -spacing.xxxl },
  statRow: { flexDirection: 'row', gap: spacing.md },
  infoCard: { paddingVertical: spacing.sm },
  actions: { gap: spacing.md },
});
