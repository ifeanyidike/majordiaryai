import React from 'react';
import { StyleSheet, View } from 'react-native';
import { colors, spacing } from '@/theme';
import { Text } from './Text';

interface InfoRowProps {
  label: string;
  value?: string | number | null;
  /** Hide the row entirely when the value is empty */
  hideIfEmpty?: boolean;
}

/** Label/value row for detail screens — single source of truth, do not copy-paste. */
export function InfoRow({ label, value, hideIfEmpty }: InfoRowProps) {
  const display = value === null || value === undefined || value === '' ? null : String(value);
  if (!display && hideIfEmpty) return null;
  return (
    <View style={styles.row}>
      <Text variant="body" color={colors.textSecondary} style={styles.label}>
        {label}
      </Text>
      <Text variant="bodyBold" style={styles.value} numberOfLines={2}>
        {display ?? '—'}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    gap: spacing.lg,
    paddingVertical: spacing.sm + 2,
  },
  label: { flexShrink: 0 },
  value: { flex: 1, textAlign: 'right' },
});
