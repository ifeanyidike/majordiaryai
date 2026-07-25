import React from 'react';
import { StyleSheet, View, ViewStyle } from 'react-native';
import { colors, radius, shadows, spacing } from '@/theme';
import { Text } from './Text';

interface StatCardProps {
  value: string | number;
  label: string;
  /** Optional signal color — rendered as a small dot next to the label */
  accent?: string;
  style?: ViewStyle;
}

/**
 * Compact stat tile for summary grids.
 * Clean single surface: big charcoal number, quiet label,
 * accent color reduced to a small status dot.
 */
export function StatCard({ value, label, accent, style }: StatCardProps) {
  return (
    <View style={[styles.card, style]}>
      <Text variant="stat">{value}</Text>
      <View style={styles.labelRow}>
        {accent ? <View style={[styles.dot, { backgroundColor: accent }]} /> : null}
        <Text variant="caption" color={colors.textSecondary} numberOfLines={1}>
          {label}
        </Text>
      </View>
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
    paddingVertical: spacing.lg,
    paddingHorizontal: spacing.md,
    alignItems: 'center',
    gap: 3,
    ...shadows.card,
  },
  labelRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs + 1,
  },
  dot: {
    width: 6,
    height: 6,
    borderRadius: 3,
  },
});
