import * as Haptics from 'expo-haptics';
import React from 'react';
import { Pressable, PressableProps, StyleProp, ViewStyle } from 'react-native';
import Animated, {
  useAnimatedStyle,
  useSharedValue,
  withSpring,
} from 'react-native-reanimated';
import { useSettingsStore } from '@/store/useSettingsStore';

const AnimatedPressable = Animated.createAnimatedComponent(Pressable);

interface PressableScaleProps extends PressableProps {
  style?: StyleProp<ViewStyle>;
  haptic?: boolean;
  scaleTo?: number;
}

/** Pressable with spring scale feedback + optional haptic tick. */
export function PressableScale({
  style,
  haptic = true,
  scaleTo = 0.97,
  onPressIn,
  onPressOut,
  onPress,
  ...rest
}: PressableScaleProps) {
  const scale = useSharedValue(1);

  const animatedStyle = useAnimatedStyle(() => ({
    transform: [{ scale: scale.value }],
  }));

  return (
    <AnimatedPressable
      style={[animatedStyle, style]}
      onPressIn={(e) => {
        scale.value = withSpring(scaleTo, { damping: 20, stiffness: 400 });
        onPressIn?.(e);
      }}
      onPressOut={(e) => {
        scale.value = withSpring(1, { damping: 20, stiffness: 400 });
        onPressOut?.(e);
      }}
      onPress={(e) => {
        // The Settings toggle only wrote to a store nobody read, so turning
        // haptics off changed nothing. Read at press time, not at render, so
        // the switch takes effect without remounting the tree.
        if (haptic && useSettingsStore.getState().hapticsEnabled) {
          Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
        }
        onPress?.(e);
      }}
      {...rest}
    />
  );
}
