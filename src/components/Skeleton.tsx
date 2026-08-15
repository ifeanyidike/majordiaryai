import { LinearGradient } from 'expo-linear-gradient';
import React, { useEffect } from 'react';
import { StyleProp, StyleSheet, View, ViewStyle } from 'react-native';
import Animated, {
  Easing,
  useAnimatedStyle,
  useSharedValue,
  withRepeat,
  withTiming,
  cancelAnimation,
} from 'react-native-reanimated';
import { colors, radius, spacing, useReduceMotion } from '@/theme';

/**
 * Loading placeholders shaped like the content that is coming.
 *
 * Thirteen screens showed a bare centred spinner while their data loaded. A
 * spinner communicates "something is happening somewhere"; it gives no sense
 * of how much is coming or where it will land, so the screen jumps when the
 * data arrives and every wait feels the same length. Placeholders in the shape
 * of the real rows read as "your list is loading, here it is", hold the layout
 * still, and make the wait feel shorter than it is.
 *
 * The sweep is a gradient translating across a muted bar — the same treatment
 * used by the platform's own loading states. With Reduce Motion on the sweep
 * stops and the bars simply sit there, which still holds the layout.
 */

const SWEEP_MS = 1200;

function Shimmer({ style }: { style?: StyleProp<ViewStyle> }) {
  const reduced = useReduceMotion();
  const progress = useSharedValue(0);

  useEffect(() => {
    if (reduced) return;
    progress.value = withRepeat(
      withTiming(1, { duration: SWEEP_MS, easing: Easing.inOut(Easing.ease) }),
      -1,
      false,
    );
    return () => cancelAnimation(progress);
  }, [reduced, progress]);

  const sweep = useAnimatedStyle(() => ({
    // Travels one full width beyond each edge so the highlight enters and
    // leaves cleanly instead of appearing mid-bar.
    transform: [{ translateX: (progress.value * 2 - 1) * 220 }],
  }));

  return (
    <View style={[styles.bar, style]}>
      {!reduced && (
        <Animated.View style={[StyleSheet.absoluteFill, sweep]}>
          <LinearGradient
            colors={['transparent', colors.surface, 'transparent']}
            start={{ x: 0, y: 0.5 }}
            end={{ x: 1, y: 0.5 }}
            style={StyleSheet.absoluteFill}
          />
        </Animated.View>
      )}
    </View>
  );
}

/** A single placeholder bar. `width` accepts a percentage or a number. */
export function Skeleton({
  width = '100%',
  height = 14,
  style,
}: {
  width?: number | `${number}%`;
  height?: number;
  style?: StyleProp<ViewStyle>;
}) {
  return <Shimmer style={[{ width, height, borderRadius: height / 2 }, style]} />;
}

/**
 * The shape of a list row: leading circle, two lines of text, trailing chevron.
 * Matches the farm, cow, vet and people rows closely enough that nothing moves
 * when the real data replaces it.
 */
export function SkeletonRow() {
  return (
    <View style={styles.row}>
      <Shimmer style={styles.avatar} />
      <View style={styles.rowText}>
        <Skeleton width="62%" height={15} />
        <Skeleton width="40%" height={12} />
      </View>
      <Skeleton width={16} height={16} />
    </View>
  );
}

/** The shape of a report/worklist card: title, action line, meta line. */
export function SkeletonCard() {
  return (
    <View style={styles.card}>
      <View style={styles.cardTop}>
        <Skeleton width="45%" height={17} />
        <Skeleton width={64} height={22} style={styles.pill} />
      </View>
      <Skeleton width="88%" height={14} />
      <Skeleton width="55%" height={12} />
    </View>
  );
}

/** The shape of the three-up stat strip under a hero header. */
export function SkeletonStats({ count = 3 }: { count?: number }) {
  return (
    <View style={styles.statRow}>
      {Array.from({ length: count }, (_, i) => (
        <View key={i} style={styles.stat}>
          <Skeleton width={44} height={24} />
          <Skeleton width="70%" height={11} />
        </View>
      ))}
    </View>
  );
}

/**
 * `count` placeholders of the given shape.
 *
 * Default 4: enough to fill the fold on a phone without implying a long list that
 * may turn out to be empty.
 */
export function SkeletonList({
  count = 4,
  variant = 'row',
}: {
  count?: number;
  variant?: 'row' | 'card';
}) {
  const Item = variant === 'card' ? SkeletonCard : SkeletonRow;
  return (
    <View
      style={styles.list}
      accessibilityRole="progressbar"
      accessibilityLabel="Loading"
    >
      {Array.from({ length: count }, (_, i) => (
        <Item key={i} />
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  bar: {
    backgroundColor: colors.surfaceSoft,
    overflow: 'hidden',
  },
  list: { gap: spacing.sm + 2 },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.lg,
    minHeight: 76,
  },
  avatar: { width: 44, height: 44, borderRadius: radius.pill },
  rowText: { flex: 1, gap: spacing.sm },
  card: {
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.lg,
    gap: spacing.sm + 2,
  },
  cardTop: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  pill: { borderRadius: radius.pill },
  statRow: { flexDirection: 'row', gap: spacing.sm },
  stat: {
    flex: 1,
    alignItems: 'center',
    gap: spacing.sm,
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    paddingVertical: spacing.lg,
    paddingHorizontal: spacing.sm,
  },
});
