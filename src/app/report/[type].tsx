import { Ionicons } from '@expo/vector-icons';
import { useLocalSearchParams, useRouter } from 'expo-router';
import React, { useEffect, useState } from 'react';
import { FlatList, Pressable, RefreshControl, StyleSheet, View } from 'react-native';
import Animated from 'react-native-reanimated';
import {
  CowRecordSheet,
  EmptyState,
  ErrorBanner,
  Header,
  Screen,
  StatusPill,
  Text,
  SkeletonList,
} from '@/components';
import { colors, radius, shadows, spacing, useMotion } from '@/theme';
import { emptyReport, knownReportType } from '@/data/reports';
import { WorklistCow } from '@/data/types';
import { farmWorklist, reportFromWorklist, useAppStore, worklistFarms } from '@/store/useAppStore';

/**
 * Layer 3 — the report itself: every cow on it, the exact action for each, and
 * where to record the outcome.
 *
 * Rows, actions and "can this user record it" all come from the server. The
 * screen decides nothing about membership — including which form opens, since
 * offering one the API would answer with a 403 is worse than offering none.
 */
export default function ReportDetailScreen() {
  const motion = useMotion();
  const { type, farmId } = useLocalSearchParams<{ type: string; farmId?: string }>();
  const router = useRouter();
  const state = useAppStore();
  const { worklist, worklistLoading, worklistError, fetchWorklist, ensureWorklist } = state;
  const [active, setActive] = useState<WorklistCow | null>(null);

  useEffect(() => {
    ensureWorklist();
  }, [type, farmId]);

  if (!type || !knownReportType(type)) {
    return (
      <Screen>
        <Header back title="Report" />
        <EmptyState
          icon="help-circle-outline"
          title="Report not found"
          message="This report type doesn't exist. Head back and pick one from the Reports tab."
        />
      </Screen>
    );
  }

  const farm = farmWorklist(state, farmId);
  const report = reportFromWorklist(state, type, farmId) ?? emptyReport(type);
  const list = report.cows;
  const loading = worklistLoading && !worklist;

  // Always the full worklist — a farm-scoped fetch would replace the whole
  // store slice with a one-farm payload and corrupt every other screen.
  const refresh = () => fetchWorklist();

  // A farm handed to someone else today is reference, not work — recording on
  // it would double-enter against whoever is actually covering the visit.
  //
  // Rows carry their own farmId, so the gate is evaluated PER ROW rather than
  // from the screen's optional farmId param: opened from the Reports hub or a
  // dashboard there is no farmId, and the gate silently never fired.
  const handedOff = new Set(
    worklistFarms(state)
      .filter((f) => f.schedule === 'reassigned' || f.schedule === 'skipped')
      .map((f) => f.farmId),
  );
  const isHandedOff = (cowFarmId: string) => handedOff.has(cowFarmId);
  const reassignedAway = farm != null && handedOff.has(farm.farmId);
  const canRecord = report.canRecord && !reassignedAway;

  return (
    <Screen scroll={false} padded={false}>
      <FlatList
        data={list}
        keyExtractor={(cow) => cow.cowId}
        contentContainerStyle={{ paddingHorizontal: spacing.xl, paddingBottom: spacing.huge }}
        refreshControl={
          <RefreshControl
            refreshing={worklistLoading && !!worklist}
            onRefresh={refresh}
            tintColor={colors.primary}
            colors={[colors.primary]}
          />
        }
        ListHeaderComponent={
          <>
            <Header
              back
              title={report.title}
              subtitle={
                [farm?.farmName, `${list.length} ${list.length === 1 ? 'cow' : 'cows'}`]
                  .filter(Boolean)
                  .join(' · ')
              }
            />
            {worklistError ? <ErrorBanner message={worklistError} onRetry={refresh} /> : null}
            {loading ? (
              <View style={{ marginTop: spacing.lg }}><SkeletonList count={4} variant="card" /></View>
            ) : null}
            {!canRecord && list.length > 0 ? (
              <View style={styles.readOnly}>
                <Ionicons name="eye-outline" size={15} color={colors.textSecondary} />
                <Text variant="caption" color={colors.textSecondary} style={styles.flex1}>
                  {reassignedAway
                    ? `${farm?.scheduleLabel ?? 'Reassigned today'} — view only.`
                    : type === 'pregnancy-check'
                      ? 'View only — the veterinarian records the result for this report.'
                      : "View only — your role can't record results on this report."}
                </Text>
              </View>
            ) : null}
          </>
        }
        ListEmptyComponent={
          loading || worklistError ? null : (
            <EmptyState title="No cows in this report" message="Nothing due here right now." />
          )
        }
        renderItem={({ item: cow, index }) => (
          <Animated.View entering={motion.down(index)}>
            <Pressable
              style={styles.row}
              onPress={() =>
                !isHandedOff(cow.farmId) && cow.recordKind
                  ? setActive(cow)
                  : router.push({ pathname: '/cow/[id]', params: { id: cow.cowId } })
              }
              accessibilityRole="button"
              accessibilityLabel={`${cow.earTag}. ${cow.action}`}
            >
              <View style={styles.rowTop}>
                <Text variant="subheading" style={styles.flex1} numberOfLines={1}>
                  {cow.earTag}
                </Text>
                {cow.overdue ? (
                  <View style={styles.overdue}>
                    <Text variant="caption" color={colors.danger}>Overdue</Text>
                  </View>
                ) : null}
                <StatusPill kind={report.type === 'heat' ? 'heat' : cow.status} />
              </View>

              {/* Action Required — the imperative instruction for today */}
              <View style={styles.actionRow}>
                <Ionicons name="arrow-forward-circle" size={15} color={colors.primary} />
                <Text variant="body" color={colors.text} style={styles.flex1}>
                  {cow.action}
                </Text>
              </View>

              <View style={styles.metaRow}>
                <Text variant="caption" color={colors.textMuted} numberOfLines={1} style={styles.flex1}>
                  {cow.detail}
                </Text>
                <Text variant="caption" color={colors.primary}>
                  {!isHandedOff(cow.farmId) && cow.recordKind ? 'Tap to record' : 'Open profile'}
                </Text>
              </View>
            </Pressable>
          </Animated.View>
        )}
      />

      <CowRecordSheet
        visible={!!active}
        cow={active ?? undefined}
        reportType={type}
        onClose={() => setActive(null)}
        onRecorded={refresh}
      />
    </Screen>
  );
}

const styles = StyleSheet.create({
  flex1: { flex: 1 },
  row: {
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.lg,
    marginBottom: spacing.sm + 2,
    gap: spacing.sm,
    ...shadows.card,
  },
  rowTop: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  actionRow: { flexDirection: 'row', alignItems: 'flex-start', gap: spacing.sm },
  metaRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  overdue: {
    paddingHorizontal: spacing.sm,
    paddingVertical: 1,
    borderRadius: radius.pill,
    backgroundColor: colors.primarySoft,
  },
  readOnly: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    marginBottom: spacing.md,
  },
});
