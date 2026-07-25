import React from 'react';
import { StyleSheet, View, ViewStyle } from 'react-native';
import { radius, spacing, status, statusFallback, StatusKey } from '@/theme';
import { Text } from './Text';

const LABELS: Record<StatusKey, string> = {
  pregnant:    'Pregnant',
  open:        'Open',
  inseminated: 'Inseminated',
  dry:         'Dry',
  fresh:       'Fresh',
  cull:        'Cull',
  heat:        'In Heat',
  needling:    'Needling',
  calf:        'Calf',
  heifer:      'Heifer',
  calving:     'Calving',
  sold:        'Sold',
  dead:        'Dead',
};

interface StatusPillProps {
  /** Accepts unknown strings from the API and renders a neutral fallback */
  kind: StatusKey | string;
  label?: string;
  style?: ViewStyle;
}

export function StatusPill({ kind, label, style }: StatusPillProps) {
  const known = kind in status;
  const c = known ? status[kind as StatusKey] : statusFallback;
  const fallbackLabel = known
    ? LABELS[kind as StatusKey]
    : kind.charAt(0).toUpperCase() + kind.slice(1);
  return (
    <View style={[styles.pill, { backgroundColor: c.bg }, style]}>
      <View style={[styles.dot, { backgroundColor: c.fg }]} />
      <Text variant="label" color={c.fg}>
        {label ?? fallbackLabel}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  pill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs + 2,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs + 2,
    borderRadius: radius.pill,
    alignSelf: 'flex-start',
  },
  dot: { width: 6, height: 6, borderRadius: 3 },
});
