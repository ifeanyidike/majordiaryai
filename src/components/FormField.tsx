import React from 'react';
import { StyleSheet, TextInput, View } from 'react-native';
import { Text } from './Text';
import { colors, radius, spacing, typography } from '@/theme';

/**
 * Form primitives shared by the recording sheets and the full-screen forms.
 *
 * These lived privately inside CowActionsSheet; a second copy in the farm form
 * would have drifted in padding and error styling, so they live here and both
 * sides import them.
 */

export function FormLabel({ children }: { children: string }) {
  return (
    <Text variant="label" color={colors.textSecondary} style={styles.label}>
      {children}
    </Text>
  );
}

export interface FormInputProps {
  value: string;
  onChangeText: (t: string) => void;
  placeholder?: string;
  multiline?: boolean;
  keyboardType?: 'default' | 'numeric' | 'numbers-and-punctuation' | 'email-address' | 'phone-pad';
  error?: boolean;
  autoCapitalize?: 'none' | 'sentences' | 'words' | 'characters';
}

export function FormInput({
  value, onChangeText, placeholder, multiline, keyboardType, error,
  autoCapitalize = 'none',
}: FormInputProps) {
  return (
    <TextInput
      style={[styles.input, multiline && styles.inputMulti, error && styles.inputError]}
      value={value}
      onChangeText={onChangeText}
      placeholder={placeholder}
      placeholderTextColor={colors.textMuted}
      multiline={multiline}
      keyboardType={keyboardType}
      autoCapitalize={autoCapitalize}
    />
  );
}

/** Label + input + inline validation message, the common vertical unit. */
export function FormRow({
  label, hint, error, ...input
}: Omit<FormInputProps, 'error'> & { label: string; hint?: string; error?: string }) {
  return (
    <View style={styles.row}>
      <FormLabel>{label}</FormLabel>
      <FormInput {...input} error={!!error} />
      {error ? (
        <Text variant="caption" color={colors.danger} style={styles.hint}>{error}</Text>
      ) : hint ? (
        <Text variant="caption" color={colors.textMuted} style={styles.hint}>{hint}</Text>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  label: { marginBottom: 4 },
  row: { marginBottom: spacing.md },
  hint: { marginTop: 4 },
  input: {
    ...typography.input,
    color: colors.text,
    backgroundColor: colors.surfaceSoft,
    borderRadius: radius.sm,
    borderWidth: 1,
    borderColor: colors.border,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.md,
    minHeight: 46,
  },
  inputMulti: { minHeight: 88, textAlignVertical: 'top' },
  inputError: { borderColor: colors.danger },
});
