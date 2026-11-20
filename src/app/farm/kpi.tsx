import { useLocalSearchParams } from 'expo-router';
import React, { useCallback, useEffect, useState } from 'react';
import { StyleSheet, View } from 'react-native';
import Animated from 'react-native-reanimated';
import {
  Card, ColumnChart, EmptyState, ErrorBanner, FocusedStatusBar, Header, HeroHeader, HeroStats,
  Meter, Screen, SectionHeader, SkeletonList, Text,
} from '@/components';
import type { Column } from '@/components';
import { colors, gradients, onDark, spacing, useMotion } from '@/theme';
import { farmById, useAppStore } from '@/store/useAppStore';
import { errorMessage } from '@/lib/api';

/**
 * KPI for one farm (Josh, Nov 20: "pick the 3 easiest ... make a page showing
 * raw data"). Each KPI as his "Major Dairy AI KPI" document defines it, with
 * its formula and the counts behind it, over every record the farm has (he
 * gives no period). Worked out by the server (services/farm_kpis.py).
 *
 * An analytics screen, so it wears the charcoal hero of the analytics family;
 * the headline KPI lives in it, the two breakdowns below.
 */

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const MONTHS_LONG = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August',
  'September', 'October', 'November', 'December'];
const SEMEN: Record<string, string> = {
  sexed: 'Sexed Semen', conventional: 'Conventional', beef: 'Beef', 'not recorded': 'Not recorded',
};

const pct = (r: number | null) => (r == null ? '—' : `${r}%`);
const plural = (n: number, one: string, many: string) => (n === 1 ? one : many);

function monthParts(ym: string) {
  const [y, m] = ym.split('-').map(Number);
  return { year: y, month: m };
}

/**
 * One column per month. The year sits under the first month, each January and
 * the latest month, so the part of a long chart on screen always shows one.
 */
function monthColumns(months: { month: string; pregnant: number }[]): Column[] {
  return months.map((m, i) => {
    const { year, month } = monthParts(m.month);
    return {
      key: m.month,
      label: MONTHS[month - 1],
      sublabel: i === 0 || month === 1 || i === months.length - 1 ? String(year) : undefined,
      value: m.pregnant,
      accessibilityLabel: `${MONTHS_LONG[month - 1]} ${year}: ${m.pregnant} confirmed `
        + plural(m.pregnant, 'pregnancy', 'pregnancies'),
    };
  });
}

