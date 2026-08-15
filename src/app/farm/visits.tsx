import { Ionicons } from '@expo/vector-icons';
import { useLocalSearchParams, useRouter } from 'expo-router';
import React, { useEffect, useMemo, useState } from 'react';
import {
  KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, View,
} from 'react-native';
import {
  Button,
  EmptyState,
  FormRow,
  FormLabel,
  Header,
  Screen,
  SectionHeader,
  Text,
  useToast,
} from '@/components';
import { colors, radius, spacing, touch } from '@/theme';
import { addDays, todayISO } from '@/lib/dates';
import { farmById, useAppStore } from '@/store/useAppStore';
import { useAuthStore } from '@/store/useAuthStore';

/**
 * Hand a day's visit to someone else — the spec's "Farms can be reassigned to a
 * Relief Technician or another technician", which the To-Do list already
 * renders ("Reassigned to Relief Tech — Skip") but had no way to actually do.
 *
 * Only upcoming days are offered: a past visit either happened or didn't, and
 * the API rejects back-dating for the same reason.
 */

const DAY_NAMES = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const HORIZON_DAYS = 14;

function pretty(iso: string): string {
  const d = new Date(`${iso}T00:00:00`);
  return `${DAY_NAMES[d.getDay()]} ${d.getDate()}/${d.getMonth() + 1}`;
}

export default function FarmVisitsScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const toast = useToast();
  const state = useAppStore();
  const {
    technicians, fetchTechnicians, visitAssignments,
    fetchVisitAssignments, setVisitAssignment, clearVisitAssignment, demoMode,
  } = state;
  const role = useAuthStore((s) => s.user?.role);
  const farm = id ? farmById(state, id) : undefined;

  const [date, setDate] = useState(todayISO());
  const [coverId, setCoverId] = useState<string | null | undefined>(undefined);
  const [reason, setReason] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    fetchTechnicians();
    if (id) fetchVisitAssignments(id);
  }, [id]);

  // Only days the farm is actually visited can be handed over.
  const dueDays = useMemo(() => {
    const days: string[] = [];
    const weekdays = new Set(farm?.visitWeekdays ?? [0, 1, 2, 3, 4, 5]);
    for (let i = 0; i < HORIZON_DAYS; i++) {
      const iso = addDays(todayISO(), i);
      // getDay() is Sun=0; the API and farm.visitWeekdays use Mon=0.
      const mondayFirst = (new Date(`${iso}T00:00:00`).getDay() + 6) % 7;
      if (weekdays.has(mondayFirst)) days.push(iso);
    }
    return days;
  }, [farm?.visitWeekdays]);

  useEffect(() => {
    if (dueDays.length && !dueDays.includes(date)) setDate(dueDays[0]);
  }, [dueDays.join(',')]);

  const existing = (visitAssignments[id ?? ''] ?? []).filter((a) => a.visitDate >= todayISO());

  if (role !== 'admin' && role !== 'technician') {
    return (
      <Screen>
        <Header back title="Visit Schedule" />
        <EmptyState
          icon="lock-closed-outline"
          title="Not permitted"
          message="Visit assignments are managed by technicians and administrators."
        />
      </Screen>
    );
  }

  if (!farm) {
    return (
      <Screen>
        <Header back title="Visit Schedule" />
        <EmptyState title="Farm not found" />
      </Screen>
    );
  }

  const save = async () => {
    if (demoMode) {
      toast.error('Demo mode — connect the API to change visits.');
      return;
    }
    if (coverId === undefined) {
      toast.error('Choose who covers the visit, or mark it skipped.');
      return;
    }
    setSaving(true);
    try {
      await setVisitAssignment(farm.id, date, coverId, reason.trim() || undefined);
      toast.success(
        coverId ? `${pretty(date)} handed over` : `${pretty(date)} marked as skipped`,
      );
      setReason('');
      setCoverId(undefined);
    } catch (e: any) {
      toast.error(e?.message ?? 'Could not change the visit');
    } finally {
      setSaving(false);
    }
  };

  const undo = async (visitDate: string) => {
    try {
      await clearVisitAssignment(farm.id, visitDate);
      toast.success(`${pretty(visitDate)} back to the standing technician`);
    } catch (e: any) {
      toast.error(e?.message ?? 'Could not clear the override');
    }
  };

  return (
    <Screen scroll={false} padded={false}>
      {/* Without this the bottom fields sit under the iOS keyboard. */}
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        style={styles.flex1}
      >
      <ScrollView
        contentContainerStyle={styles.content}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
      >
        <Header
          back
          title="Visit Schedule"
          subtitle={`${farm.name} · ${farm.visitScheduleLabel ?? 'Mon–Sat'}`}
        />

        <SectionHeader title="Hand over a day" />
        <Text variant="caption" color={colors.textSecondary} style={styles.blurb}>
          The standing technician is {farm.assignedTechnician || 'unassigned'}. Only days
          this farm is due are listed.
        </Text>

        <FormLabel>Which day</FormLabel>
        {dueDays.length === 0 ? (
          <Text variant="caption" color={colors.textMuted} style={styles.blurb}>
            No visits scheduled in the next {HORIZON_DAYS} days.
          </Text>
        ) : (
          <View style={styles.dayRow}>
            {dueDays.map((iso) => {
              const on = date === iso;
              return (
                <Pressable
                  key={iso}
                  onPress={() => setDate(iso)}
                  style={[styles.day, on && styles.dayOn]}
                  accessibilityRole="button"
                  accessibilityState={{ selected: on }}
                >
                  <Text variant="caption" color={on ? colors.textOnPrimary : colors.textSecondary}>
                    {pretty(iso)}
                  </Text>
                </Pressable>
              );
            })}
          </View>
        )}

        <FormLabel>Who covers it</FormLabel>
        <View style={styles.list}>
          <Option
            label="Nobody — skip this visit"
            icon="remove-circle-outline"
            active={coverId === null}
            onPress={() => setCoverId(null)}
          />
          {technicians.map((t) => (
            <Option
              key={t.id}
              label={t.name}
              sublabel={t.email}
              icon="person-circle-outline"
              active={coverId === t.id}
              onPress={() => setCoverId(t.id)}
            />
          ))}
        </View>

        <FormRow
          label="Reason (optional)"
          value={reason}
          onChangeText={setReason}
          placeholder="On leave, route swap…"
          autoCapitalize="sentences"
        />

        <Button
          label="Save Assignment"
          icon="checkmark"
          onPress={save}
          loading={saving}
          disabled={dueDays.length === 0}
        />

        {existing.length > 0 && (
          <>
            <SectionHeader title="Upcoming overrides" />
            {existing.map((a) => (
              <View key={a.visitDate} style={styles.overrideRow}>
                <View style={styles.flex1}>
                  <Text variant="bodyBold">{pretty(a.visitDate)}</Text>
                  <Text variant="caption" color={colors.textSecondary}>
                    {a.assignedTechnicianName
                      ? `Covered by ${a.assignedTechnicianName}`
                      : 'Visit skipped'}
                    {a.reason ? ` · ${a.reason}` : ''}
                  </Text>
                </View>
                <Pressable
                  onPress={() => undo(a.visitDate)}
                  style={styles.undo}
                  accessibilityRole="button"
                  accessibilityLabel={`Undo the override for ${pretty(a.visitDate)}`}
                >
                  <Ionicons name="arrow-undo" size={16} color={colors.primary} />
                  <Text variant="caption" color={colors.primary}>Undo</Text>
                </Pressable>
              </View>
            ))}
          </>
        )}
      </ScrollView>
      </KeyboardAvoidingView>
    </Screen>
  );
}

