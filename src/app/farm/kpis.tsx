import { Ionicons } from '@expo/vector-icons';
import { useLocalSearchParams } from 'expo-router';
import React, { useEffect, useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import {
  EmptyState, ErrorBanner, Header, Screen, SkeletonList, Text,
} from '@/components';
import { BarChart } from '@/components/charts/BarChart';
import {
  formatKpi, Metric, MetricGroup, STATUS_COLOR, STATUS_WORD,
} from '@/components/charts/MetricList';
import { colors, radius, spacing } from '@/theme';
import { parseLocalDate } from '@/lib/dates';
import { KPI_DEFINITIONS, KpiReport, KpiValue } from '@/data/kpis';
import { farmById, useAppStore } from '@/store/useAppStore';

/**
 * One farm's reproduction performance.
 *
 * Built around three questions, in the order a farmer asks them: how is the
 * breeding programme doing, what needs fixing, and what are all the numbers.
 *
 * The first version answered the third question fourteen times over — a grid
 * of bordered tiles each carrying a value, a denominator, a judgement word and
 * a target sentence, under three charts of equal weight. Everything competed,
 * so nothing led. Now: one hero figure, one chart that earns its space, the
 * exceptions named outright, and the rest as a quiet list that opens on tap.
 */
export default function FarmKpisScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const state = useAppStore();
  const { kpiReports, kpiLoading, kpiError, fetchKpiReport } = state;
  const farm = id ? farmById(state, id) : undefined;
  const report: KpiReport | undefined = id ? kpiReports[id] : undefined;
  const [showDefs, setShowDefs] = useState(false);

  useEffect(() => {
    if (id) fetchKpiReport(id);
  }, [id]);

  if (!farm) {
    return (
      <Screen>
        <Header back title="Performance" />
        <EmptyState title="Farm not found" />
      </Screen>
    );
  }

  const refresh = () => fetchKpiReport(farm.id);

  if (!report) {
    return (
      <Screen refreshing={kpiLoading} onRefresh={refresh}>
        <Header back title={farm.name} subtitle="Performance" />
        {kpiError ? <ErrorBanner message={kpiError} onRetry={refresh} /> : null}
        {!kpiError ? (
          <View style={{ marginTop: spacing.xl }}><SkeletonList count={3} variant="card" /></View>
        ) : null}
      </Screen>
    );
  }

  const { conception, timing, outcomes, compliance } = report;
  const pr = report.pregnancy_rate_21d;

  const breeding: Metric[] = [
    { label: 'Service rate', kpi: report.service_rate_21d,
      basis: `${report.service_rate_21d.n} eligible cow-cycles` },
    { label: 'Conception rate', kpi: conception.rate,
      basis: `${conception.rate.n} checked${conception.unchecked_breedings ? ` · ${conception.unchecked_breedings} awaiting a check` : ''}` },
    { label: 'First-service conception', kpi: conception.first_service_rate,
      basis: `${conception.first_service_rate.n} first breedings` },
    { label: 'Services per conception', kpi: conception.services_per_conception,
      basis: `${conception.services_per_conception.n} pregnancies` },
  ];

  const timingMetrics: Metric[] = [
    { label: 'Days open (median)', kpi: timing.days_open,
      basis: `${timing.days_open.n} pregnancies${timing.days_open.mean != null ? ` · mean ${timing.days_open.mean}` : ''}` },
    { label: 'Days to first service', kpi: timing.days_to_first_service,
      basis: `${timing.days_to_first_service.n} calvings` },
    { label: 'Calving interval', kpi: timing.calving_interval_months,
      basis: `${timing.calving_interval_months.n} cows with two calvings` },
    { label: 'Overdue pregnancy checks', kpi: outcomes.overdue_pregnancy_checks,
      basis: 'cows past day 50 with no result entered' },
  ];

  const herd: Metric[] = [
    { label: 'Stillbirth rate', kpi: outcomes.stillbirth_rate, basis: `${outcomes.calvings} calvings` },
    { label: 'Cull rate', kpi: outcomes.cull_rate, basis: `${outcomes.culls} culled in 12 months` },
    { label: 'Heifers from sexed semen', kpi: outcomes.sexed_semen_heifer_rate,
      basis: `${outcomes.sexed_semen_heifer_rate.n} calves · expect about 90%` },
    { label: 'Heifers from conventional', kpi: outcomes.conventional_heifer_rate,
      basis: `${outcomes.conventional_heifer_rate.n} calves · expect about 48%` },
  ];

  const protocols: Metric[] = [
    { label: 'Shots given on the day', kpi: compliance.protocol_on_time_rate,
      basis: `${compliance.protocol_on_time_rate.late} late · ${compliance.protocol_on_time_rate.missed} missed` },
    { label: 'Protocols completed', kpi: compliance.protocol_completion_rate,
      basis: `${compliance.protocol_completion_rate.cancelled} cancelled · ${compliance.protocol_completion_rate.active} still running` },
    { label: 'Heat-check coverage', kpi: compliance.heat_check_coverage,
      basis: `${compliance.heat_check_coverage.n} breedings past day 25` },
  ];

  const groups = [
    { title: 'Breeding', metrics: breeding },
    { title: 'Timing', metrics: timingMetrics },
    { title: 'Herd', metrics: herd },
    { title: 'Protocols', metrics: protocols },
  ];

  // Only what is actionable gets named up front. "Fair" and "poor" qualify;
  // "too few records" does not — that is a data gap, not a herd problem.
  const attention = groups
    .flatMap((g) => g.metrics)
    .filter((m) => m.kpi.status === 'poor' || m.kpi.status === 'fair');

  const judged = [pr, ...groups.flatMap((g) => g.metrics.map((m) => m.kpi))]
    .some((k: KpiValue) => k.status !== 'na');

  const cycleLabel = (start: string) =>
    parseLocalDate(start).toLocaleDateString('en-CA', { month: 'short', day: 'numeric' });

  return (
    <Screen refreshing={kpiLoading} onRefresh={refresh}>
      <Header back title={farm.name} subtitle="Performance" />
      {kpiError ? <ErrorBanner message={kpiError} onRetry={refresh} /> : null}

      {/* One hero figure, no card — the number is the thing, not its frame. */}
      <View style={styles.hero}>
        <Text variant="label" color={colors.textMuted}>21-day pregnancy rate</Text>
        <View style={styles.heroValue}>
          <Text variant="hero" color={pr.value == null ? colors.textMuted : colors.text}>
            {pr.value == null ? '—' : `${pr.value % 1 === 0 ? pr.value : pr.value.toFixed(1)}`}
          </Text>
          {pr.value != null ? (
            <Text variant="title" color={colors.textSecondary} style={styles.heroUnit}>%</Text>
          ) : null}
        </View>
        <View style={styles.heroStatus}>
          <View style={[styles.dot, { backgroundColor: STATUS_COLOR[pr.status] }]} />
          <Text variant="bodyBold" color={STATUS_COLOR[pr.status]}>{STATUS_WORD[pr.status]}</Text>
          {pr.target ? (
            <Text variant="caption" color={colors.textMuted} numberOfLines={1} style={styles.flex1}>
              · {pr.target.split('—')[0].trim()}
            </Text>
          ) : null}
        </View>
      </View>

      <View style={styles.chartCard}>
        <BarChart
          unit="%"
          benchmark={{ value: 20, label: '20%' }}
          data={report.cycles.map((c) => ({
            label: cycleLabel(c.start),
            value: c.pregnancy_rate,
            pending: c.pending,
            detail: `${c.conceived} of ${c.eligible} eligible · ${c.served} bred`
              + (c.unchecked ? ` · ${c.unchecked} awaiting checks` : ''),
          }))}
          pendingLabel="Checks not in yet"
        />
      </View>

      {/* The exceptions, named. This is also what keeps the list's status dots
          from being colour-only: anything off target is written out here. */}
      {attention.length > 0 ? (
        <View style={styles.attention}>
          {attention.map((m) => (
            <View key={m.label} style={styles.attentionRow}>
              <View style={[styles.dot, { backgroundColor: STATUS_COLOR[m.kpi.status] }]} />
              <Text variant="body" style={styles.flex1} numberOfLines={1}>{m.label}</Text>
              <Text variant="bodyBold" style={styles.attentionValue}>{formatKpi(m.kpi)}</Text>
            </View>
          ))}
        </View>
      ) : judged ? (
        <View style={styles.allClear}>
          <Ionicons name="checkmark-circle" size={16} color={colors.success} />
          <Text variant="body" color={colors.textSecondary}>Every figure is on target.</Text>
        </View>
      ) : (
        <View style={styles.allClear}>
          <Ionicons name="time-outline" size={16} color={colors.textMuted} />
          <Text variant="body" color={colors.textSecondary} style={styles.flex1}>
            Not enough recorded work yet to judge this farm.
          </Text>
        </View>
      )}

      {groups.map((g) => (
        <MetricGroup key={g.title} title={g.title} metrics={g.metrics} />
      ))}

      <Pressable onPress={() => setShowDefs((s) => !s)} style={styles.defsToggle} accessibilityRole="button">
        <Text variant="bodyBold" color={colors.primary}>How these are calculated</Text>
        <Ionicons name={showDefs ? 'chevron-up' : 'chevron-down'} size={16} color={colors.primary} />
      </Pressable>
      {showDefs ? (
        <View style={styles.defs}>
          {KPI_DEFINITIONS.map((d) => (
            <View key={d.title} style={styles.def}>
              <Text variant="bodyBold">{d.title}</Text>
              <Text variant="caption" color={colors.textSecondary}>{d.formula}</Text>
            </View>
          ))}
          <Text variant="caption" color={colors.textMuted}>
            Last 12 months · waiting period {report.assumptions.voluntary_waiting_period_days} days ·
            heifers eligible at {report.assumptions.heifer_breeding_age_days} days ·
            fewer than {report.assumptions.min_records_to_judge} records is shown but not judged.
          </Text>
        </View>
      ) : null}
    </Screen>
  );
}