export default function FarmKpiScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const state = useAppStore();
  const fetchFarmKpis = useAppStore((s) => s.fetchFarmKpis);
  const motion = useMotion();
  const farm = id ? farmById(state, id) : undefined;
  const kpis = id ? state.farmKpis[id] : undefined;
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  // The error stays up until a load succeeds, so a retry does not flicker it.
  const load = useCallback(() => {
    if (!id) return Promise.resolve();
    return fetchFarmKpis(id)
      .then(() => setError(null))
      .catch((e: any) => setError(errorMessage(e, 'Could not load the KPIs')));
  }, [id, fetchFarmKpis]);
  useEffect(() => { load(); }, [load]);
  const refresh = () => {
    setRefreshing(true);
    load().finally(() => setRefreshing(false));
  };

  if (!farm) {
    return (
      <Screen>
        <Header back title="KPI" />
        <EmptyState title="Farm not found" />
      </Screen>
    );
  }

  const conception = kpis?.conception;
  const rate = conception?.rate ?? null;
  const months = kpis?.pregnancies_by_month ?? [];
  const confirmed = months.reduce((n, m) => n + m.pregnant, 0);
  const since = months.length ? monthParts(months[0].month) : null;

  return (
    <Screen padded={false} topInset={false} refreshing={refreshing} onRefresh={refresh}>
      <FocusedStatusBar style="light" />
      <HeroHeader gradient={gradients.charcoal} back>
        <Animated.View
          entering={motion.downAt(0, 500)}
          accessible
          accessibilityLabel={`Conception rate${rate == null ? ' not known yet' : `, ${rate} percent`}`}
        >
          <Text variant="label" color={onDark.textMuted}>KPI · {farm.name}</Text>
          <Text variant="heading" color={onDark.text} style={styles.heroTitle}>Conception Rate</Text>
          <View style={styles.rateRow}>
            <Text variant="metric" color={rate == null ? onDark.textMuted : onDark.text}>
              {rate == null ? '—' : String(rate)}
            </Text>
            {rate == null ? null : (
              <Text variant="title" color={onDark.textSecondary} style={styles.percent}>%</Text>
            )}
          </View>
          <Meter value={rate} tone="dark" color={colors.red[400]} height={10} />
          <Text variant="caption" color={onDark.textSecondary} style={styles.heroFormula}>
            Confirmed Pregnancies ÷ Total Inseminations
          </Text>
        </Animated.View>
        <Animated.View entering={motion.downAt(120, 500)} style={styles.heroStats}>
          <HeroStats
            tone="panel"
            items={[
              { value: conception ? conception.inseminated : '—', label: 'Inseminated' },
              { value: conception ? conception.pregnant : '—', label: 'Pregnant' },
            ]}
          />
        </Animated.View>
      </HeroHeader>

      <View style={styles.body}>
        {error ? <ErrorBanner message={error} onRetry={load} /> : null}
        {!kpis ? (
          error ? null : <SkeletonList count={2} variant="card" />
        ) : (
          <>
            <Animated.View entering={motion.up(0)}>
              <SectionHeader title="Hard Pregnancy Count" />
              <Card style={styles.card}>
                <View style={styles.countHead}>
                  <Text variant="stat">{confirmed}</Text>
                  <Text variant="caption" color={colors.textSecondary} style={styles.flex1}>
                    {plural(confirmed, 'confirmed pregnancy', 'confirmed pregnancies')}
                    {since ? ` since ${MONTHS_LONG[since.month - 1]} ${since.year}` : ''}
                  </Text>
                </View>
                <Text variant="caption" color={colors.textMuted} style={styles.formula}>
                  Count of confirmed pregnancies by month
                </Text>
                {months.length ? (
                  <ColumnChart columns={monthColumns(months)} />
                ) : (
                  <Text variant="body" color={colors.textMuted}>No confirmed pregnancies yet.</Text>
                )}
              </Card>
            </Animated.View>

            <Animated.View entering={motion.up(1)}>
              <SectionHeader title="Pregnancy by Semen Type" />
              <Card style={styles.card}>
                <Text variant="caption" color={colors.textMuted} style={styles.formula}>
                  Pregnancies ÷ Inseminations using semen type
                </Text>
                {kpis.by_semen.length === 0 ? (
                  <Text variant="body" color={colors.textMuted}>No inseminations recorded yet.</Text>
                ) : kpis.by_semen.map((s, i) => {
                  const name = SEMEN[s.semen_type] ?? s.semen_type;
                  // No semen type on the breeding: shown, but quieter than the real types.
                  const quiet = s.semen_type === 'not recorded';
                  return (
                    <View
                      key={s.semen_type}
                      style={[styles.semenRow, i > 0 && styles.divider]}
                      accessible
                      accessibilityLabel={`${name}: ${s.inseminated} inseminated, ${s.pregnant} pregnant, `
                        + (s.rate == null ? 'no rate yet' : `${s.rate} percent`)}
                    >
                      <View style={styles.semenTop}>
                        <Text variant="bodyBold" color={quiet ? colors.textSecondary : colors.text}
                              style={styles.flex1} numberOfLines={1}>
                          {name}
                        </Text>
                        <Text variant="statSmall" color={quiet ? colors.textSecondary : colors.primary}>
                          {pct(s.rate)}
                        </Text>
                      </View>
                      <Meter value={s.rate} color={quiet ? colors.charcoal[300] : colors.primary} />
                      <Text variant="caption" color={colors.textSecondary}>
                        {s.inseminated} inseminated · {s.pregnant} pregnant
                      </Text>
                    </View>
                  );
                })}
              </Card>
            </Animated.View>

            <Text variant="caption" color={colors.textMuted} style={styles.note}>
              A pregnancy counts once a pregnancy check says pregnant. Every insemination on
              this farm is counted.
            </Text>
          </>
        )}
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  flex1: { flex: 1 },
  heroTitle: { marginTop: spacing.xs },
  rateRow: { flexDirection: 'row', alignItems: 'flex-end', marginTop: spacing.sm, marginBottom: spacing.md },
  percent: { marginLeft: spacing.xs, marginBottom: spacing.sm },
  heroFormula: { marginTop: spacing.sm },
  heroStats: { marginTop: spacing.xxl },
  body: { paddingHorizontal: spacing.xl, marginTop: -spacing.lg },
  card: { gap: spacing.md },
  countHead: { flexDirection: 'row', alignItems: 'baseline', gap: spacing.sm },
  formula: { marginTop: -spacing.sm },
  semenRow: { gap: spacing.sm, paddingVertical: spacing.sm },
  divider: { borderTopWidth: 1, borderTopColor: colors.border, paddingTop: spacing.md },
  semenTop: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  note: { marginTop: spacing.lg, marginBottom: spacing.xxl, textAlign: 'center' },
});
