import { Ionicons } from '@expo/vector-icons';
import React, { useEffect, useState } from 'react';
import { StyleSheet, Switch, TextInput, View } from 'react-native';
import { Button } from './Button';
import { Skeleton } from './Skeleton';
import { Text } from './Text';
import { useToast } from './Toast';
import { api } from '@/lib/api';
import { colors, radius, spacing, typography } from '@/theme';

interface ApiNeedlingRecord {
  id: string;
  protocol_day: number;
  scheduled_date: string;
  completed_date?: string | null;
  treatment: string;
  is_final: boolean;
  completed: boolean;
  bleeding_event: boolean;
}

interface ApiEnrollment {
  id: string;
  protocol: string;
  status: string;
  records?: ApiNeedlingRecord[];
}

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

  // Injection history is part of the spec's needling entry ("protocol name,
  // current day, exact treatment, injection history, notes field") and it was
  // the one piece missing: the technician could see what to give today but not
  // whether the earlier shots in this protocol had actually been given — the
  // thing that decides whether today's step is even valid.
  const [history, setHistory] = useState<ApiNeedlingRecord[] | null>(null);
  const [historyFailed, setHistoryFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api
      .get<ApiEnrollment[]>(`/needling/cow/${cowId}`)
      .then((enrollments) => {
        if (cancelled) return;
        // The active enrollment is the one this record belongs to.
        const active = enrollments.find((e) =>
          (e.records ?? []).some((r) => r.id === recordId),
        ) ?? enrollments[0];
        setHistory(
          [...(active?.records ?? [])].sort((a, b) => a.protocol_day - b.protocol_day),
        );
      })
      .catch(() => {
        // History is context, never a reason to block recording the shot.
        if (!cancelled) setHistoryFailed(true);
      });
    return () => { cancelled = true; };
  }, [cowId, recordId]);

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
      {/* Injection history — what has and has not been given on this protocol. */}
      {historyFailed ? null : history === null ? (
        <View style={styles.historyCard}>
          <Skeleton width="40%" height={12} />
          <Skeleton width="80%" height={13} />
          <Skeleton width="70%" height={13} />
        </View>
      ) : history.length > 0 ? (
        <View style={styles.historyCard}>
          <Text variant="label" color={colors.textSecondary}>Injection history</Text>
          {history.map((r) => {
            const isToday = r.id === recordId;
            return (
              <View key={r.id} style={styles.historyRow}>
                <Ionicons
                  name={
                    r.completed ? 'checkmark-circle'
                    : isToday ? 'ellipse-outline'
                    : 'close-circle-outline'
                  }
                  size={15}
                  color={
                    r.completed ? colors.success
                    : isToday ? colors.primary
                    : colors.textMuted
                  }
                />
                <Text
                  variant="caption"
                  color={isToday ? colors.text : colors.textSecondary}
                  style={styles.flex1}
                  numberOfLines={1}
                >
                  Day {r.protocol_day} · {r.treatment}
                </Text>
                <Text variant="caption" color={colors.textMuted}>
                  {r.completed
                    ? (r.completed_date ?? 'given')
                    : isToday ? 'today' : 'not given'}
                </Text>
              </View>
            );
          })}
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
    gap: spacing.hairline,
  },
  historyCard: {
    backgroundColor: colors.surfaceSoft,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.sm,
    padding: spacing.md,
    marginBottom: spacing.md,
    gap: spacing.xs,
  },
  historyRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
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
