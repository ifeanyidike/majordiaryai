import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import React, { useEffect } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import {
  EmptyState,
  ErrorBanner,
  Header,
  Screen,
  Text,
  SkeletonList,
} from '@/components';
import { colors, radius, shadows, spacing } from '@/theme';
import { formatAddress, openDirections } from '@/lib/maps';
import { VisitSchedule, WorklistFarm } from '@/data/types';
import { useAppStore, worklistFarms } from '@/store/useAppStore';

/**
 * Layer 1 — General To-Do List: which farms the technician visits today.
 *
 * Which farms appear is a schedule question, not a workload question: farms run
 * on 5- or 6-day rotations, and a day can be handed to a relief technician. The
 * server resolves both; this screen renders the answer. A scheduled farm with
 * no cows due still appears (that's a real, informative "nothing to do here"),
 * and a farm reassigned away is shown flagged to skip so its absence from the
 * route is explained rather than mysterious.
 */
export default function TasksScreen() {
  const router = useRouter();
  const state = useAppStore();
  const { worklist, worklistLoading, worklistError, fetchWorklist } = state;
  const farms = worklistFarms(state);

  useEffect(() => {
    fetchWorklist();
  }, []);

  const visiting = farms.filter((f) => f.schedule === 'visit_today' || f.schedule === 'covering');
  const skipping = farms.filter((f) => f.schedule === 'reassigned' || f.schedule === 'skipped');
  const totalCows = visiting.reduce((n, f) => n + f.totalCows, 0);
  const loading = worklistLoading && !worklist;

  const today = new Date().toLocaleDateString('en-CA', {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
  });

  return (
    <Screen refreshing={worklistLoading && !!worklist} onRefresh={fetchWorklist}>
      <Header
        title="To Do List"
        subtitle={today}
        right={
          visiting.length > 0 ? (
            <View style={styles.countBadge}>
              <Text variant="label" color={colors.primary}>
                {visiting.length} {visiting.length === 1 ? 'farm' : 'farms'}
              </Text>
            </View>
          ) : undefined
        }
      />

      {worklistError ? (
        <ErrorBanner message={worklistError} onRetry={() => fetchWorklist()} />
      ) : null}

      {visiting.length > 0 && (
        <Text variant="body" color={colors.textSecondary} style={styles.lead}>
          {totalCows} {totalCows === 1 ? 'cow' : 'cows'} to process across your farms today.
        </Text>
      )}

      {loading ? (
        <View style={{ marginTop: spacing.lg }}><SkeletonList count={3} variant="card" /></View>
      ) : !worklistError && farms.length === 0 ? (
        <EmptyState
          icon="checkmark-done-outline"
          title="No visits today"
          message="No farm is on your rotation today."
          action={{ label: 'Refresh', icon: 'refresh', onPress: () => fetchWorklist() }}
        />
      ) : null}

      {visiting.map((farm) => (
        <FarmCard
          key={farm.farmId}
          farm={farm}
          onOpen={() =>
            router.push({ pathname: '/farm-todo/[id]', params: { id: farm.farmId } })
          }
        />
      ))}

      {skipping.length > 0 && (
        <>
          <Text variant="label" color={colors.textSecondary} style={styles.sectionLabel}>
            Not yours today
          </Text>
          {skipping.map((farm) => (
            <FarmCard
              key={farm.farmId}
              farm={farm}
              onOpen={() =>
                router.push({ pathname: '/farm-todo/[id]', params: { id: farm.farmId } })
              }
            />
          ))}
        </>
      )}
    </Screen>
  );
}

const SCHEDULE_STYLE: Record<VisitSchedule, { icon: keyof typeof Ionicons.glyphMap; color: string }> = {
  visit_today: { icon: 'today', color: colors.primary },
  covering: { icon: 'swap-horizontal', color: colors.primary },
  reassigned: { icon: 'arrow-redo', color: colors.textSecondary },
  skipped: { icon: 'remove-circle-outline', color: colors.textSecondary },
  // Off-rotation farms never render on this route screen (filtered below), but
  // the map must stay total over VisitSchedule.
  not_due: { icon: 'calendar-outline', color: colors.textSecondary },
};