const styles = StyleSheet.create({
  hero: { paddingTop: spacing.sm, paddingBottom: spacing.xl, gap: spacing.hairline },
  heroValue: { flexDirection: 'row', alignItems: 'baseline' },
  heroUnit: { marginLeft: spacing.xs },
  heroStatus: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, marginTop: spacing.xs },
  dot: { width: 8, height: 8, borderRadius: 4 },
  flex1: { flex: 1 },
  chartCard: {
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.lg,
    paddingTop: spacing.xl,
  },
  attention: {
    marginTop: spacing.xl,
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    paddingHorizontal: spacing.lg,
  },
  attentionRow: {
    flexDirection: 'row', alignItems: 'center', gap: spacing.md,
    paddingVertical: spacing.md, minHeight: 44,
  },
  attentionValue: { fontVariant: ['tabular-nums'] },
  allClear: {
    flexDirection: 'row', alignItems: 'center', gap: spacing.sm,
    marginTop: spacing.xl, paddingHorizontal: spacing.xs,
  },
  defsToggle: {
    flexDirection: 'row', alignItems: 'center', gap: spacing.xs,
    marginTop: spacing.xxl, minHeight: 44,
  },
  defs: { gap: spacing.lg, marginBottom: spacing.md },
  def: { gap: spacing.hairline },
});
