import { Ionicons } from '@expo/vector-icons';
import React from 'react';
import { StyleSheet, View, ViewStyle } from 'react-native';
import { colors, radius, shadows, spacing } from '@/theme';
import { IconCircle } from './IconCircle';
import { PressableScale } from './PressableScale';
import { Text } from './Text';

interface ActionCardProps {
  icon: keyof typeof Ionicons.glyphMap;
  label: string;
  sublabel?: string;
  onPress?: () => void;
  tint?: string;
  style?: ViewStyle;
}

/** Dashboard quick-action tile — shared by all role dashboards. */
export function ActionCard({ icon, label, sublabel, onPress, tint = colors.primary, style }: ActionCardProps) {
  return (
    <PressableScale
      onPress={onPress}
      style={[styles.card, style]}
      accessibilityRole="button"
      accessibilityLabel={sublabel ? `${label}. ${sublabel}` : label}
    >
      <IconCircle name={icon} size={52} color={tint} bg={colors.primarySoft} />
      <View>
        <Text variant="heading" numberOfLines={1}>
          {label}
        </Text>
        {sublabel ? (
          <Text variant="caption" color={colors.textSecondary} numberOfLines={2}>
            {sublabel}
          </Text>
        ) : null}
      </View>
    </PressableScale>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.xl,
    gap: spacing.lg,
    minHeight: 150,
    justifyContent: 'space-between',
    ...shadows.raised,
  },
});
