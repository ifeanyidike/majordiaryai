import React from 'react';
import { Pressable, ScrollView, StyleSheet, View, ViewStyle } from 'react-native';
import { colors, radius, spacing } from '@/theme';
import { Text } from './Text';

export interface FilterChip<T extends string> {
  value: T;
  label: string;
  /** Shown after the label, e.g. how many cows the filter would leave. */
  count?: number;
}

/**
 * One row of single-select filter chips that scrolls sideways when it runs
 * out of room — herd filters by status and by days in milk.
 */
export function FilterChips<T extends string>({
  label, chips, value, onChange, style,
}: {
  label?: string;
  chips: readonly FilterChip<T>[];
  value: T;
  onChange: (value: T) => void;
  style?: ViewStyle;
}) {
  return (
    <View style={style}>
      {label ? (
        <Text variant="label" color={colors.textSecondary} style={styles.label}>
          {label}
        </Text>
      ) : null}
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={styles.row}
        accessibilityRole="radiogroup"
      >
        {chips.map((chip) => {
          const selected = chip.value === value;
          return (
            <Pressable
              key={chip.value}
              onPress={() => onChange(chip.value)}
              style={[styles.chip, selected && styles.chipSelected]}
              accessibilityRole="radio"
              accessibilityState={{ selected }}
              accessibilityLabel={chip.count === undefined ? chip.label : `${chip.label}, ${chip.count}`}
            >
              <Text variant="caption" color={selected ? colors.textOnPrimary : colors.text}>
                {chip.label}
              </Text>
              {chip.count !== undefined ? (
                <Text variant="caption" color={selected ? colors.textOnPrimary : colors.textMuted}>
                  {chip.count}
                </Text>
              ) : null}
            </Pressable>
          );
        })}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  label: { marginBottom: spacing.xs },
  row: { gap: spacing.xs, paddingRight: spacing.xl },
  chip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    minHeight: 36,
    paddingHorizontal: spacing.md,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  chipSelected: {
    backgroundColor: colors.primary,
    borderColor: colors.primary,
  },
});
