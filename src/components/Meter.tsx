import React, { useEffect } from 'react';
import { StyleSheet, View } from 'react-native';
import Animated, { useAnimatedStyle, useSharedValue, withTiming } from 'react-native-reanimated';
import { colors, duration, onDark, radius, useReduceMotion } from '@/theme';

interface MeterProps {
  /** A rate, 0 to 100. Null (no rate yet) shows an empty track. */
  value: number | null;
  /** 'light' on a white card, 'dark' on a charcoal panel. */
  tone?: 'light' | 'dark';
  color?: string;
  height?: number;
}

/** A rate drawn as a filled bar: how much of 100% it is. Grows into place. */
export function Meter({ value, tone = 'light', color = colors.primary, height = 8 }: MeterProps) {
  const reduced = useReduceMotion();
  const target = Math.max(0, Math.min(100, value ?? 0));
  const width = useSharedValue(0);

  useEffect(() => {
    width.value = withTiming(target, { duration: reduced ? 0 : duration.slow });
  }, [target, reduced, width]);

  const fill = useAnimatedStyle(() => ({ width: `${width.value}%` }));

  return (
    <View
      style={[
        styles.track,
        { height, backgroundColor: tone === 'dark' ? onDark.panel : colors.cream.mist },
      ]}
      // The number beside it is what a screen reader should say.
      importantForAccessibility="no-hide-descendants"
      accessibilityElementsHidden
    >
      <Animated.View style={[styles.fill, { backgroundColor: color }, fill]} />
    </View>
  );
}

const styles = StyleSheet.create({
  track: { width: '100%', borderRadius: radius.pill, overflow: 'hidden' },
  fill: { height: '100%', borderRadius: radius.pill },
});
