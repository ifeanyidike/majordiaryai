import { Ionicons } from '@expo/vector-icons';
import { useLocalSearchParams, useRouter } from 'expo-router';
import React, { useEffect } from 'react';
import { StyleSheet, View } from 'react-native';
import {
  Button,
  EmptyState,
  ErrorBanner,
  Header,
  ListRow,
  Screen,
  Text,
  SkeletonList,
} from '@/components';
import { colors, radius, spacing, status, StatusKey } from '@/theme';
import { formatAddress, openDirections } from '@/lib/maps';
import { dial } from '@/lib/contact';
import { farmWorklist, useAppStore } from '@/store/useAppStore';

/**
 * Layer 2 — Farm To-Do List: what work exists at this farm, summarized by
 * report with a cow count. No individual cow detail here; that's the report
 * (layer 3). Counts come straight from the server payload, so they cannot
 * disagree with the rows the technician finds when he opens one.
 */
export default function FarmTodoScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const state = useAppStore();
  const { worklist, worklistLoading, worklistError, fetchWorklist, ensureWorklist } = state;
  const farm = farmWorklist(state, id);

  useEffect(() => {
    ensureWorklist();
  }, [id]);

  if (!farm) {
    return (
      <Screen>
        <Header back title="Farm To-Do" />
        {worklistError ? (
          <ErrorBanner message={worklistError} onRetry={() => fetchWorklist()} />
        ) : worklistLoading || !worklist ? (
          // Still loading — don't claim the farm isn't on the route.
          <View style={{ marginTop: spacing.lg }}><SkeletonList count={4} variant="card" /></View>
        ) : (
          <EmptyState
            title="Not on today's route"
            message="This farm isn't scheduled for you today."
          />
        )}
      </Screen>
    );
  }

  const reports = farm.reports.filter((r) => r.isWorkReport);
  // Off-rotation farms are reachable (deep link, farm profile) — say so rather
  // than presenting the day as a scheduled visit.
  const skip =
    farm.schedule === 'reassigned' || farm.schedule === 'skipped' || farm.schedule === 'not_due';
  const address = formatAddress(farm.address, farm.city, farm.province);

  return (
    <Screen refreshing={worklistLoading && !!worklist} onRefresh={() => fetchWorklist()}>
      <Header
        back
        title={farm.farmName}
        subtitle={
          farm.totalCows > 0
            ? `${farm.totalCows} ${farm.totalCows === 1 ? 'cow' : 'cows'} to process`
            : 'No work today'
        }
      />

      {/* The schedule is the reason this farm is (or isn't) on the route */}
      {skip ? (
        <View style={styles.skipBanner}>
          <Ionicons name="arrow-redo" size={18} color={colors.textSecondary} />
          <View style={styles.flex1}>
            <Text variant="bodyBold" color={colors.text}>{farm.scheduleLabel}</Text>
            {farm.reassignReason ? (
              <Text variant="caption" color={colors.textSecondary}>{farm.reassignReason}</Text>
            ) : null}
          </View>
        </View>
      ) : null}

      {/* Quick farm actions while on site */}
      <View style={styles.actionRow}>
        <Button
          compact
          variant="secondary"
          label="Directions"
          icon="navigate"
          onPress={() => openDirections(address)}
          style={styles.flex1}
        />
        <Button
          compact
          variant="secondary"
          label="Call Farm"
          icon="call"
          onPress={() => dial(farm.phone)}
          style={styles.flex1}
        />
        <Button
          compact
          variant="secondary"
          label="Herd"
          icon="list"
          onPress={() => router.push({ pathname: '/farm/herd', params: { id: farm.farmId } })}
          style={styles.flex1}
        />
      </View>

      {reports.length === 0 ? (
        <EmptyState
          icon="checkmark-done-outline"
          title="Nothing due at this farm"
          message={
            farm.nextVisitDate
              ? `No cows are on a report here today. Next scheduled visit: ${farm.nextVisitDate}.`
              : 'No cows are currently on any report here.'
          }
        />
      ) : (
        <>
          <Text variant="label" color={colors.textSecondary} style={styles.sectionLabel}>
            Reports to process
          </Text>
          {reports.map((r) => {
            const c = status[r.statusKey as StatusKey] ?? status.open;
            return (
              <ListRow
                key={r.type}
                icon={r.icon as keyof typeof Ionicons.glyphMap}
                iconColor={c.fg}
                iconBg={c.bg}
                title={r.title}
                subtitle={r.subtitle}
                right={
                  <View style={styles.countPill}>
                    <Text variant="bodyBold" color={c.fg}>{r.count}</Text>
                  </View>
                }
                onPress={() =>
                  router.push({
                    pathname: '/report/[type]',
                    params: { type: r.type, farmId: farm.farmId },
                  })
                }
              />
            );
          })}
        </>
      )}
    </Screen>
  );
}

const styles = StyleSheet.create({
  actionRow: { flexDirection: 'row', gap: spacing.sm, marginBottom: spacing.lg },
  flex1: { flex: 1 },
  sectionLabel: { marginBottom: spacing.sm },
  skipBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    backgroundColor: colors.surfaceSoft,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.sm,
    padding: spacing.md,
    marginBottom: spacing.md,
  },
  countPill: {
    minWidth: 30,
    paddingHorizontal: spacing.sm,
    paddingVertical: 2,
    borderRadius: radius.pill,
    backgroundColor: colors.surfaceSoft,
    alignItems: 'center',
  },
});
