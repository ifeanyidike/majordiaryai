import { Ionicons } from '@expo/vector-icons';
import React from 'react';
import { StyleSheet, View } from 'react-native';
import { colors, spacing } from '@/theme';
import { IconCircle } from './IconCircle';
import { Text } from './Text';

interface EmptyStateProps {
  icon?: keyof typeof Ionicons.glyphMap;
  title: string;
  message?: string;
}

export function EmptyState({ icon = 'leaf-outline', title, message }: EmptyStateProps) {
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
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    alignItems: 'center',
    paddingVertical: spacing.huge,
    gap: spacing.sm,
  },
  title: { marginTop: spacing.sm },
  msg: { textAlign: 'center', maxWidth: 260 },
});
