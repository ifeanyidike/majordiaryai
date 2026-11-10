import { Ionicons } from '@expo/vector-icons';
import React from 'react';
import { StyleSheet, View, ViewStyle } from 'react-native';
import { colors, onDark, radius, shadows, spacing, TileTone } from '@/theme';
import { IconCircle } from './IconCircle';
import { PressableScale } from './PressableScale';
import { Text } from './Text';

interface ActionCardProps {
  icon: keyof typeof Ionicons.glyphMap;
  label: string;
  sublabel?: string;
  onPress?: () => void;
  /** Icon colours; defaults to brand red on its soft tint. */
  tone?: TileTone;
  style?: ViewStyle;
  /** Unread count on the icon; hidden at 0. */
  badge?: number;
}

/** Dashboard quick-action tile — shared by all role dashboards. */
export function ActionCard({ icon, label, sublabel, onPress, tone, style, badge }: ActionCardProps) {
  return (
    <PressableScale
      onPress={onPress}
      style={[styles.card, style]}
      accessibilityRole="button"
      accessibilityLabel={sublabel ? `${label}. ${sublabel}` : label}
    >
      <View style={styles.iconWrap}>
        <IconCircle name={icon} size={52} color={tone?.fg ?? colors.primary}
                    bg={tone?.bg ?? colors.primarySoft} />
        {badge && badge > 0 ? (
          <View style={styles.badge}>
            <Text variant="label" color={onDark.text}>{badge > 99 ? '99+' : badge}</Text>
          </View>
        ) : null}
      </View>
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
  iconWrap: { alignSelf: 'flex-start' },
  badge: {
    position: 'absolute', top: -4, right: -6,
    minWidth: 22, height: 22, borderRadius: 11, paddingHorizontal: 6,
    backgroundColor: colors.danger, alignItems: 'center', justifyContent: 'center',
    borderWidth: 2, borderColor: colors.surface,
  },
});
