import { useLocalSearchParams, useRouter } from 'expo-router';
import React, { useEffect } from 'react';
import { StyleSheet, View } from 'react-native';
import Animated from 'react-native-reanimated';
import {
  Button, Card, EmptyState, FocusedStatusBar, Header, HeroHeader, InfoRow, ListRow, Monogram,
  Screen, SectionHeader, Text,
} from '@/components';
import { colors, gradients, onDark, spacing, useMotion } from '@/theme';
import { dial } from '@/lib/contact';
import { farmsOnRoute, staffById, useAppStore } from '@/store/useAppStore';
import { useAuthStore } from '@/store/useAuthStore';

/** Admin, Technicians: one technician — their details and the farms on their route. */
export default function TechnicianProfileScreen() {
  const motion = useMotion();
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const state = useAppStore();

  useEffect(() => {
    if (state.staff.length === 0) state.fetchStaff();
    if (state.farms.length === 0) state.fetchFarms();
  }, []);

  const role = useAuthStore((s) => s.user?.role);
  const tech = staffById(state, id);
  if (role !== 'admin') {
    return (
      <Screen>
        <Header back title="Technician" />
        <EmptyState icon="lock-closed-outline" title="Admins only"
                    message="Technicians are managed by an administrator." />
      </Screen>
    );
  }
  if (!tech) {
    return (
      <Screen>
        <Header back title="Technician" />
        <EmptyState title={state.staffLoading ? 'Loading…' : 'Technician not found'} />
      </Screen>
    );
  }
  const farms = farmsOnRoute(state, tech.id);

  return (
    <Screen padded={false} topInset={false}>
      <FocusedStatusBar style="light" />
      <HeroHeader gradient={gradients.charcoal} back>
        <Animated.View entering={motion.downAt(0, 500)} style={styles.heroRow}>
          <Monogram name={tech.name} size={64} bg={onDark.panelBorder} color={colors.cream.base} />
          <View style={styles.heroText}>
            <Text variant="title" color={onDark.text}>{tech.name}</Text>
            <Text variant="caption" color={onDark.textSecondary}>
              {tech.isActive ? 'Technician' : 'Technician · waiting for approval under People'}
            </Text>
          </View>
        </Animated.View>
        {tech.phone ? (
          <Animated.View entering={motion.downAt(120, 500)} style={styles.heroActions}>
            <Button label="Call" icon="call" variant="onDark" compact style={styles.flex1}
                    onPress={() => dial(tech.phone!)} />
          </Animated.View>
        ) : null}
      </HeroHeader>

      <View style={styles.body}>
        <SectionHeader title="Details" />
        <Card style={styles.card}>
          <InfoRow label="Email" value={tech.email} />
          <InfoRow label="Phone" value={tech.phone ?? '—'} />
          <InfoRow label="Employee ID" value={tech.employeeId ?? '—'} />
          <InfoRow label="Region" value={tech.region ?? '—'} />
        </Card>

        <SectionHeader title={`Route · ${farms.length} ${farms.length === 1 ? 'farm' : 'farms'}`} />
        {farms.length === 0 ? (
          <Card style={styles.card}>
            <Text variant="body" color={colors.textMuted}>No farms on this route.</Text>
          </Card>
        ) : (
          farms.map((f) => (
            <ListRow
              key={f.id}
              icon="business"
              iconColor={colors.primary}
              iconBg={colors.primarySoft}
              title={f.name}
              subtitle={[f.city, f.province].filter(Boolean).join(', ')}
              onPress={() => router.push({ pathname: '/farm/[id]', params: { id: f.id } })}
            />
          ))
        )}

        <View style={styles.footer}>
          <Button compact variant="secondary" label="Edit" icon="create-outline" style={styles.footerBtn}
                  onPress={() => router.push({ pathname: '/technician/edit', params: { id: tech.id } })} />
          <Button compact variant="secondary" label="Reassign farms" icon="swap-horizontal"
                  style={styles.footerBtn}
                  onPress={() => router.push({ pathname: '/route/[id]', params: { id: tech.id } })} />
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
  footer: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm, marginTop: spacing.md },
  footerBtn: { flexGrow: 1, flexBasis: '45%', minWidth: 140 },
});
