import { Ionicons } from '@expo/vector-icons';
import React from 'react';
import { StyleSheet, View } from 'react-native';
import { protocolByValue } from '@/data/protocols';
import { ActiveProtocol, ProtocolStepRecord } from '@/data/types';
import { todayISO } from '@/lib/dates';
import { colors, radius, spacing } from '@/theme';
import { Card } from './Card';
import { Text } from './Text';

const fmtDay = (iso?: string) =>
  iso
    ? new Date(iso + 'T00:00:00').toLocaleDateString('en-CA', { month: 'short', day: 'numeric' })
    : '—';

/** A step that is not done: late, next up, or further off. */
function whenLabel(step: ProtocolStepRecord, isNext: boolean, today: string) {
  if (!isNext) return { text: fmtDay(step.date), color: colors.textMuted };
  if (step.date < today) return { text: `Overdue · ${fmtDay(step.date)}`, color: colors.danger };
  return { text: step.date === today ? 'Next · Today' : `Next · ${fmtDay(step.date)}`, color: colors.primary };
}

/**
 * Where she is on her protocol: what has been done, what is next, and when.
 *
 * Josh's test results, Nov 5, row 11: "Put in notes its current schedule in
 * protocols". The page said which protocol, and the Treatments tab listed its
 * steps with dates, but nothing said which were done or what came next.
 */
export function ProtocolSchedule({ protocol }: { protocol: ActiveProtocol }) {
  const today = todayISO();
  const next = protocol.steps.find((s) => !s.done);
  return (
    <Card style={styles.card}>
      <Text variant="subheading" style={styles.title}>
        {protocolByValue(protocol.protocol)?.label ?? protocol.protocol}
      </Text>
      {protocol.steps.map((step, i) => {
        const isNext = step === next;
        const when = step.done
          ? { text: `Done · ${fmtDay(step.doneOn ?? step.date)}`, color: colors.success }
          : whenLabel(step, isNext, today);
        return (
          <View key={step.id} style={styles.row}>
            <View style={styles.rail}>
              <View style={[styles.dot, step.done && styles.dotDone, isNext && styles.dotNext]}>
                {step.done ? <Ionicons name="checkmark" size={11} color={colors.textOnPrimary} /> : null}
              </View>
              {i < protocol.steps.length - 1 ? <View style={styles.line} /> : null}
            </View>
            <View style={styles.text}>
              <Text variant={isNext ? 'bodyBold' : 'body'} color={step.done ? colors.textSecondary : colors.text}>
                Day {step.day} · {step.treatment}
              </Text>
              <Text variant="caption" color={when.color}>
                {when.text}{step.byFarm ? ' · the farm gives this one' : ''}
              </Text>
            </View>
          </View>
        );
      })}
    </Card>
  );
}

const DOT = 18;

const styles = StyleSheet.create({
  card: { marginBottom: spacing.lg, paddingVertical: spacing.lg },
  title: { marginBottom: spacing.md },
  row: { flexDirection: 'row', gap: spacing.md },
  rail: { width: DOT, alignItems: 'center' },
  dot: {
    width: DOT,
    height: DOT,
    borderRadius: radius.pill,
    borderWidth: 2,
    borderColor: colors.border,
    backgroundColor: colors.surface,
    alignItems: 'center',
    justifyContent: 'center',
  },
  dotDone: { backgroundColor: colors.success, borderColor: colors.success },
  dotNext: { borderColor: colors.primary, backgroundColor: colors.primarySoft },
  line: { flex: 1, width: 2, backgroundColor: colors.border, marginVertical: spacing.hairline },
  text: { flex: 1, paddingBottom: spacing.md, gap: spacing.hairline },
});
