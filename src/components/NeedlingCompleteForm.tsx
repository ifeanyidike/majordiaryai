import React, { useState } from 'react';
import { StyleSheet, Switch, TextInput, View } from 'react-native';
import { Button } from './Button';
import { Text } from './Text';
import { useToast } from './Toast';
import { api } from '@/lib/api';
import { colors, radius, spacing, typography } from '@/theme';

interface Props {
  /** The cow the record belongs to — bleeding is recorded against the cow. */
  cowId: string;
  /** The scheduled needling record being marked as given */
  recordId: string;
  /** Exactly what to inject today, e.g. "2cc PGF" */
  treatment?: string;
  /** Protocol context, e.g. "Ovsynch, Day 7" */
  context?: string;
  onCancel: () => void;
  onComplete: (bleeding: boolean) => void;
}

/**
 * Needling record completion — injection given, OR a bleeding event.
 *
 * The two are different endpoints on purpose: completing the record claims the
 * injection was administered, while a bleeding event means the protocol stops
 * (cow to Open, restarted on Ovsynch) and no shot is recorded as given.
 */
export function NeedlingCompleteForm({
  cowId, recordId, treatment, context, onCancel, onComplete,
}: Props) {
  const toast = useToast();
  const [bleeding, setBleeding] = useState(false);
  // Bleeding noticed AFTER the shot was given: both facts must be recorded in
  // one submission — completing the record with the bleeding flag does that.
  const [injectionGiven, setInjectionGiven] = useState(false);
  const [notes, setNotes] = useState('');
  const [loading, setLoading] = useState(false);

  const submit = async () => {
    setLoading(true);
    try {
      if (bleeding && !injectionGiven) {
        await api.post(`/needling/cow/${cowId}/bleeding`, {
          notes: notes.trim() || null,
        });
        toast.show(
          'Bleeding recorded — cow moves to Open and restarts on Ovsynch',
          'water',
          'success',
        );
      } else {
        await api.patch(`/needling/records/${recordId}/complete`, {
          bleeding_event: bleeding,
          notes: notes.trim() || null,
        });
        toast.show(
          bleeding
            ? 'Injection and bleeding recorded — cow moves to Open and restarts on Ovsynch'
            : 'Needling step completed',
          bleeding ? 'water' : 'checkmark-circle',
          'success',
        );
      }
      onComplete(bleeding);
    } catch (e: any) {
      toast.error(e?.message ?? 'Failed to record the needling step');
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      {/* What to give, before confirming — the technician shouldn't have to
          remember it from the previous screen. */}
      {treatment ? (
        <View style={styles.treatmentCard}>
          <Text variant="label" color={colors.textSecondary}>Give today</Text>
          <Text variant="heading" color={colors.primary}>{treatment}</Text>
          {context ? (
            <Text variant="caption" color={colors.textSecondary}>{context}</Text>
          ) : null}
        </View>
      ) : null}
      <View style={styles.toggleRow}>
        <Text variant="body">Bleeding event?</Text>
        <Switch
          value={bleeding}
          onValueChange={setBleeding}
          trackColor={{ false: colors.cream.line, true: colors.primary }}
          thumbColor={colors.cream.base}
          accessibilityLabel="Bleeding event"
        />
      </View>
      {bleeding && (
        <>
          <View style={styles.toggleRow}>
            <Text variant="body">Was the injection given first?</Text>
            <Switch
              value={injectionGiven}
              onValueChange={setInjectionGiven}
              trackColor={{ false: colors.cream.line, true: colors.primary }}
              thumbColor={colors.cream.base}
              accessibilityLabel="Injection given before the bleeding was noticed"
            />
          </View>
          <Text variant="caption" color={colors.textSecondary} style={{ marginBottom: spacing.md }}>
            Bleeding before insemination sends the cow to Open and transfers her to the Ovsynch
            program.{' '}
            {injectionGiven
              ? "Today's injection is recorded as given."
              : "Today's injection is not marked as given."}
          </Text>
        </>
      )}
      <TextInput
        style={styles.noteInput}
        value={notes}
        onChangeText={setNotes}
        placeholder="Notes — side effects, behavior… (optional)"
        placeholderTextColor={colors.textMuted}
        multiline
      />
      <View style={styles.actions}>
        <Button compact variant="secondary" label="Cancel" onPress={onCancel} style={styles.flex1} />
        <Button
          compact
          label={bleeding ? 'Record Bleeding' : 'Mark Completed'}
          icon={bleeding ? 'water' : 'checkmark'}
          onPress={submit}
          loading={loading}
          style={styles.flex1}
        />
      </View>
    </>
  );
}

const styles = StyleSheet.create({
  treatmentCard: {
    backgroundColor: colors.primarySoft,
    borderWidth: 1,
    borderColor: colors.red[200],
    borderRadius: radius.sm,
    padding: spacing.md,
    marginBottom: spacing.md,
    gap: 2,
  },
  toggleRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: spacing.sm,
    marginBottom: spacing.sm,
  },
  noteInput: {
    ...typography.input,
    color: colors.text,
    backgroundColor: colors.surfaceSoft,
    borderRadius: radius.sm,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.md,
    minHeight: 80,
    textAlignVertical: 'top',
    marginBottom: spacing.md,
  },
  actions: { flexDirection: 'row', gap: spacing.md },
  flex1: { flex: 1 },
});
