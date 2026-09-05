import { Ionicons } from '@expo/vector-icons';
import React from 'react';
import { StyleSheet, View, ViewStyle } from 'react-native';
import { colors, radius, shadows, spacing, status as statusColors } from '@/theme';
import { KpiStatus, KpiValue } from '@/data/kpis';
import { Text } from '../Text';

/**
 * One KPI: label, value, and a judgement the reader can trust.
 *
 * The judgement comes from the server against published benchmarks — the tile
 * never decides what is good. It is shown as an icon AND a word, never colour
 * alone, and "too few records" is a first-class state: three cows do not make
 * a conception rate, and a confident green on a sample of three would be the
 * dashboard lying.
 */

const JUDGEMENT: Record<KpiStatus, { icon: keyof typeof Ionicons.glyphMap; word: string; color: string }> = {
  good: { icon: 'checkmark-circle', word: 'Good', color: statusColors.pregnant.fg },
  fair: { icon: 'remove-circle', word: 'Fair', color: statusColors.open.fg },
  poor: { icon: 'alert-circle', word: 'Needs attention', color: colors.danger },
  na:   { icon: 'help-circle-outline', word: 'Too few records', color: colors.textSecondary },
  info: { icon: 'information-circle-outline', word: 'For reference', color: colors.textSecondary },
};

function format(value: number | null, unit: string): { main: string; unit: string } {
  if (value == null) return { main: '—', unit: '' };
  if (unit === '%') return { main: value.toFixed(value % 1 === 0 ? 0 : 1), unit: '%' };
  if (unit === 'ratio') return { main: value.toFixed(2), unit: '' };
  if (unit === 'months') return { main: value.toFixed(1), unit: ' mo' };
  if (unit === 'days') return { main: String(Math.round(value)), unit: ' d' };
  return { main: String(value), unit: '' };
}

interface Props {
  label: string;
  kpi: KpiValue;
  /** A second line under the value — the denominator in words, or a note. */
  sublabel?: string;
  style?: ViewStyle;
}

export function KpiTile({ label, kpi, sublabel, style }: Props) {
  const j = JUDGEMENT[kpi.status] ?? JUDGEMENT.na;
  const v = format(kpi.value, kpi.unit);
  const dim = kpi.status === 'na';
  return (
    <View style={[styles.card, style]} accessibilityLabel={`${label}: ${v.main}${v.unit}, ${j.word}`}>
      <Text variant="caption" color={colors.textSecondary} numberOfLines={2}>{label}</Text>
      <View style={styles.valueRow}>
        <Text variant="stat" color={dim ? colors.textMuted : colors.text}>{v.main}</Text>
        {v.unit ? <Text variant="bodyBold" color={dim ? colors.textMuted : colors.textSecondary}>{v.unit}</Text> : null}
      </View>
      {sublabel ? (
        <Text variant="caption" color={colors.textMuted} numberOfLines={1}>{sublabel}</Text>
      ) : null}
      <View style={styles.judgement}>
        <Ionicons name={j.icon} size={14} color={j.color} />
        <Text variant="caption" color={j.color} numberOfLines={1} style={styles.flex1}>
          {j.word}{kpi.status === 'na' && kpi.n ? ` (n=${kpi.n})` : ''}
        </Text>
      </View>
      {kpi.target ? (
        <Text variant="caption" color={colors.textMuted} numberOfLines={2} style={styles.target}>
          Target: {kpi.target}
        </Text>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    flex: 1,
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.lg,
    gap: spacing.xs,
    minWidth: 150,
    ...shadows.card,
  },
  valueRow: { flexDirection: 'row', alignItems: 'baseline', gap: spacing.hairline },
  judgement: { flexDirection: 'row', alignItems: 'center', gap: spacing.xs, marginTop: spacing.hairline },
  target: { marginTop: spacing.hairline },
  flex1: { flex: 1 },
});
