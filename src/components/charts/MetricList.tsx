import React, { useState } from 'react';
import { LayoutAnimation, Platform, Pressable, StyleSheet, UIManager, View } from 'react-native';
import { charcoal, colors, radius, spacing, status as statusColors } from '@/theme';
import { KpiStatus, KpiValue } from '@/data/kpis';
import { Text } from '../Text';

/**
 * A quiet, dense list of figures — the alternative to a wall of stat cards.
 *
 * Fourteen bordered tiles, each carrying a label, a value, a denominator, a
 * judgement word AND a target sentence, is five lines of text fourteen times
 * over. Everything shouted equally, so nothing read. A metric is a ROW here:
 * name on the left, number on the right, a small status mark between them.
 * The target and the denominator are one tap away, which is where reference
 * material belongs — available, not shouted.
 *
 * Colour is never the only channel: the row's accessibility label carries the
 * judgement in words, tapping shows it, and anything not "good" is named
 * outright in the Needs attention block above the list.
 */

if (Platform.OS === 'android' && UIManager.setLayoutAnimationEnabledExperimental) {
  UIManager.setLayoutAnimationEnabledExperimental(true);
}

export const STATUS_COLOR: Record<KpiStatus, string> = {
  good: statusColors.pregnant.fg,
  fair: statusColors.open.fg,
  poor: colors.danger,
  na: charcoal[200],
  info: charcoal[200],
};

export const STATUS_WORD: Record<KpiStatus, string> = {
  good: 'On target',
  fair: 'Below target',
  poor: 'Needs attention',
  na: 'Too few records',
  info: 'For reference',
};

export function formatKpi(kpi: KpiValue): string {
  const { value, unit } = kpi;
  if (value == null) return '—';
  if (unit === '%') return `${value % 1 === 0 ? value : value.toFixed(1)}%`;
  if (unit === 'ratio') return value.toFixed(2);
  if (unit === 'months') return `${value.toFixed(1)} mo`;
  if (unit === 'days') return `${Math.round(value)} d`;
  return String(value);
}

export interface Metric {
  label: string;
  kpi: KpiValue;
  /** What the figure is computed over — shown when the row is opened. */
  basis?: string;
}

export function MetricGroup({ title, metrics }: { title: string; metrics: Metric[] }) {
  return (
    <View style={styles.group}>
      <Text variant="label" color={colors.textMuted} style={styles.groupTitle}>
        {title}
      </Text>
      <View style={styles.card}>
        {metrics.map((m, i) => (
          <MetricRow key={m.label} metric={m} first={i === 0} />
        ))}
      </View>
    </View>
  );
}

function MetricRow({ metric, first }: { metric: Metric; first: boolean }) {
  const [open, setOpen] = useState(false);
  const { label, kpi, basis } = metric;
  const dim = kpi.value == null || kpi.status === 'na';

  const toggle = () => {
    LayoutAnimation.configureNext(LayoutAnimation.Presets.easeInEaseOut);
    setOpen((o) => !o);
  };

  return (
    <Pressable
      onPress={toggle}
      style={[styles.row, !first && styles.divider]}
      accessibilityRole="button"
      accessibilityState={{ expanded: open }}
      accessibilityLabel={`${label}, ${formatKpi(kpi)}, ${STATUS_WORD[kpi.status]}`}
    >
      <View style={styles.rowMain}>
        <View style={[styles.dot, { backgroundColor: STATUS_COLOR[kpi.status] }]} />
        <Text variant="body" color={colors.text} style={styles.flex1} numberOfLines={1}>
          {label}
        </Text>
        <Text
          variant="bodyBold"
          color={dim ? colors.textMuted : colors.text}
          style={styles.value}
        >
          {formatKpi(kpi)}
        </Text>
      </View>
      {open ? (
        <View style={styles.detail}>
          <Text variant="caption" color={colors.textSecondary}>
            {STATUS_WORD[kpi.status]}
            {kpi.target ? ` · target ${kpi.target}` : ''}
          </Text>
          {basis ? (
            <Text variant="caption" color={colors.textMuted}>{basis}</Text>
          ) : null}
        </View>
      ) : null}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  group: { marginTop: spacing.xxl },
  groupTitle: { marginBottom: spacing.sm, marginLeft: spacing.xs },
  card: {
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    paddingHorizontal: spacing.lg,
  },
  row: { paddingVertical: spacing.md, minHeight: 48, justifyContent: 'center' },
  divider: { borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border },
  rowMain: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  dot: { width: 7, height: 7, borderRadius: 4 },
  flex1: { flex: 1 },
  value: { fontVariant: ['tabular-nums'] },
  detail: { paddingLeft: spacing.lg + spacing.hairline, paddingTop: spacing.xs, gap: 1 },
});
