import { Ionicons } from '@expo/vector-icons';
import { useLocalSearchParams } from 'expo-router';
import React, { useEffect, useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import {
  EmptyState, ErrorBanner, Header, Screen, SectionHeader, SkeletonList, SkeletonStats, Text,
} from '@/components';
import { BarChart } from '@/components/charts/BarChart';
import { KpiTile } from '@/components/charts/KpiTile';
import { colors, radius, spacing } from '@/theme';
import { KPI_DEFINITIONS, KpiReport } from '@/data/kpis';
import { farmById, useAppStore } from '@/store/useAppStore';

/**
 * One farm's reproduction performance.
 *
 * Leads with the one figure a breeding programme is judged on — the 21-day
 * pregnancy rate — then the two things it is made of (service rate and
 * conception rate), then timing, outcomes, and the compliance measures only
 * this system can compute because it knows which shots were given on which
 * day. Every judgement on this screen came from the server against published
 * benchmarks; the screen decides nothing about what is good.
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
        {!kpiError && (
          <View style={{ gap: spacing.xl, marginTop: spacing.lg }}>
            <SkeletonStats count={1} />
            <SkeletonList count={2} variant="card" />
            <SkeletonStats />
          </View>
        )}
      </Screen>
    );
  }

  const pr = report.pregnancy_rate_21d;
  const monthLabel = (ym: string) =>
    new Date(Number(ym.slice(0, 4)), Number(ym.slice(5, 7)) - 1, 1)
      .toLocaleDateString('en-CA', { month: 'short' });
  const cycleLabel = (start: string) =>
    new Date(start).toLocaleDateString('en-CA', { month: 'short', day: 'numeric' });

  const heroJudgement =
    pr.status === 'good' ? { color: colors.success, icon: 'checkmark-circle' as const, word: 'On target' }
    : pr.status === 'fair' ? { color: colors.warning, icon: 'remove-circle' as const, word: 'Below target' }
    : pr.status === 'poor' ? { color: colors.danger, icon: 'alert-circle' as const, word: 'Needs attention' }
    : { color: colors.textSecondary, icon: 'help-circle-outline' as const, word: 'Too few records to judge yet' };

  const buckets = report.timing.days_open.buckets;

  return (
    <Screen refreshing={kpiLoading} onRefresh={refresh}>
      <Header
        back
        title={farm.name}
        subtitle={`Performance · last ${Math.round(report.period_days / 30)} months`}
      />
      {kpiError ? <ErrorBanner message={kpiError} onRetry={refresh} /> : null}

      {/* Hero: the one number */}
      <View style={styles.hero}>
        <Text variant="label" color={colors.textSecondary}>21-day pregnancy rate</Text>
        <View style={styles.heroValue}>
          <Text variant="hero" color={pr.value == null ? colors.textMuted : colors.text}>
            {pr.value == null ? '—' : pr.value.toFixed(pr.value % 1 === 0 ? 0 : 1)}
          </Text>
          {pr.value != null ? <Text variant="title" color={colors.textSecondary}>%</Text> : null}
        </View>
        <View style={styles.heroJudge}>
          <Ionicons name={heroJudgement.icon} size={16} color={heroJudgement.color} />
          <Text variant="bodyBold" color={heroJudgement.color}>{heroJudgement.word}</Text>
          <Text variant="caption" color={colors.textMuted}>
            {' · '}{pr.target}
          </Text>
        </View>
        <Text variant="caption" color={colors.textMuted}>
          Over {report.cycles.filter((c) => !c.pending).length} confirmed cycles · {pr.n} eligible cow-cycles
        </Text>
      </View>

      <SectionHeader title="Pregnancy rate by 21-day cycle" />
      <View style={styles.chartCard}>
        <BarChart
          unit="%"
          height={140}
          benchmark={{ value: 20, label: 'Target 20%' }}
          data={report.cycles.map((c) => ({
            label: cycleLabel(c.start),
            value: c.pregnancy_rate,
            pending: c.pending,
            detail: `${c.conceived} of ${c.eligible} eligible · ${c.served} bred`,
          }))}
          pendingLabel="Checks not in yet"
        />
      </View>

      <SectionHeader title="What it is made of" />
      <View style={styles.tileRow}>
        <KpiTile label="Service rate" kpi={report.service_rate_21d}
          sublabel={`${report.service_rate_21d.n} eligible cow-cycles`} />
        <KpiTile label="Conception rate" kpi={report.conception.rate}
          sublabel={`${report.conception.rate.n} checked · ${report.conception.unchecked_breedings} awaiting`} />
      </View>
      <View style={styles.tileRow}>
        <KpiTile label="First-service conception" kpi={report.conception.first_service_rate}
          sublabel={`${report.conception.first_service_rate.n} first breedings`} />
        <KpiTile label="Services per conception" kpi={report.conception.services_per_conception}
          sublabel={`${report.conception.services_per_conception.n} pregnancies`} />
      </View>

      <SectionHeader title="Conception rate by month bred" />
      <View style={styles.chartCard}>
        <BarChart
          unit="%"
          height={130}
          benchmark={{ value: 40, label: 'Target 40%' }}
          data={report.conception.by_month.map((m) => ({
            label: monthLabel(m.month),
            value: m.checked ? m.rate : null,
            detail: `${m.pregnant} of ${m.checked} checked${m.unchecked ? ` · ${m.unchecked} awaiting` : ''}`,
          }))}
        />
      </View>

      <SectionHeader title="Timing" />
      <View style={styles.tileRow}>
        <KpiTile label="Days open (median)" kpi={report.timing.days_open}
          sublabel={report.timing.days_open.mean != null ? `mean ${report.timing.days_open.mean} · ${report.timing.days_open.n} pregnancies` : undefined} />
        <KpiTile label="Days to first service" kpi={report.timing.days_to_first_service}
          sublabel={`${report.timing.days_to_first_service.n} calvings`} />
      </View>
      <View style={styles.tileRow}>
        <KpiTile label="Calving interval" kpi={report.timing.calving_interval_months}
          sublabel={`${report.timing.calving_interval_months.n} cows with two calvings`} />
        <KpiTile label="Overdue pregnancy checks" kpi={report.outcomes.overdue_pregnancy_checks}
          sublabel="cows past day 50 with no result" />
      </View>

      {report.timing.days_open.n > 0 ? (
        <>
          <SectionHeader title="Days open distribution" />
          <View style={styles.chartCard}>
            <BarChart
              height={110}
              data={[
                { label: '<100', value: buckets.under_100 ?? 0 },
                { label: '100–130', value: buckets['100_130'] ?? 0 },
                { label: '131–160', value: buckets['131_160'] ?? 0 },
                { label: '>160', value: buckets.over_160 ?? 0 },
              ]}
            />
          </View>
        </>
      ) : null}

      <SectionHeader title="Outcomes" />
      <View style={styles.tileRow}>
        <KpiTile label="Stillbirth rate" kpi={report.outcomes.stillbirth_rate}
          sublabel={`${report.outcomes.calvings} calvings`} />
        <KpiTile label="Cull rate" kpi={report.outcomes.cull_rate}
          sublabel={`${report.outcomes.culls} culled`} />
      </View>
      <View style={styles.tileRow}>
        <KpiTile label="Heifers from sexed semen" kpi={report.outcomes.sexed_semen_heifer_rate}
          sublabel={`${report.outcomes.sexed_semen_heifer_rate.n} calves · expect ~90%`} />
        <KpiTile label="Heifers from conventional" kpi={report.outcomes.conventional_heifer_rate}
          sublabel={`${report.outcomes.conventional_heifer_rate.n} calves · expect ~48%`} />
      </View>

      <SectionHeader title="Protocol compliance" />
      <View style={styles.tileRow}>
        <KpiTile label="Shots on the scheduled day" kpi={report.compliance.protocol_on_time_rate}
          sublabel={`${report.compliance.protocol_on_time_rate.late} late · ${report.compliance.protocol_on_time_rate.missed} missed`} />
        <KpiTile label="Protocols completed" kpi={report.compliance.protocol_completion_rate}
          sublabel={`${report.compliance.protocol_completion_rate.cancelled} cancelled · ${report.compliance.protocol_completion_rate.active} running`} />
      </View>
      <View style={styles.tileRow}>
        <KpiTile label="Heat-check coverage" kpi={report.compliance.heat_check_coverage}
          sublabel={`${report.compliance.heat_check_coverage.n} breedings past day 25`} />
        <View style={styles.tileSpacer} />
      </View>

      {/* Definitions: professional means the maths is on the table */}
      <Pressable onPress={() => setShowDefs((s) => !s)} style={styles.defsToggle} accessibilityRole="button">
        <Ionicons name={showDefs ? 'chevron-up' : 'chevron-down'} size={16} color={colors.primary} />
        <Text variant="bodyBold" color={colors.primary}>How these are calculated</Text>
      </Pressable>
      {showDefs ? (
        <View style={styles.defs}>
          {KPI_DEFINITIONS.map((d) => (
            <View key={d.title} style={styles.def}>
              <Text variant="subheading">{d.title}</Text>
              <Text variant="caption" color={colors.textSecondary}>{d.formula}</Text>
              <Text variant="caption" color={colors.textMuted}>{d.why}</Text>
            </View>
          ))}
          <Text variant="caption" color={colors.textMuted}>
            Assumptions: voluntary waiting period {report.assumptions.voluntary_waiting_period_days} days ·
            heifers eligible from {report.assumptions.heifer_breeding_age_days} days old ·
            pregnancy checks expected within {report.assumptions.pregnancy_check_lag_days} days ·
            figures with fewer than {report.assumptions.min_records_to_judge} records are shown but not judged.
          </Text>
        </View>
      ) : null}
    </Screen>
  );
}

const styles = StyleSheet.create({
  hero: {
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.xxl,
    gap: spacing.xs,
    marginBottom: spacing.sm,
  },
  heroValue: { flexDirection: 'row', alignItems: 'baseline', gap: spacing.xs },
  heroJudge: { flexDirection: 'row', alignItems: 'center', gap: spacing.xs, flexWrap: 'wrap' },
  chartCard: {
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.lg,
    paddingTop: spacing.xl,
  },
  tileRow: { flexDirection: 'row', gap: spacing.sm, marginBottom: spacing.sm },
  tileSpacer: { flex: 1, minWidth: 150 },
  defsToggle: {
    flexDirection: 'row', alignItems: 'center', gap: spacing.xs,
    marginTop: spacing.xl, minHeight: 44,
  },
  defs: { gap: spacing.lg, marginTop: spacing.sm },
  def: { gap: spacing.hairline },
});
