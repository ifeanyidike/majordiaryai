import { useLocalSearchParams } from 'expo-router';
import React, { useEffect, useState } from 'react';
import { StyleSheet, View } from 'react-native';
import {
  Card, EmptyState, ErrorBanner, Header, InfoRow, Screen, SectionHeader, SkeletonList, Text,
} from '@/components';
import { colors, radius, spacing } from '@/theme';
import { farmById, useAppStore } from '@/store/useAppStore';
import { errorMessage } from '@/lib/api';

/**
 * KPI for one farm (Josh, Nov 20: "pick the 3 easiest ... make a page showing
 * raw data"). Each KPI as his "Major Dairy AI KPI" document defines it, with
 * its formula and the counts behind it, over every record the farm has (he
 * gives no period). Worked out by the server (services/farm_kpis.py).
 */

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const monthName = (ym: string) => {
  const [y, m] = ym.split('-').map(Number);
  return `${MONTHS[m - 1]} ${y}`;
};
const pct = (r: number | null) => (r == null ? '—' : `${r}%`);
const SEMEN: Record<string, string> = {
  sexed: 'Sexed Semen', conventional: 'Conventional', beef: 'Beef', 'not recorded': 'Not recorded',
};
/** Table cells stay on one line, shrinking a little on narrow phones, so a
 *  word such as "Inseminated" is never broken across two lines. */
const ONE_LINE = { numberOfLines: 1, adjustsFontSizeToFit: true, minimumFontScale: 0.7 } as const;

export default function FarmKpiScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const state = useAppStore();
  const farm = id ? farmById(state, id) : undefined;
  const kpis = id ? state.farmKpis[id] : undefined;
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    if (!id) return;
    setError(null);
    state.fetchFarmKpis(id).catch((e: any) => setError(errorMessage(e, 'Could not load the KPIs')));
  };
  useEffect(load, [id]);

  if (!farm) {
    return (
      <Screen>
        <Header back title="KPI" />
        <EmptyState title="Farm not found" />
      </Screen>
    );
  }

  const most = kpis ? Math.max(1, ...kpis.pregnancies_by_month.map((m) => m.pregnant)) : 1;

  return (
    <Screen>
      <Header back title="KPI" subtitle={farm.name} />
      {error ? <ErrorBanner message={error} onRetry={load} /> : null}
      {!kpis ? (
        error ? null : <View style={{ marginTop: spacing.lg }}><SkeletonList count={3} variant="card" /></View>
      ) : (
        <>
          <SectionHeader title="Conception Rate" />
          <Card style={styles.card}>
            <Text variant="caption" color={colors.textSecondary} style={styles.formula}>
              Confirmed Pregnancies ÷ Total Inseminations
            </Text>
            <InfoRow label="Inseminated" value={String(kpis.conception.inseminated)} />
            <InfoRow label="Pregnant" value={String(kpis.conception.pregnant)} />
            <View style={styles.result}>
              <Text variant="bodyBold">Conception Rate</Text>
              <Text variant="title" color={colors.primary}>{pct(kpis.conception.rate)}</Text>
            </View>
          </Card>

          <SectionHeader title="Hard Pregnancy Count (by Month)" />
          <Card style={styles.card}>
            <Text variant="caption" color={colors.textSecondary} style={styles.formula}>
              Count of confirmed pregnancies by month
            </Text>
            {kpis.pregnancies_by_month.length === 0 ? (
              <Text variant="body" color={colors.textMuted}>No confirmed pregnancies yet.</Text>
            ) : kpis.pregnancies_by_month.map((m) => (
              <View key={m.month} style={styles.monthRow}>
                <Text variant="body" style={styles.monthName}>{monthName(m.month)}</Text>
                <View style={styles.barTrack}>
                  <View style={[styles.bar, { width: `${(m.pregnant / most) * 100}%` }]} />
                </View>
                <Text variant="bodyBold" style={styles.monthCount}>{m.pregnant}</Text>
              </View>
            ))}
          </Card>

          <SectionHeader title="Pregnancy by Semen Type" />
          <Card style={styles.card}>
            <Text variant="caption" color={colors.textSecondary} style={styles.formula}>
              Pregnancies ÷ Inseminations using semen type
            </Text>
            {kpis.by_semen.length === 0 ? (
              <Text variant="body" color={colors.textMuted}>No inseminations recorded yet.</Text>
            ) : (
              <>
                <View style={styles.tableRow}>
                  {['Semen Type', 'Inseminated', 'Pregnant', 'Rate'].map((h, i) => (
                    <Text key={h} variant="caption" color={colors.textSecondary} {...ONE_LINE}
                          style={i === 0 ? styles.cellWide : styles.cell}>{h}</Text>
                  ))}
                </View>
                {kpis.by_semen.map((s) => (
                  <View key={s.semen_type} style={[styles.tableRow, styles.tableDivider]}>
                    <Text variant="body" {...ONE_LINE} style={styles.cellWide}>
                      {SEMEN[s.semen_type] ?? s.semen_type}
                    </Text>
                    <Text variant="body" {...ONE_LINE} style={styles.cell}>{s.inseminated}</Text>
                    <Text variant="body" {...ONE_LINE} style={styles.cell}>{s.pregnant}</Text>
                    <Text variant="bodyBold" color={colors.primary} {...ONE_LINE} style={styles.cell}>
                      {pct(s.rate)}
                    </Text>
                  </View>
                ))}
              </>
            )}
          </Card>
        </>
      )}
    </Screen>
  );
}

const styles = StyleSheet.create({
  card: { paddingVertical: spacing.md, gap: spacing.xs },
  formula: { marginBottom: spacing.sm },
  result: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    marginTop: spacing.sm, paddingTop: spacing.sm,
    borderTopWidth: 1, borderTopColor: colors.border,
  },
  monthRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.md, paddingVertical: 2 },
  monthName: { width: 76 },
  barTrack: { flex: 1, height: 10, borderRadius: radius.pill, backgroundColor: colors.primarySoft },
  bar: { height: 10, borderRadius: radius.pill, backgroundColor: colors.primary },
  monthCount: { width: 28, textAlign: 'right' },
  tableRow: { flexDirection: 'row', alignItems: 'center', paddingVertical: spacing.xs },
  tableDivider: { borderTopWidth: 1, borderTopColor: colors.border },
  cellWide: { flex: 1.6 },
  cell: { flex: 1, textAlign: 'right' },
});
