import React, { useEffect, useState } from 'react';
import {
  KeyboardAvoidingView,
  Modal,
  Platform,
  Pressable,
  StyleSheet,
  TextInput,
  View,
} from 'react-native';
import { colors, radius, shadows, spacing, typography } from '@/theme';
import { Button } from './Button';
import { Text } from './Text';

interface InputModalProps {
  visible: boolean;
  title: string;
  placeholder?: string;
  submitLabel?: string;
  initialValue?: string;
  submitting?: boolean;
  /** May be async — callers that persist must be able to await and catch. */
  onSubmit: (text: string) => void | Promise<void>;
  onClose: () => void;
}

/** Shared single-field note/text modal — backdrop tap dismisses. */
export function InputModal({
  visible,
  title,
  placeholder = 'Write a note…',
  submitLabel = 'Save',
  initialValue = '',
  submitting,
  onSubmit,
  onClose,
}: InputModalProps) {
  const [text, setText] = useState(initialValue);

  useEffect(() => {
    if (visible) setText(initialValue);
  }, [visible, initialValue]);

  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <Pressable
        style={styles.backdrop}
        onPress={onClose}
        accessibilityRole="button"
        accessibilityLabel="Dismiss"
      >
        <KeyboardAvoidingView
          behavior={Platform.OS === 'ios' ? 'padding' : undefined}
          style={styles.avoider}
          pointerEvents="box-none"
        >
          <Pressable style={styles.sheet} onPress={() => {}}>
            <Text variant="heading">{title}</Text>
            <TextInput
              style={styles.input}
              value={text}
              onChangeText={setText}
              placeholder={placeholder}
              placeholderTextColor={colors.textMuted}
              multiline
              autoFocus
            />
            <View style={styles.actions}>
              <Button label="Cancel" variant="secondary" compact onPress={onClose} style={styles.actionBtn} />
              <Button
                label={submitLabel}
                compact
                loading={submitting}
                disabled={!text.trim()}
                onPress={() => onSubmit(text.trim())}
                style={styles.actionBtn}
              />
            </View>
          </Pressable>
        </KeyboardAvoidingView>
      </Pressable>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: {
    flex: 1,
    backgroundColor: colors.overlayDark,
    justifyContent: 'center',
  },
  avoider: { justifyContent: 'center' },
  sheet: {
    marginHorizontal: spacing.xl,
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    padding: spacing.xl,
    gap: spacing.lg,
    ...shadows.raised,
  },
  input: {
    ...typography.input,
    color: colors.text,
    backgroundColor: colors.surfaceSoft,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.sm,
    padding: spacing.md,
    minHeight: 96,
    textAlignVertical: 'top',
  },
  actions: {
    flexDirection: 'row',
    gap: spacing.md,
  },
  actionBtn: { flex: 1 },
});
