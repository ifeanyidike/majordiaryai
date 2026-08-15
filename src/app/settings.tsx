import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import React, { useState } from 'react';
import { Linking, StyleSheet, Switch, View } from 'react-native';
import Constants from 'expo-constants';
import {
  Button, Card, Header, PressableScale, Screen, SectionHeader, Text,
} from '@/components';
import { colors, radius, spacing } from '@/theme';
import { NOTIFICATION_TOPICS, useSettingsStore } from '@/store/useSettingsStore';
import { useAuthStore } from '@/store/useAuthStore';

/**
 * Where support mail goes.
 *
 * It was hardcoded to help@majordairy.ai, a domain with no MX record, so the
 * row opened a composer addressed to a mailbox that cannot receive anything
 * and the send bounced silently some time later.
 *
 * The default is a real mailbox rather than null: a release build that forgot
 * one EAS variable would otherwise ship with no way to contact anybody, and
 * that failure is invisible until a user needs help. The env var is still
 * honoured so the client can point it at their own inbox without a rebuild
 * of this file.
 */
const SUPPORT_EMAIL =
  process.env.EXPO_PUBLIC_SUPPORT_EMAIL?.trim() || 'majordiary@gmail.com';

function Row({
  icon, label, hint, right, onPress,
}: {
  icon: keyof typeof Ionicons.glyphMap;
  label: string;
  hint?: string;
  right?: React.ReactNode;
  onPress?: () => void;
}) {
  const content = (
    <>
      <Ionicons name={icon} size={20} color={colors.textSecondary} style={styles.rowIcon} />
      <View style={styles.rowText}>
        <Text variant="subheading">{label}</Text>
        {hint ? (
          <Text variant="caption" color={colors.textSecondary} numberOfLines={2}>
            {hint}
          </Text>
        ) : null}
      </View>
      {right ?? (onPress ? <Ionicons name="chevron-forward" size={18} color={colors.textMuted} /> : null)}
    </>
  );
  if (onPress) {
    return (
      <PressableScale
        scaleTo={0.98}
        style={styles.row}
        onPress={onPress}
        accessibilityRole="button"
        accessibilityLabel={label}
      >
        {content}
      </PressableScale>
    );
  }
  return <View style={styles.row}>{content}</View>;
}

export default function SettingsScreen() {
  const router = useRouter();
  const { user, signOut } = useAuthStore();
  const { notifications, setNotificationPref, hapticsEnabled, setHaptics } = useSettingsStore();
  const [signingOut, setSigningOut] = useState(false);

  const canImport = user?.role === 'admin' || user?.role === 'technician';
  const version = Constants.expoConfig?.version ?? '1.0.0';

  const handleLogout = async () => {
    setSigningOut(true);
    await signOut();
    router.replace('/');
  };

  return (
    <Screen>
      <Header back title="Settings" subtitle="Manage your account and preferences" />

      <SectionHeader title="Account" />
      <Card style={styles.card}>
        <Row
          icon="person-outline"
          label={user?.name ?? 'Your profile'}
          hint={user?.email}
          onPress={() => router.push('/edit-profile')}
        />
      </Card>

      <SectionHeader title="Notifications" />
      <Card style={styles.card}>
        {NOTIFICATION_TOPICS.map((t, i) => (
          <View key={t.key} style={i > 0 ? styles.divided : undefined}>
            <Row
              icon="notifications-outline"
              label={t.label}
              hint={t.hint}
              right={
                <Switch
                  value={notifications[t.key]}
                  onValueChange={(v) => setNotificationPref(t.key, v)}
                  trackColor={{ false: colors.cream.line, true: colors.primary }}
                  thumbColor={colors.cream.base}
                  accessibilityLabel={t.label}
                />
              }
            />
          </View>
        ))}
      </Card>

      <SectionHeader title="App" />
      <Card style={styles.card}>
        <Row
          icon="phone-portrait-outline"
          label="Haptic feedback"
          hint="Vibrate on taps and actions"
          right={
            <Switch
              value={hapticsEnabled}
              onValueChange={setHaptics}
              trackColor={{ false: colors.cream.line, true: colors.primary }}
              thumbColor={colors.cream.base}
              accessibilityLabel="Haptic feedback"
            />
          }
        />
        {canImport ? (
          <View style={styles.divided}>
            <Row
              icon="cloud-upload-outline"
              label="Import cows"
              hint="Upload a herd spreadsheet (Excel or CSV)"
              onPress={() => router.push('/import-cows')}
            />
          </View>
        ) : null}
        {user?.role === 'admin' ? (
          <View style={styles.divided}>
            <Row
              icon="people-outline"
              label="People"
              hint="Set roles and assign a farm manager to their farm"
              onPress={() => router.push('/users')}
            />
          </View>
        ) : null}
      </Card>

      <SectionHeader title="About" />
      <Card style={styles.card}>
        <Row
          icon="help-buoy-outline"
          label="Support"
          hint={SUPPORT_EMAIL}
          onPress={() => Linking.openURL(`mailto:${SUPPORT_EMAIL}`)}
        />
        <View style={styles.divided}>
          <Row icon="information-circle-outline" label="Version" right={
            <Text variant="body" color={colors.textSecondary}>{version}</Text>
          } />
        </View>
      </Card>

      <View style={styles.logout}>
        <Button
          variant="secondary"
          label="Sign Out"
          icon="log-out-outline"
          onPress={handleLogout}
          loading={signingOut}
        />
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  card: { paddingVertical: spacing.xs },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    paddingVertical: spacing.md,
    minHeight: 56,
  },
  rowIcon: { width: 24, textAlign: 'center' },
  rowText: { flex: 1, gap: spacing.hairline },
  divided: {
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.border,
  },
  logout: { marginTop: spacing.xl },
});