function Option({
  label, sublabel, icon, active, onPress,
}: {
  label: string;
  sublabel?: string;
  icon: keyof typeof Ionicons.glyphMap;
  active: boolean;
  onPress: () => void;
}) {
  return (
    <Pressable
      onPress={onPress}
      style={[styles.option, active && styles.optionOn]}
      accessibilityRole="radio"
      accessibilityState={{ selected: active }}
    >
      <Ionicons
        name={active ? 'radio-button-on' : icon}
        size={19}
        color={active ? colors.primary : colors.textMuted}
      />
      <View style={styles.flex1}>
        <Text variant="body">{label}</Text>
        {sublabel ? (
          <Text variant="caption" color={colors.textMuted} numberOfLines={1}>{sublabel}</Text>
        ) : null}
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  content: { paddingHorizontal: spacing.xl, paddingBottom: spacing.huge },
  flex1: { flex: 1 },
  blurb: { marginBottom: spacing.md },
  dayRow: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.xs + 2, marginBottom: spacing.md },
  day: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    // touch.iconButton: below 44 a chip is hard to hit accurately, and these
    // are tapped seven at a time to build a rotation.
    minHeight: touch.iconButton,
    justifyContent: 'center',
    borderRadius: radius.sm,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  dayOn: { backgroundColor: colors.primary, borderColor: colors.primary },
  list: { gap: spacing.xs, marginBottom: spacing.md },
  option: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.md,
    borderRadius: radius.sm,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
    minHeight: 56,
  },
  optionOn: { borderColor: colors.primary, backgroundColor: colors.primarySoft },
  overrideRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    paddingVertical: spacing.md,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.border,
  },
  undo: { flexDirection: 'row', alignItems: 'center', gap: spacing.xs, minHeight: 44, paddingHorizontal: spacing.sm },
});