function FarmCard({ farm, onOpen }: { farm: WorklistFarm; onOpen: () => void }) {
  const skip = farm.schedule === 'reassigned' || farm.schedule === 'skipped';
  const chip = SCHEDULE_STYLE[farm.schedule];
  const address = formatAddress(farm.address, farm.city);
  const reports = farm.reports.filter((r) => r.isWorkReport);

  return (
    <Pressable
      style={[styles.farmCard, skip && styles.farmCardMuted]}
      onPress={onOpen}
      accessibilityRole="button"
      accessibilityLabel={`${farm.farmName}. ${farm.scheduleLabel}. ${farm.totalCows} cows to process`}
    >
      <View style={styles.farmTop}>
        <View style={styles.farmIcon}>
          <Ionicons name="business" size={22} color={colors.primary} />
        </View>
        <View style={styles.flex1}>
          <Text variant="heading" numberOfLines={1}>{farm.farmName}</Text>
          {address ? (
            <Text variant="caption" color={colors.textSecondary} numberOfLines={1}>
              {address}
            </Text>
          ) : null}
        </View>
        {!skip && (
          <View style={styles.workBadge}>
            <Text variant="bodyBold" color={colors.textOnPrimary}>{farm.totalCows}</Text>
          </View>
        )}
      </View>

      {/* Schedule — the spec's Schedule column, including why a farm is skipped */}
      <View style={styles.scheduleRow}>
        <Ionicons name={chip.icon} size={13} color={chip.color} />
        <Text variant="caption" color={chip.color}>{farm.scheduleLabel}</Text>
        {farm.reassignReason ? (
          <Text variant="caption" color={colors.textMuted} numberOfLines={1} style={styles.flex1}>
            · {farm.reassignReason}
          </Text>
        ) : null}
      </View>

      {reports.length > 0 ? (
        <View style={styles.chipRow}>
          {reports.map((r) => (
            <View key={r.type} style={styles.chip}>
              <Ionicons
                name={r.icon as keyof typeof Ionicons.glyphMap}
                size={12}
                color={colors.textSecondary}
              />
              <Text variant="caption" color={colors.textSecondary}>
                {r.title.replace(' Report', '')} · {r.count}
              </Text>
            </View>
          ))}
        </View>
      ) : (
        <Text variant="caption" color={colors.textMuted}>
          Nothing due here today — visit scheduled all the same.
        </Text>
      )}

      <View style={styles.farmActions}>
        <View style={styles.openRow}>
          <Text variant="bodyBold" color={colors.primary}>Open farm list</Text>
          <Ionicons name="chevron-forward" size={16} color={colors.primary} />
        </View>
        {address ? (
          <Pressable
            onPress={() => openDirections(formatAddress(farm.address, farm.city, farm.province))}
            style={styles.iconAction}
            accessibilityRole="button"
            accessibilityLabel={`Directions to ${farm.farmName}`}
          >
            <Ionicons name="navigate-outline" size={17} color={colors.textSecondary} />
            <Text variant="caption" color={colors.textSecondary}>Directions</Text>
          </Pressable>
        ) : null}
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  countBadge: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: radius.pill,
    backgroundColor: colors.primarySoft,
  },
  lead: { marginBottom: spacing.lg },
  sectionLabel: { marginTop: spacing.md, marginBottom: spacing.sm },
  flex1: { flex: 1 },
  farmCard: {
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.lg,
    marginBottom: spacing.md,
    gap: spacing.md,
    ...shadows.card,
  },
  farmCardMuted: { opacity: 0.62 },
  farmTop: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  farmIcon: {
    width: 44, height: 44, borderRadius: radius.pill,
    backgroundColor: colors.primarySoft,
    alignItems: 'center', justifyContent: 'center',
  },
  workBadge: {
    minWidth: 34, height: 34, borderRadius: 17,
    paddingHorizontal: spacing.sm,
    backgroundColor: colors.primary,
    alignItems: 'center', justifyContent: 'center',
  },
  scheduleRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.xs },
  chipRow: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.xs + 2 },
  chip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    backgroundColor: colors.surfaceSoft,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.sm,
    paddingHorizontal: spacing.sm + 2,
    paddingVertical: spacing.xs + 1,
  },
  farmActions: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.border,
    paddingTop: spacing.md,
  },
  openRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.xs },
  iconAction: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    minHeight: 44,
    paddingHorizontal: spacing.sm,
  },
});
