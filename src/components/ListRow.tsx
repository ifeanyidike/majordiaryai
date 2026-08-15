import { Ionicons } from '@expo/vector-icons';
import React from 'react';
import { StyleProp, StyleSheet, View, ViewStyle } from 'react-native';
import { colors, radius, shadows, spacing } from '@/theme';
import { IconCircle } from './IconCircle';
import { PressableScale } from './PressableScale';
import { Text } from './Text';

interface ListRowProps {
  title: string;
  subtitle?: string;
  icon?: keyof typeof Ionicons.glyphMap;
  iconColor?: string;
  iconBg?: string;
  right?: React.ReactNode;
  onPress?: () => void;
  chevron?: boolean;
  style?: StyleProp<ViewStyle>;
}

/** One-line tappable row used for farms, cows, reports lists. */
export function ListRow({
  title,
  subtitle,
  icon,
  iconColor,
  iconBg,
  right,
  onPress,
  chevron = true,
  style,
}: ListRowProps) {
  const content = (
    <>
      {icon ? <IconCircle name={icon} color={iconColor} bg={iconBg} /> : null}
      <View style={styles.textCol}>
        <Text variant="subheading" numberOfLines={1}>
          {title}
        </Text>
        {subtitle ? (
          <Text variant="caption" color={colors.textSecondary} numberOfLines={1}>
            {subtitle}
          </Text>
        ) : null}
      </View>
      {right}
      {onPress && chevron ? (
        <Ionicons name="chevron-forward" size={18} color={colors.textMuted} />
      ) : null}
    </>
  );

  if (onPress) {
    return (
      <PressableScale onPress={onPress} style={[styles.row, style]} scaleTo={0.98}>
        {content}
      </PressableScale>
    );
  }
  return <View style={[styles.row, style]}>{content}</View>;
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    minHeight: 64,
    marginBottom: spacing.sm + 2,
    ...shadows.card,
  },
  textCol: { flex: 1, gap: spacing.hairline },
});
