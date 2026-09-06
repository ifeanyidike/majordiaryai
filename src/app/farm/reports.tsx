import { Ionicons } from '@expo/vector-icons';
import { LinearGradient } from 'expo-linear-gradient';
import { useLocalSearchParams, useRouter } from 'expo-router';
import React, { useEffect } from 'react';
import { StyleSheet, View } from 'react-native';
import {
  EmptyState,
  ErrorBanner,
  Header,
  ListRow,
  Screen,
  SectionHeader,
  SkeletonList,
  Text,
} from '@/components';
import {
  alpha, colors, gradients, onDark, radius, red, shadows, spacing, status, StatusKey,
} from '@/theme';
import { WorklistReport } from '@/data/types';
import {
  DAILY_REPORT_TYPES, emptyReport, LIST_REPORT_TYPES, PROGRAM_REPORT_TYPES,
} from '@/data/reports';
import {
  cowsByFarm, farmById, farmWorklist, summarize, useAppStore,
} from '@/store/useAppStore';

/**
 * One farm's reports.
 *
 * Reports used to live on a global tab that merged every farm the user could
 * see into a single list. The client's correction: a report belongs to a farm.
 * A technician standing at Green Valley wants Green Valley's Heat Report, not
 * every farm's heat cows in one column with the farm name buried in the meta
 * line. So this screen is reached from the farm, and every report it opens is
 * already filtered to it.
 *
 * Membership still comes from the server's worklist payload — the one source
 * of report rules — this screen only picks out one farm's slice of it.
 */
