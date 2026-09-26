import React, { useState } from 'react';
import { StyleSheet } from 'react-native';
import { api } from '@/lib/api';
import { colors, spacing } from '@/theme';
import { useToast } from './Toast';
import { FormRow } from './FormField';
import { Text } from './Text';

interface Props {
  cowLabel: string;
  recordId: string;
  /** The hormone the farmer has to give, e.g. "2cc GnRH". */
  treatment?: string;
  /** "Farm gives this one · 2cc GnRH due 2026-09-24" */
  context?: string;
  onCancel: () => void;
  onComplete: () => void;
}

/**
 * The note a technician leaves on a farm that gives its own last injection.
 *
 * Deliberately NOT the needling-complete form. That one records the shot as
 * administered — by the technician, today — and this shot is the farmer's.
 * Writing the note is the whole task: saving it sends it to the farm as a
 * notification. The farmer's shot is marked given when the technician
 * records the insemination that follows it.
 */
export function FarmerNoteForm({
  cowLabel, recordId, treatment, context, onCancel, onComplete,
}: Props) {
  const toast = useToast();
  const [note, setNote] = useState(
    treatment ? `${cowLabel} needs ${treatment}.` : '',
  );
  const [loading, setLoading] = useState(false);

  const submit = async () => {
    const body = note.trim();
    if (!body) {
      toast.error('Write the note first');
      return;
    }
    setLoading(true);
    try {
      await api.patch(`/needling/records/${recordId}/note`, { note: body });
      toast.success('Note left for the farmer');
      onComplete();
    } catch (e: any) {
      toast.error(e?.message ?? 'Could not save the note');
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <Text variant="body" color={colors.textSecondary} style={styles.hint}>
        This farm gives its own last injection. Leave the instruction here and
        it comes off your list — the farm has already been sent the same cow
        and hormone.
      </Text>
      {context ? (
        <Text variant="caption" color={colors.textMuted} style={styles.context}>
          {context}
        </Text>
      ) : null}
      <FormRow
        label="Note for the farmer"
        value={note}
        onChangeText={setNote}
        placeholder="Which cow, which hormone, which day"
        multiline
      />
      <FormActionsShim
        onCancel={onCancel}
        onSubmit={submit}
        loading={loading}
      />
    </>
  );
}

// The shared FormActions lives in CowActionsSheet, which imports this file's
// sibling forms — importing it back would close the cycle. This is the same
// pair of buttons.
import { Button } from './Button';
import { View } from 'react-native';

function FormActionsShim({
  onCancel, onSubmit, loading,
}: { onCancel: () => void; onSubmit: () => void; loading: boolean }) {
  return (
    <View style={styles.actions}>
      <Button label="Cancel" variant="ghost" onPress={onCancel} style={styles.action} />
      <Button
        label="Save Note"
        icon="create"
        onPress={onSubmit}
        loading={loading}
        style={styles.action}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  hint: { marginBottom: spacing.md },
  context: { marginBottom: spacing.md },
  actions: { flexDirection: 'row', gap: spacing.md, marginTop: spacing.lg },
  action: { flex: 1 },
});
