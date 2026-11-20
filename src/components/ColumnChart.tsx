import { LinearGradient } from 'expo-linear-gradient';
import React, { useEffect, useRef, useState } from 'react';
import { ScrollView, StyleSheet, View } from 'react-native';
import Animated, { useAnimatedStyle, useSharedValue, withDelay, withTiming } from 'react-native-reanimated';
import { alpha, colors, duration, radius, spacing, staggerFor, useReduceMotion } from '@/theme';
import { Text } from './Text';

export interface Column {
  key: string;
  /** Under the bar, e.g. "Mar". */
  label: string;
  /** A second line under the label, e.g. the year. */
  sublabel?: string;
  value: number;
  /** What a screen reader says for this column. */
  accessibilityLabel: string;
}

interface ColumnChartProps {
  columns: Column[];
  color?: string;
  /** Height of the tallest bar. */
  barHeight?: number;
  /** Narrower than this and the chart scrolls sideways instead. */
  minColumnWidth?: number;
}

/**
 * Counts over time as columns, the latest on the right, each count sitting on
 * its bar. All columns share the width when they fit. Past that the chart
 * shows as many whole columns as fit, opens on the latest, scrolls a column
 * at a time, and fades at the left edge while earlier ones are hidden.
 */
export function ColumnChart({
  columns, color = colors.primary, barHeight = 112, minColumnWidth = 34,
}: ColumnChartProps) {
  const [width, setWidth] = useState(0);
  const [atStart, setAtStart] = useState(false);
  const scroll = useRef<ScrollView>(null);
  const most = Math.max(1, ...columns.map((c) => c.value));
  const fits = Math.max(1, Math.floor(width / minColumnWidth));
  const scrolls = columns.length > fits;
  const columnWidth = width ? width / (scrolls ? fits : Math.max(1, columns.length)) : 0;

  return (
    <View onLayout={(e) => setWidth(e.nativeEvent.layout.width)}>
      {columnWidth ? (
        <ScrollView
          ref={scroll}
          horizontal
          scrollEnabled={scrolls}
          snapToInterval={scrolls ? columnWidth : undefined}
          decelerationRate="fast"
          showsHorizontalScrollIndicator={false}
          onContentSizeChange={() => scroll.current?.scrollToEnd({ animated: false })}
          scrollEventThrottle={32}
          onScroll={(e) => setAtStart(e.nativeEvent.contentOffset.x < columnWidth / 2)}
        >
          {columns.map((c, i) => (
            <View
              key={c.key}
              style={[styles.column, { width: columnWidth }]}
              accessible
              accessibilityLabel={c.accessibilityLabel}
            >
              <View style={[styles.slot, { height: barHeight + spacing.xxl }]}>
                <Text variant="caption" color={c.value ? colors.text : colors.textMuted} style={styles.count}>
                  {c.value}
                </Text>
                <Bar
                  height={c.value ? Math.max(6, (c.value / most) * barHeight) : 3}
                  color={c.value ? color : colors.cream.line}
                  width={Math.min(22, columnWidth - spacing.md)}
                  index={columns.length - 1 - i}
                />
              </View>
              <Text variant="caption" color={colors.textSecondary} numberOfLines={1}>{c.label}</Text>
              <Text variant="caption" color={colors.textMuted} numberOfLines={1}>
                {c.sublabel ?? ' '}
              </Text>
            </View>
          ))}
        </ScrollView>
      ) : null}
      {scrolls && !atStart ? (
        <LinearGradient
          colors={[colors.surface, alpha(colors.surface, 0)]}
          start={{ x: 0, y: 0 }}
          end={{ x: 1, y: 0 }}
          style={styles.fade}
          pointerEvents="none"
        />
      ) : null}
    </View>
  );
}

/** One column's bar, growing up from the baseline, the latest first. */
function Bar({ height, color, width, index }: { height: number; color: string; width: number; index: number }) {
  const reduced = useReduceMotion();
  const grown = useSharedValue(0);

  useEffect(() => {
    grown.value = reduced
      ? height
      : withDelay(staggerFor(index), withTiming(height, { duration: duration.slow }));
  }, [height, index, reduced, grown]);

  const style = useAnimatedStyle(() => ({ height: grown.value }));
  return <Animated.View style={[styles.bar, { width, backgroundColor: color }, style]} />;
}

const styles = StyleSheet.create({
  column: { alignItems: 'center' },
  slot: { justifyContent: 'flex-end', alignItems: 'center', marginBottom: spacing.sm },
  count: { marginBottom: spacing.xs },
  bar: { borderRadius: radius.sm / 2 },
  fade: { position: 'absolute', left: 0, top: 0, bottom: 0, width: spacing.xxl },
});
