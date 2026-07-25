import { Ionicons } from '@expo/vector-icons';
import React, { useEffect } from 'react';
import { StyleSheet, View } from 'react-native';
import Animated, { FadeInUp, FadeOutUp } from 'react-native-reanimated';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { create } from 'zustand';
import { charcoal, colors, radius, red, shadows, spacing, status } from '@/theme';
import { Text } from './Text';

type ToastVariant = 'info' | 'success' | 'error';

interface ToastState {
  message: string | null;
  icon: keyof typeof Ionicons.glyphMap;
  variant: ToastVariant;
  show: (
    message: string,
    icon?: keyof typeof Ionicons.glyphMap,
    variant?: ToastVariant,
  ) => void;
  success: (message: string) => void;
  error: (message: string) => void;
  hide: () => void;
}

export const useToast = create<ToastState>((set) => ({
  message: null,
  icon: 'information-circle',
  variant: 'info',
  show: (message, icon = 'information-circle', variant = 'info') =>
    set({ message, icon, variant }),
  success: (message) => set({ message, icon: 'checkmark-circle', variant: 'success' }),
  error: (message) => set({ message, icon: 'alert-circle', variant: 'error' }),
  hide: () => set({ message: null }),
}));

const ACCENT: Record<ToastVariant, string> = {
  info: colors.cream.base,
  success: status.pregnant.fg,
  error: red[400],
};

/** Mount once in the root layout. Trigger with useToast.getState().show(...) */
export function ToastHost() {
  const { message, icon, variant, hide } = useToast();
  const insets = useSafeAreaInsets();

  useEffect(() => {
    if (!message) return;
    const t = setTimeout(hide, variant === 'error' ? 3800 : 2600);
    return () => clearTimeout(t);
  }, [message, variant, hide]);

  if (!message) return null;

  return (
    <Animated.View
      entering={FadeInUp.springify().damping(18)}
      exiting={FadeOutUp}
      style={[styles.toast, { top: insets.top + spacing.sm }]}
      pointerEvents="none"
      accessibilityLiveRegion="polite"
    >
      <View style={[styles.accent, { backgroundColor: ACCENT[variant] }]} />
      <Ionicons name={icon} size={20} color={ACCENT[variant]} />
      <Text variant="bodyBold" color={colors.cream.base} style={styles.text}>
        {message}
      </Text>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  toast: {
    position: 'absolute',
    left: spacing.xl,
    right: spacing.xl,
    backgroundColor: charcoal[800],
    borderRadius: radius.md,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md + 2,
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    overflow: 'hidden',
    ...shadows.raised,
  },
  accent: {
    position: 'absolute',
    left: 0,
    top: 0,
    bottom: 0,
    width: 4,
  },
  text: { flex: 1 },
});
