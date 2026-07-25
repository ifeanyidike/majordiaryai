import { Ionicons } from '@expo/vector-icons';
import React from 'react';
import { ActivityIndicator, StyleProp, StyleSheet, ViewStyle } from 'react-native';
import { colors, onDark, radius, shadows, spacing, touch } from '@/theme';
import { PressableScale } from './PressableScale';
import { Text } from './Text';

type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'onDark' | 'danger';

interface ButtonProps {
  label: string;
  onPress?: () => void;
  variant?: ButtonVariant;
  icon?: keyof typeof Ionicons.glyphMap;
  loading?: boolean;
  disabled?: boolean;
  style?: StyleProp<ViewStyle>;
  compact?: boolean;
}

const variantStyles: Record<ButtonVariant, { container: ViewStyle; text: string }> = {
  primary: {
    container: { backgroundColor: colors.primary, ...shadows.hero },
    text: colors.textOnPrimary,
  },
  secondary: {
    container: {
      backgroundColor: colors.surface,
      borderWidth: 1.5,
      borderColor: colors.border,
      ...shadows.card,
    },
    text: colors.text,
  },
  ghost: {
    container: { backgroundColor: 'transparent' },
    text: colors.primary,
  },
  /** For use on the dark video overlay */
  onDark: {
    container: {
      backgroundColor: 'rgba(252, 251, 249, 0.14)',
      borderWidth: 1,
      borderColor: 'rgba(252, 251, 249, 0.35)',
    },
    text: onDark.text,
  },
  /** Destructive confirmations (cull, delete) */
  danger: {
    container: { backgroundColor: colors.danger, ...shadows.card },
    text: colors.textOnPrimary,
  },
};

export function Button({
  label,
  onPress,
  variant = 'primary',
  icon,
  loading,
  disabled,
  style,
  compact,
}: ButtonProps) {
  const v = variantStyles[variant];
  const blocked = Boolean(disabled || loading);
  return (
    <PressableScale
      onPress={blocked ? undefined : onPress}
      disabled={blocked}
      style={[styles.base, compact && styles.compact, v.container, disabled && styles.disabled, style]}
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityState={{ disabled: blocked, busy: Boolean(loading) }}
    >
      {loading ? (
        <ActivityIndicator color={v.text} />
      ) : (
        <>
          {icon ? <Ionicons name={icon} size={compact ? 18 : 22} color={v.text} /> : null}
          <Text variant={compact ? 'bodyBold' : 'subheading'} color={v.text}>
            {label}
          </Text>
        </>
      )}
    </PressableScale>
  );
}

const styles = StyleSheet.create({
  base: {
    height: touch.buttonHeight,
    borderRadius: radius.md,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.sm,
    paddingHorizontal: spacing.xl,
  },
  compact: {
    height: 44,
    paddingHorizontal: spacing.lg,
    borderRadius: radius.sm,
  },
  disabled: { opacity: 0.5 },
});
