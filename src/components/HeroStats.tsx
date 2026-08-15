import React from 'react';
import { StyleSheet, View, ViewStyle } from 'react-native';
import { onDark, radius, spacing } from '@/theme';
import { Text } from './Text';

export interface HeroStatItem {
  label: string;
  value: string | number;
}

interface HeroStatsProps {
  items: HeroStatItem[];
  /** 'panel' = light glass on charcoal heroes, 'scrim' = dark glass on red heroes */
  tone?: 'panel' | 'scrim';
  style?: ViewStyle;
}

/** The stat ribbon that sits at the bottom of hero headers — one look everywhere. */
export function HeroStats({ items, tone = 'panel', style }: HeroStatsProps) {
  const bg = tone === 'panel' ? onDark.panel : onDark.scrim;
  return (
    <View style={[styles.ribbon, { backgroundColor: bg, borderColor: onDark.panelBorder }, style]}>
      {items.map((item, i) => (
        <React.Fragment key={item.label}>
          {i > 0 && <View style={styles.divider} />}
          <View style={styles.item}>
            <Text variant="statSmall" color={onDark.text}>
              {String(item.value)}
            </Text>
            <Text variant="caption" color={onDark.textSecondary} numberOfLines={1}>
              {item.label}
            </Text>
          </View>
        </React.Fragment>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  ribbon: {
    flexDirection: 'row',
    borderRadius: radius.md,
    borderWidth: 1,
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.sm,
  },
  item: {
    flex: 1,
    alignItems: 'center',
    gap: spacing.hairline,
  },
  divider: {
    width: 1,
    backgroundColor: onDark.divider,
    marginVertical: spacing.xs,
  },
});
