import React from 'react';
import { StyleSheet, View } from 'react-native';
import { colors, radius, spacing } from '@/theme';
import { Text } from './Text';
import { YesNoField } from './YesNoField';

/**
 * A tag already on the farm is usually a typing mistake, but real herds reuse
 * them (Josh's test results, Nov 5). The server says when it happens; this asks.
 */
export function SharedTagQuestion({ tag, value, onChange }: {
  tag: string;
  value: boolean | null;
  onChange: (sure: boolean) => void;
}) {
  return (
    <View style={styles.box}>
      <Text variant="bodyBold">Tag {tag} is already on this farm.</Text>
      <Text variant="caption" color={colors.textSecondary} style={styles.hint}>
        It is usually a typing mistake, but herds do reuse tags.
      </Text>
      <YesNoField label="Are you sure this animal has the same tag?" value={value} onChange={onChange} />
    </View>
  );
}

const styles = StyleSheet.create({
  box: {
    backgroundColor: colors.primarySoft,
    borderRadius: radius.sm,
    borderWidth: 1,
    borderColor: colors.red[200],
    padding: spacing.md,
    marginBottom: spacing.md,
  },
  hint: { marginBottom: spacing.sm },
});
