import { Ionicons } from '@expo/vector-icons';
import { LinearGradient } from 'expo-linear-gradient';
import { useRouter } from 'expo-router';
import React, { useEffect } from 'react';
import { StyleSheet, View } from 'react-native';
import {
  ErrorBanner,
  Header,
  ListRow,
  Screen,
  SectionHeader,
  Text,
} from '@/components';
import { alpha, colors, gradients, onDark, radius, red, shadows, spacing, status, StatusKey } from '@/theme';
import { WorklistReport } from '@/data/types';
import {
  DAILY_REPORT_TYPES, emptyReport, LIST_REPORT_TYPES, PROGRAM_REPORT_TYPES,
} from '@/data/reports';
import { mergedReports, summarize, useAppStore } from '@/store/useAppStore';
import { useAuthStore, useRole } from '@/store/useAuthStore';

export default function ReportsScreen() {
  const router = useRouter();
  const store = useAppStore();
  const { cows, kpis, cowsLoading, cowsError, fetchCows, fetchWorklist, fetchKpis } = store;
  // Counts come from the same payload the To-Do list uses, so the hub and the
  // technician's day can never show different numbers for the same report.
  const reports = mergedReports(store);
  const { user } = useAuthStore();
  const summary = summarize(cows);

  useEffect(() => {
    fetchWorklist();
    fetchKpis();
  }, []);

  const refresh = () => {
    fetchCows();
    fetchWorklist();
    fetchKpis();
  };

  const role = useRole();
  const scopeLabel =
    role === 'farm'
      ? 'Your herd performance'
      : role === 'vet'
        ? 'Your assigned farms'
        : 'Herd performance at a glance';

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

  // A report the server omitted has no cows today; still list it so the hub is
  // a stable catalog rather than a list that shifts under the user.
  const byType = (types: string[]) =>
    types.map((t) => reports.find((r) => r.type === t) ?? emptyReport(t));

  const dailyReports = byType(DAILY_REPORT_TYPES);
  const programReports = byType(PROGRAM_REPORT_TYPES);
  const lists = byType(LIST_REPORT_TYPES);

  const renderReportRows = (defs: WorklistReport[]) =>
    defs.map((r) => {
      const c = status[r.statusKey as StatusKey] ?? status.open;
      const count = r.count;
      return (
        <ListRow
          key={r.type}
          icon={r.icon as keyof typeof Ionicons.glyphMap}
          iconColor={c.fg}
          iconBg={c.bg}
          title={r.title}
          subtitle={`${count} ${count === 1 ? 'cow' : 'cows'}`}
          onPress={() => router.push({ pathname: '/report/[type]', params: { type: r.type } })}
        />
      );
    });

  return (
    <Screen refreshing={cowsLoading} onRefresh={refresh}>
      <Header title="Reports" subtitle={scopeLabel} />

      {cowsError ? <ErrorBanner message={cowsError} onRetry={refresh} /> : null}

      {/* Charcoal analytics panel */}
      <View>
        <LinearGradient
          colors={gradients.charcoal as unknown as [string, string, ...string[]]}
          start={{ x: 0, y: 0 }}
          end={{ x: 1, y: 1 }}
          style={styles.panel}
        >
          <View style={styles.panelTop}>
            <View>
              <Text variant="label" color={onDark.textMuted}>
                Herd Summary
              </Text>
              <Text variant="display" color={onDark.text}>
                {summary.total}
              </Text>
              <Text variant="caption" color={onDark.textMuted}>
                Total cows tracked
              </Text>
            </View>
            <View style={styles.heatBadge}>
              <Text variant="stat" color={onDark.text}>
                {summary.heat}
              </Text>
              <Text variant="label" color={onDark.textSecondary}>
                In Heat
              </Text>
            </View>
          </View>

          {/* Mini bar chart */}
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

          {/* Doc-required KPIs */}
          <View style={styles.kpiRow}>
            {kpiItems.map((k) => (
              <View key={k.label} style={styles.kpiItem}>
                <Text variant="statSmall" color={onDark.text}>
                  {k.value}
                </Text>
                <Text variant="caption" color={onDark.textSecondary} numberOfLines={1}>
                  {k.label}
                </Text>
              </View>
            ))}
          </View>
        </LinearGradient>
      </View>

      <SectionHeader title="Daily Reports" />
      {renderReportRows(dailyReports)}

      <SectionHeader title="Program Reports" />
      {renderReportRows(programReports)}

      <SectionHeader title="Lists" />
      {renderReportRows(lists)}
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
