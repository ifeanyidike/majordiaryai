import { useLocalSearchParams, useRouter } from 'expo-router';
import React, { useEffect, useMemo, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, View } from 'react-native';
import {
  Button,
  EmptyState,
  FormRow,
  FormLabel,
  Header,
  Screen,
  SectionHeader,
  SegmentedControl,
  Text,
  useToast,
} from '@/components';
import { colors, radius, spacing } from '@/theme';
import { isValidPastOrTodayDate } from '@/lib/dates';
import { CowInput, cowById, useAppStore } from '@/store/useAppStore';
import { useAuthStore } from '@/store/useAuthStore';

/**
 * Add / edit a cow — the Master Cow Record from the requirements doc.
 *
 * Cows could previously only enter the system by CSV import or by being born,
 * and a wrong breed or date of birth could never be corrected.
 *
 * Two fields are deliberately create-only. Ear tag is the animal's identity and
 * the farm is where she physically is; changing either after the fact is a
 * different operation (a re-tag or a transfer) with its own record-keeping, not
 * a form edit. The API's CowUpdate omits them for the same reason.
 */

export default function CowEditScreen() {
  const { id, farmId: farmIdParam } = useLocalSearchParams<{ id?: string; farmId?: string }>();
  const router = useRouter();
  const toast = useToast();
  const state = useAppStore();
  const { saveCow, farms, fetchFarms, demoMode } = state;
  const role = useAuthStore((s) => s.user?.role);

  const existing = id ? cowById(state, id) : undefined;
  const isEdit = !!id;

  const [earTag, setEarTag] = useState('');
  const [farmId, setFarmId] = useState<string | undefined>(farmIdParam);
  const [breed, setBreed] = useState('');
  const [dob, setDob] = useState('');
  const [sex, setSex] = useState<'female' | 'male'>('female');
  const [lactation, setLactation] = useState('0');
  const [notes, setNotes] = useState('');
  const [saving, setSaving] = useState(false);
  const [touched, setTouched] = useState(false);

  useEffect(() => {
    if (farms.length === 0) fetchFarms();
  }, []);

  useEffect(() => {
    if (!existing) return;
    setEarTag(existing.earTag);
    setFarmId(existing.farmId);
    setBreed(existing.breed ?? '');
    setDob(existing.dateOfBirth ?? '');
    setLactation(String(existing.lactationNumber ?? 0));
    setNotes(existing.notes ?? '');
  }, [existing?.id]);

  const errors = useMemo(() => {
    const e: Record<string, string> = {};
    if (!isEdit && !earTag.trim()) e.earTag = 'Ear tag is required';
    if (!isEdit && !farmId) e.farmId = 'Choose the farm this cow belongs to';
    if (dob.trim() && !isValidPastOrTodayDate(dob.trim())) {
      e.dob = 'Use YYYY-MM-DD, today or earlier';
    }
    if (lactation.trim() && !/^\d+$/.test(lactation.trim())) e.lactation = 'Numbers only';
    return e;
  }, [earTag, farmId, dob, lactation, isEdit]);

  const valid = Object.keys(errors).length === 0;

  if (role !== 'admin' && role !== 'technician') {
    return (
      <Screen>
        <Header back title={isEdit ? 'Edit Cow' : 'Add Cow'} />
        <EmptyState
          icon="lock-closed-outline"
          title="Not permitted"
          message="Cow records are managed by technicians and administrators."
        />
      </Screen>
    );
  }

  if (isEdit && !existing) {
    return (
      <Screen>
        <Header back title="Edit Cow" />
        <EmptyState title="Cow not found" message="She may have been removed." />
      </Screen>
    );
  }

  const submit = async () => {
    setTouched(true);
    if (!valid) return;
    if (demoMode) {
      toast.error('Demo mode — connect the API to save cows.');
      return;
    }
    setSaving(true);
    try {
      const input: CowInput = {
        earTag: earTag.trim(),
        farmId: farmId!,
        breed: breed.trim(),
        dateOfBirth: dob.trim(),
        sex,
        lactationNumber: lactation.trim() ? Number(lactation.trim()) : 0,
        notes: notes.trim(),
      };
      const savedId = await saveCow(input, id);
      toast.success(isEdit ? 'Cow updated' : `${input.earTag} added`);
      router.replace({ pathname: '/cow/[id]', params: { id: savedId } });
    } catch (e: any) {
      toast.error(e?.message ?? 'Could not save the cow');
    } finally {
      setSaving(false);
    }
  };

  const err = (key: string) => (touched ? errors[key] : undefined);

  return (
    <Screen scroll={false} padded={false}>
      <ScrollView
        contentContainerStyle={styles.content}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
      >
        <Header
          back
          title={isEdit ? 'Edit Cow' : 'Add Cow'}
          subtitle={isEdit ? existing?.earTag : 'New cow record'}
        />

        <SectionHeader title="Identity" />
        {isEdit ? (
          <View style={styles.locked}>
            <Text variant="label" color={colors.textSecondary}>Ear Tag</Text>
            <Text variant="bodyBold">{existing?.earTag}</Text>
            <Text variant="caption" color={colors.textMuted}>
              An ear tag identifies the animal — re-tagging is a separate process.
            </Text>
          </View>
        ) : (
          <FormRow
            label="Ear Tag"
            value={earTag}
            onChangeText={setEarTag}
            placeholder="e.g. CA 124 578 1042"
            autoCapitalize="characters"
            error={err('earTag')}
          />
        )}

        {isEdit ? null : (
          <>
            <FormLabel>Farm</FormLabel>
            <View style={styles.farmList}>
              {farms.map((f) => {
                const on = farmId === f.id;
                return (
                  <Pressable
                    key={f.id}
                    onPress={() => setFarmId(f.id)}
                    style={[styles.farmRow, on && styles.farmRowOn]}
                    accessibilityRole="radio"
                    accessibilityState={{ selected: on }}
                  >
                    <Text variant="body">{f.name}</Text>
                  </Pressable>
                );
              })}
            </View>
            {err('farmId') ? (
              <Text variant="caption" color={colors.danger} style={styles.hint}>
                {errors.farmId}
              </Text>
            ) : null}

            <FormLabel>Sex</FormLabel>
            <SegmentedControl
              options={[
                { value: 'female', label: 'Female' },
                { value: 'male', label: 'Male' },
              ]}
              value={sex}
              onChange={setSex}
              style={styles.segment}
            />
          </>
        )}

        <SectionHeader title="Details" />
        <FormRow label="Breed" value={breed} onChangeText={setBreed}
                 placeholder="e.g. Holstein" autoCapitalize="words" />
        <FormRow label="Date of Birth" value={dob} onChangeText={setDob}
                 placeholder="YYYY-MM-DD" keyboardType="numbers-and-punctuation"
                 error={err('dob')} />
        <FormRow label="Lactation Number" value={lactation} onChangeText={setLactation}
                 placeholder="0" keyboardType="numeric"
                 hint="0 for a heifer that has not calved yet."
                 error={err('lactation')} />

        <SectionHeader title="Notes" />
        <FormRow value={notes} onChangeText={setNotes}
                 placeholder="Temperament, health history, anything worth knowing…"
                 multiline autoCapitalize="sentences" />

        <View style={styles.actions}>
          <Button variant="secondary" label="Cancel" onPress={() => router.back()}
                  style={styles.flex1} />
          <Button
            label={isEdit ? 'Save Changes' : 'Add Cow'}
            icon="checkmark"
            onPress={submit}
            loading={saving}
            disabled={touched && !valid}
            style={styles.flex1}
          />
        </View>
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  content: { paddingHorizontal: spacing.xl, paddingBottom: spacing.huge },
  flex1: { flex: 1 },
  hint: { marginBottom: spacing.md },
  segment: { marginBottom: spacing.md },
  locked: {
    backgroundColor: colors.surfaceSoft,
    borderRadius: radius.sm,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.md,
    marginBottom: spacing.md,
    gap: 2,
  },
  farmList: { gap: spacing.xs, marginBottom: spacing.md },
  farmRow: {
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.md,
    borderRadius: radius.sm,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
    minHeight: 48,
    justifyContent: 'center',
  },
  farmRowOn: { borderColor: colors.primary, backgroundColor: colors.primarySoft },
  actions: { flexDirection: 'row', gap: spacing.md, marginTop: spacing.lg },
});
