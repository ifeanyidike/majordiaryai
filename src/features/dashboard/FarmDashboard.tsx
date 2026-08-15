import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import React, { useEffect } from 'react';
import { StyleSheet, View } from 'react-native';
import Animated from 'react-native-reanimated';
import {
  Button,
  Card,
  EmptyState,
  ErrorBanner,
  SkeletonList,
  Header,
  HeroHeader,
  IconCircle,
  Monogram,
  PressableScale,
  Screen,
  SectionHeader,
  StatCard,
  Text,
  useToast,
  FocusedStatusBar,
} from '@/components';
import { colors, gradients, onDark, radius, spacing, status, useMotion } from '@/theme';
import { dial } from '@/lib/contact';
import { farmUpcomingActivities, summarize, useAppStore } from '@/store/useAppStore';

const ACTIVITY_ICONS: Record<string, keyof typeof Ionicons.glyphMap> = {
  medkit: 'medkit',
  'shield-checkmark': 'shield-checkmark',
  heart: 'heart',
  walk: 'walk',
};

/** Farm owner — their farm IS the home screen. Brand-red identity. */
export function FarmDashboard() {
  const motion = useMotion();
  const router = useRouter();
  const toast = useToast();
  const { farms, cows, vets, kpis, farmsLoading, farmsError, fetchFarms, fetchKpis } = useAppStore();
  const farm = farms[0]; // Farm role users only see their own farm
  const summary = summarize(cows);
  // The vet assigned to this farm, when loaded
  const vet = farm ? vets.find((v) => v.farmIds.includes(farm.id)) ?? null : null;
  // Derived from the herd's own dry-off and calving dates — the farm record
  // carries no activity feed, and this card used to be permanently empty.
  const upcoming = farm ? farmUpcomingActivities(cows, farm.id) : [];

  useEffect(() => { fetchKpis(); }, []);

  if (!farm) {
    return (
      <Screen>
        <Header title="My Farm" subtitle="Your herd at a glance" />
        {farmsError ? (
          <ErrorBanner message={farmsError} onRetry={fetchFarms} />
        ) : farmsLoading ? (
          <View style={{ marginTop: spacing.lg }}>
            <SkeletonList count={3} variant="card" />
          </View>
        ) : (
          <EmptyState
            icon="business-outline"
            title="No farm linked yet"
            message="Ask your administrator to link your account to a farm."
          />
        )}
      </Screen>
    );
  }

  const kpiRow = [
    { label: 'Preg Rate', value: kpis?.pregnancyRate != null ? `${kpis.pregnancyRate}%` : '—' },
    { label: 'Conception', value: kpis?.conceptionRate != null ? `${kpis.conceptionRate}%` : '—' },
    { label: 'Serv/Conc', value: kpis?.servicesPerConception != null ? String(kpis.servicesPerConception) : '—' },
    { label: 'Calvings 30d', value: kpis ? String(kpis.upcomingCalvings30d) : '—' },
  ];

  return (
    <Screen padded={false} topInset={false}>
      <FocusedStatusBar style="light" />
      <HeroHeader gradient={gradients.primary}>
        <Animated.View entering={motion.downAt(0, 500)} style={styles.heroRow}>
          <Monogram name={farm.name} size={64} bg={onDark.panelBorder} color={colors.cream.base} />
          <View style={styles.heroText}>
            <Text variant="caption" color={onDark.textSecondary}>
              Welcome back
            </Text>
            <Text variant="title" color={onDark.text}>
              {farm.name}
            </Text>
            <Text variant="caption" color={onDark.textSecondary}>
              {farm.city}, {farm.province} · {summary.total} tracked cows
            </Text>
          </View>
        </Animated.View>

        <Animated.View entering={motion.downAt(120, 500)} style={styles.chipsRow}>
          <PressableScale
            style={styles.chip}
            onPress={() =>
              farm.assignedTechnicianPhone
                ? dial(farm.assignedTechnicianPhone)
                : toast.show(
                    farm.assignedTechnician
                      ? `${farm.assignedTechnician} has no phone number on file`
                      : 'No technician is assigned to your farm yet',
                    'construct',
                  )
            }
            accessibilityRole="button"
            accessibilityLabel="Contact technician"
          >
            <Ionicons name="construct" size={18} color={onDark.text} />
            <Text variant="label" color={onDark.text}>
              Technician
            </Text>
          </PressableScale>
          {vet ? (
            <PressableScale
              style={styles.chip}
              onPress={() => dial(vet.phone)}
              accessibilityRole="button"
              accessibilityLabel={`Call ${vet.name}`}
            >
              <Ionicons name="medkit" size={18} color={onDark.text} />
              <Text variant="label" color={onDark.text}>
                Call Vet
              </Text>
            </PressableScale>
          ) : null}
          <PressableScale
            style={styles.chip}
            onPress={() => router.push({ pathname: '/farm/herd', params: { id: farm.id } })}
            accessibilityRole="button"
            accessibilityLabel="View my herd"
          >
            <Ionicons name="list" size={18} color={onDark.text} />
            <Text variant="label" color={onDark.text}>
              My Herd
            </Text>
          </PressableScale>
        </Animated.View>
      </HeroHeader>

      <View style={styles.body}>
        {/* Herd summary */}
        <Animated.View entering={motion.upAt(150, 500)}>
          <View style={styles.statRow}>
            <StatCard value={summary.total} label="Tracked Cows" />
            <StatCard value={summary.pregnant} label="Pregnant" accent={status.pregnant.fg} />
            <StatCard value={summary.open} label="Open" accent={status.open.fg} />
          </View>
          <View style={styles.statRow}>
            <StatCard value={summary.dry} label="Dry" accent={status.dry.fg} />
            <StatCard value={summary.fresh} label="Fresh" accent={status.fresh.fg} />
            <StatCard value={summary.cull} label="Cull" accent={status.cull.fg} />
          </View>
        </Animated.View>

        {/* Doc-required KPIs */}
        <SectionHeader title="Performance" />
        <Animated.View entering={motion.upAt(200, 500)}>
          <Card style={styles.kpiCard}>
            {kpiRow.map((k) => (
              <View key={k.label} style={styles.kpiItem}>
                <Text variant="statSmall" color={colors.primary}>
                  {k.value}
                </Text>
                <Text variant="caption" color={colors.textSecondary} numberOfLines={1}>
                  {k.label}
                </Text>
              </View>
            ))}
          </Card>
        </Animated.View>

        {/* Upcoming on the farm */}
        <SectionHeader title="Upcoming On Your Farm" />
        <Animated.View entering={motion.upAt(240, 500)}>
          <Card style={styles.activityCard}>
            {upcoming.length === 0 ? (
              <Text variant="body" color={colors.textMuted}>
                Nothing scheduled — dry-offs and calvings appear here as they come due.
              </Text>
            ) : (
              upcoming.map((a, i) => (
                <View key={a.id} style={[styles.activityRow, i > 0 && styles.activityDivider]}>
                  <IconCircle name={ACTIVITY_ICONS[a.icon] ?? 'calendar'} size={38} />
                  <View style={styles.activityText}>
                    <Text variant="bodyBold">{a.label}</Text>
                    <Text variant="caption" color={colors.textSecondary}>
                      {a.date}
                    </Text>
                  </View>
                </View>
              ))
            )}
          </Card>
        </Animated.View>

        {/* Your team */}
        <SectionHeader title="Your Team" />
        <Animated.View entering={motion.upAt(310, 500)}>
          <Card style={styles.teamCard}>
            <PressableScale
              style={styles.teamRow}
              onPress={() => farm.assignedTechnicianPhone && dial(farm.assignedTechnicianPhone)}
              disabled={!farm.assignedTechnicianPhone}
              accessibilityRole="button"
              accessibilityLabel={
                farm.assignedTechnicianPhone
                  ? `Call ${farm.assignedTechnician}`
                  : 'Technician contact unavailable'
              }
            >
              <IconCircle name="construct" size={40} />
              <View style={styles.teamText}>
                <Text variant="bodyBold">
                  {farm.assignedTechnician || 'Technician not assigned yet'}
                </Text>
                <Text variant="caption" color={colors.textSecondary}>
                  Reproduction Technician
                  {farm.assignedTechnicianPhone ? ` · ${farm.assignedTechnicianPhone}` : ''}
                </Text>
              </View>
              {farm.assignedTechnicianPhone ? (
                <Ionicons name="call" size={18} color={colors.primary} />
              ) : null}
            </PressableScale>
            {vet ? (
              <PressableScale
                style={[styles.teamRow, styles.teamDivider]}
                onPress={() => router.push({ pathname: '/vet/[id]', params: { id: vet.id } })}
                accessibilityRole="button"
                accessibilityLabel={`Open veterinarian ${vet.name}`}
              >
                <IconCircle name="medkit" size={40} color={colors.primary} bg={colors.primarySoft} />
                <View style={styles.teamText}>
                  <Text variant="bodyBold">{vet.name}</Text>
                  <Text variant="caption" color={colors.textSecondary}>
                    Herd Veterinarian · {vet.clinic}
                  </Text>
                </View>
                <Ionicons name="chevron-forward" size={18} color={colors.textMuted} />
              </PressableScale>
            ) : null}
          </Card>
        </Animated.View>

        <Animated.View entering={motion.upAt(380, 500)}>
          <Button
            label="View Herd Reports"
            icon="bar-chart"
            onPress={() => router.push('/(tabs)/reports')}
            style={styles.reportsBtn}
          />
        </Animated.View>
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  heroRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.lg },
  heroText: { flex: 1, gap: 2 },
  chipsRow: { flexDirection: 'row', gap: spacing.sm, marginTop: spacing.xxl },
  chip: {
    flex: 1,
    alignItems: 'center',
    gap: spacing.xs,
    backgroundColor: onDark.scrim,
    borderWidth: 1,
    borderColor: onDark.panelBorder,
    borderRadius: radius.md,
    paddingVertical: spacing.md,
  },
  body: {
    paddingHorizontal: spacing.xl,
    marginTop: -spacing.xxxl,
  },
  statRow: { flexDirection: 'row', gap: spacing.md, marginBottom: spacing.md },
  kpiCard: { flexDirection: 'row', paddingVertical: spacing.lg },
  kpiItem: { flex: 1, alignItems: 'center', gap: 1 },
  activityCard: { gap: 0, paddingVertical: spacing.sm },
  activityRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    paddingVertical: spacing.md - 2,
  },
  activityDivider: {
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.border,
  },
  activityText: { flex: 1, gap: 1 },
  teamCard: { gap: 0, paddingVertical: spacing.sm },
  teamRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    paddingVertical: spacing.md - 2,
  },
  teamDivider: {
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.border,
  },
  teamText: { flex: 1, gap: 1 },
  reportsBtn: { marginTop: spacing.sm },
});