export default function FarmReportsScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const state = useAppStore();
  const {
    worklist, worklistLoading, worklistError,
    fetchWorklist, ensureWorklist, fetchCows, fetchKpis, kpisByFarm,
  } = state;
  const farm = id ? farmById(state, id) : undefined;
  const slice = id ? farmWorklist(state, id) : undefined;

  useEffect(() => {
    if (!id) return;
    ensureWorklist();
    fetchCows(id);
    fetchKpis(id);
  }, [id]);

  if (!farm) {
    return (
      <Screen>
        <Header back title="Reports" />
        <EmptyState title="Farm not found" />
      </Screen>
    );
  }

  const herd = cowsByFarm(state, farm.id);
  const summary = summarize(herd);
  const kpis = kpisByFarm[farm.id];
  const reports = slice?.reports ?? [];
  const loading = worklistLoading && !worklist;

  const refresh = () => {
    fetchWorklist();
    fetchCows(farm.id);
    fetchKpis(farm.id);
  };

  // Chart colors come from the same status tokens as StatusPill —
  // one status, one color, everywhere.
  const breakdown = [
    { key: 'pregnant', label: 'Pregnant', count: summary.pregnant, color: status.pregnant.fg },
    { key: 'open', label: 'Open', count: summary.open, color: status.open.fg },
    { key: 'inseminated', label: 'Bred', count: summary.inseminated, color: status.inseminated.fg },
    { key: 'dry', label: 'Dry', count: summary.dry, color: status.dry.fg },
    { key: 'fresh', label: 'Fresh', count: summary.fresh, color: status.fresh.fg },
    { key: 'cull', label: 'Cull', count: summary.cull, color: status.cull.fg },
  ];
  const maxCount = Math.max(...breakdown.map((b) => b.count), 1);

  const kpiItems = [
    { label: 'Preg Rate', value: kpis?.pregnancyRate != null ? `${kpis.pregnancyRate}%` : '—' },
    { label: 'Conception', value: kpis?.conceptionRate != null ? `${kpis.conceptionRate}%` : '—' },
    { label: 'Serv/Conc', value: kpis?.servicesPerConception != null ? String(kpis.servicesPerConception) : '—' },
    { label: 'Calvings 30d', value: kpis ? String(kpis.upcomingCalvings30d) : '—' },
  ];

  // A report the server omitted has no cows on this farm today; still list it
  // so the hub is a stable catalog rather than a list that shifts under the user.
  const byType = (types: string[]) =>
    types.map((t) => reports.find((r) => r.type === t) ?? emptyReport(t));

  const renderRows = (defs: WorklistReport[]) =>
    defs.map((r) => {
      const c = status[r.statusKey as StatusKey] ?? status.open;
      return (
        <ListRow
          key={r.type}
          icon={r.icon as keyof typeof Ionicons.glyphMap}
          iconColor={c.fg}
          iconBg={c.bg}
          title={r.title}
          subtitle={`${r.count} ${r.count === 1 ? 'cow' : 'cows'}`}
          onPress={() =>
            router.push({
              pathname: '/report/[type]',
              params: { type: r.type, farmId: farm.id },
            })
          }
        />
      );
    });

  return (
    <Screen refreshing={worklistLoading && !!worklist} onRefresh={refresh}>
      <Header back title={farm.name} subtitle="Reports" />

      {worklistError ? <ErrorBanner message={worklistError} onRetry={refresh} /> : null}

      <LinearGradient
        colors={gradients.charcoal as unknown as [string, string, ...string[]]}
        start={{ x: 0, y: 0 }}
        end={{ x: 1, y: 1 }}
        style={styles.panel}
      >
        <View style={styles.panelTop}>
          <View>
            <Text variant="label" color={onDark.textMuted}>Herd Summary</Text>
            <Text variant="display" color={onDark.text}>{summary.total}</Text>
            <Text variant="caption" color={onDark.textMuted}>Cows on this farm</Text>
          </View>
          <View style={styles.heatBadge}>
            <Text variant="stat" color={onDark.text}>{summary.heat}</Text>
            <Text variant="label" color={onDark.textSecondary}>In Heat</Text>
          </View>
        </View>

        <View style={styles.chart}>
          {breakdown.map((b) => (
            <View key={b.key} style={styles.chartRow}>
              <Text variant="caption" color={onDark.textSecondary} style={styles.chartLabel}>
                {b.label}
              </Text>
              <View style={styles.chartTrack}>
                <View
                  style={[
                    styles.chartBar,
                    { width: `${(b.count / maxCount) * 100}%`, backgroundColor: b.color },
                  ]}
                />
              </View>
              <Text variant="bodyBold" color={onDark.text} style={styles.chartCount}>
                {b.count}
              </Text>
            </View>
          ))}
        </View>

        <View style={styles.kpiRow}>
          {kpiItems.map((k) => (
            <View key={k.label} style={styles.kpiItem}>
              <Text variant="statSmall" color={onDark.text}>{k.value}</Text>
              <Text variant="caption" color={onDark.textSecondary} numberOfLines={1}>
                {k.label}
              </Text>
            </View>
          ))}
        </View>
      </LinearGradient>

      {loading ? (
        <View style={{ marginTop: spacing.xl }}><SkeletonList count={5} /></View>
      ) : (
        <>
          <SectionHeader title="Daily Reports" />
          {renderRows(byType(DAILY_REPORT_TYPES))}

          <SectionHeader title="Program Reports" />
          {renderRows(byType(PROGRAM_REPORT_TYPES))}

          <SectionHeader title="Lists" />
          {renderRows(byType(LIST_REPORT_TYPES))}
        </>
      )}
    </Screen>
  );
}

const styles = StyleSheet.create({
  panel: {
    borderRadius: radius.lg,
    padding: spacing.xxl,
    gap: spacing.xl,
    ...shadows.raised,
  },
  panelTop: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
  },
  heatBadge: {
    alignItems: 'center',
    backgroundColor: alpha(red[500], 0.35),
    borderWidth: 1,
    borderColor: alpha(red[300], 0.4),
    borderRadius: radius.md,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    gap: spacing.hairline,
  },
  chart: { gap: spacing.md },
  chartRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  chartLabel: { width: 64 },
  chartTrack: {
    flex: 1,
    height: 10,
    borderRadius: 5,
    backgroundColor: onDark.panel,
    overflow: 'hidden',
  },
  chartBar: { height: '100%', borderRadius: 5 },
  chartCount: { width: 24, textAlign: 'right' },
  kpiRow: {
    flexDirection: 'row',
    borderTopWidth: 1,
    borderTopColor: onDark.divider,
    paddingTop: spacing.lg,
  },
  kpiItem: { flex: 1, alignItems: 'center', gap: spacing.hairline },
});
