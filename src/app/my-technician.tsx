import { useRouter } from 'expo-router';
import React from 'react';
import { StyleSheet, View } from 'react-native';
import Animated from 'react-native-reanimated';
import {
  Button, Card, EmptyState, FocusedStatusBar, Header, HeroHeader, InfoRow, Monogram, Screen,
  SectionHeader, Text,
} from '@/components';
import { colors, gradients, onDark, spacing, useMotion } from '@/theme';
import { dial, emailTo } from '@/lib/contact';
import { useAppStore } from '@/store/useAppStore';
import { useAuthStore } from '@/store/useAuthStore';

/**
 * The farm's own technician, opened from the farm home (Josh's change
 * requests, Nov 20): a limited profile with their details, how to contact
 * them, and a way to send them a note or an alarm.
 */
export default function MyTechnicianScreen() {
  const motion = useMotion();
  const router = useRouter();
  const role = useAuthStore((s) => s.user?.role);
  const farm = useAppStore((s) => s.farms[0]);

  if (role !== 'farm' || !farm?.assignedTechnician) {
    return (
      <Screen>
        <Header back title="Your Technician" />
        <EmptyState icon="construct-outline" title="No technician yet"
                    message="The office has not given your farm a technician yet." />
      </Screen>
    );
  }
  const name = farm.assignedTechnician;
  const phone = farm.assignedTechnicianPhone;
  const email = farm.assignedTechnicianEmail;
  // To this technician by name ("send them a note or an alarm"), even on a
  // day someone else covers the farm.
  const write = (kind: 'note' | 'alarm') =>
    router.push({
      pathname: '/messages/compose',
      params: { channel: 'alarm', kind, to: farm.assignedTechnicianId ?? '', toName: name },
    });

  return (
    <Screen padded={false} topInset={false}>
      <FocusedStatusBar style="light" />
      <HeroHeader gradient={gradients.charcoal} back>
        <Animated.View entering={motion.downAt(0, 500)} style={styles.heroRow}>
          <Monogram name={name} size={64} bg={onDark.panelBorder} color={colors.cream.base} />
          <View style={styles.heroText}>
            <Text variant="title" color={onDark.text}>{name}</Text>
            <Text variant="caption" color={onDark.textSecondary}>
              Reproduction Technician · {farm.name}
            </Text>
          </View>
        </Animated.View>
        {phone || email ? (
          <Animated.View entering={motion.downAt(120, 500)} style={styles.heroActions}>
            {phone ? (
              <Button label="Call" icon="call" variant="onDark" compact style={styles.flex1}
                      onPress={() => dial(phone)} />
            ) : null}
            {email ? (
              <Button label="Email" icon="mail" variant="onDark" compact style={styles.flex1}
                      onPress={() => emailTo(email)} />
            ) : null}
          </Animated.View>
        ) : null}
      </HeroHeader>

      <View style={styles.body}>
        <SectionHeader title="Contact" />
        <Card style={styles.card}>
          <InfoRow label="Phone" value={phone ?? '—'} />
          <InfoRow label="Email" value={email ?? '—'} />
        </Card>

        <SectionHeader title="Send them" />
        <View style={styles.sendRow}>
          <Button variant="secondary" label="A note" icon="chatbubble-ellipses-outline"
                  style={styles.flex1} onPress={() => write('note')} />
          <Button label="An alarm" icon="alert-circle" style={styles.flex1}
                  onPress={() => write('alarm')} />
        </View>
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  heroRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.lg },
  heroText: { flex: 1, gap: spacing.hairline },
  heroActions: { flexDirection: 'row', gap: spacing.md, marginTop: spacing.xxl },
  flex1: { flex: 1 },
  body: { paddingHorizontal: spacing.xl, paddingBottom: spacing.huge },
  card: { paddingVertical: spacing.sm },
  sendRow: { flexDirection: 'row', gap: spacing.md },
});
