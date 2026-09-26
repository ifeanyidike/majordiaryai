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
        {/* Shrink rather than truncate: "Tracked Co…" told nobody anything. */}
        <Text variant="caption" color={colors.textSecondary} numberOfLines={1}
          adjustsFontSizeToFit minimumFontScale={0.75} style={styles.labelText}>
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
    gap: spacing.hairline,
    ...shadows.card,
  },
  labelText: { flexShrink: 1 },
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
