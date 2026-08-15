import { Ionicons } from '@expo/vector-icons';
import React from 'react';
import { StyleSheet, View } from 'react-native';
import { colors, spacing } from '@/theme';
import { Button } from './Button';
import { IconCircle } from './IconCircle';
import { Text } from './Text';

interface EmptyStateProps {
  icon?: keyof typeof Ionicons.glyphMap;
  title: string;
  message?: string;
  /**
   * The way out.
   *
   * An empty state without one is a dead end: it tells the user there is
   * nothing here and leaves them to work out what to do about it, which on a
   * screen like "No farms assigned yet" is the difference between an app that
   * is empty and an app that looks broken.
   */
  action?: { label: string; icon?: keyof typeof Ionicons.glyphMap; onPress: () => void };
}

export function EmptyState({
  icon = 'leaf-outline', title, message, action,
}: EmptyStateProps) {
  return (
    <View style={styles.wrap}>
      <IconCircle name={icon} size={64} color={colors.textMuted} bg={colors.surfaceSoft} />
      <Text variant="heading" style={styles.title}>
        {title}
      </Text>
      {message ? (
        <Text variant="body" color={colors.textSecondary} style={styles.msg}>
          {message}
        </Text>
      ) : null}
      {action ? (
        <Button
          compact
          variant="secondary"
          label={action.label}
          icon={action.icon}
          onPress={action.onPress}
          style={styles.action}
        />
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    alignItems: 'center',
    paddingVertical: spacing.huge,
    gap: spacing.sm,
  },
  title: { marginTop: spacing.sm, textAlign: 'center' },
  msg: { textAlign: 'center', maxWidth: 280 },
  action: { marginTop: spacing.md },
});
