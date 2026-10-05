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
  SegmentedControl,
  YesNoField,
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
  const [name, setName] = useState('');
  const [farmId, setFarmId] = useState<string | undefined>(farmIdParam);
  const [breed, setBreed] = useState('');
  const [dob, setDob] = useState('');
  const [sex, setSex] = useState<'female' | 'male'>('female');
  const [lactation, setLactation] = useState('0');
  const [notes, setNotes] = useState('');
  const [sire, setSire] = useState('');
  const [maternalSire, setMaternalSire] = useState('');
  const [doNotBreed, setDoNotBreed] = useState(false);
  const [doNotInseminate, setDoNotInseminate] = useState(false);
  const [saving, setSaving] = useState(false);
  const [touched, setTouched] = useState(false);

  useEffect(() => {
    if (farms.length === 0) fetchFarms();
  }, []);

  useEffect(() => {
    if (!existing) return;
    setEarTag(existing.earTag ?? '');
    setName(existing.name ?? '');
    setFarmId(existing.farmId);
    setBreed(existing.breed ?? '');
    setDob(existing.dateOfBirth ?? '');
    setLactation(String(existing.lactationNumber ?? 0));
    setNotes(existing.notes ?? '');
    setSire(existing.sire ?? '');
    setMaternalSire(existing.maternalSire ?? '');
    setDoNotBreed(!!existing.doNotBreed);
    setDoNotInseminate(!!existing.doNotInseminate);
  }, [existing?.id]);

  const errors = useMemo(() => {
    const e: Record<string, string> = {};
    // Either identifier will do; the API and the database both refuse
    // neither, so say so here rather than letting the save fail.
    if (!isEdit && !earTag.trim() && !name.trim()) {
      e.earTag = 'Give her an ear tag, a name, or both';
    }
    if (!isEdit && !farmId) e.farmId = 'Choose the farm this cow belongs to';
    if (dob.trim() && !isValidPastOrTodayDate(dob.trim())) {
      e.dob = 'Use YYYY-MM-DD, today or earlier';
    }
    if (lactation.trim() && !/^\d+$/.test(lactation.trim())) e.lactation = 'Numbers only';
    return e;
  }, [earTag, name, farmId, dob, lactation, isEdit]);

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
        earTag: earTag.trim() || undefined,
        name: name.trim() || undefined,
        farmId: farmId!,
        breed: breed.trim(),
        dateOfBirth: dob.trim(),
        sex,
        lactationNumber: lactation.trim() ? Number(lactation.trim()) : 0,
        notes: notes.trim(),
        sire: sire.trim(),
        maternalSire: maternalSire.trim(),
        doNotBreed,
        doNotInseminate,
      };
      const savedId = await saveCow(input, id);
      toast.success(
        isEdit ? 'Cow updated' : `${input.name || input.earTag} added`,
      );
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
          title={isEdit ? 'Edit Cow' : 'Add Cow'}
          subtitle={isEdit ? existing?.label : 'New cow record'}
        />

        <SectionHeader title="Identity" />
        {isEdit ? (
          <View style={styles.locked}>
            <Text variant="label" color={colors.textSecondary}>Ear Tag</Text>
            <Text variant="bodyBold">{existing?.label}</Text>
            <Text variant="caption" color={colors.textMuted}>
              An ear tag identifies the animal — re-tagging is a separate process.
            </Text>
          </View>
        ) : (
          <FormRow
            label="Ear Tag (optional if she has a name)"
            value={earTag}
            onChangeText={setEarTag}
            placeholder="e.g. CA 124 578 1042"
            autoCapitalize="characters"
            error={err('earTag')}
          />
        )}

        {/* Optional: a farm that names its cows can search and read her that
            way. The tag above is still the identity — unique per farm, and
            what every other record keys on — so this never replaces it. */}
        <FormRow
          label="Name (optional if she has a tag)"
          value={name}
          onChangeText={setName}
          placeholder="e.g. Bluebell"
        />

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

        {/* Josh, Oct 2: her father, and her mother's father. */}
        <SectionHeader title="Parentage" />
        <FormRow label="Sire (Father)" value={sire} onChangeText={setSire}
                 placeholder="e.g. Delta-Lambda" autoCapitalize="words" />
        <FormRow label="Maternal Sire (Mother's Father)" value={maternalSire}
                 onChangeText={setMaternalSire}
                 placeholder="e.g. Mogul" autoCapitalize="words" />

        {/* A cow on either list who shows heat is not put on Today's Breed
            Report (Josh, Oct 4). */}
        <SectionHeader title="Breeding" />
        <YesNoField label="On the Do Not Breed list?" value={doNotBreed} onChange={setDoNotBreed} />
        <YesNoField label="On the Do Not Inseminate list?" value={doNotInseminate}
                    onChange={setDoNotInseminate} />

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
      </KeyboardAvoidingView>
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
    gap: spacing.hairline,
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
