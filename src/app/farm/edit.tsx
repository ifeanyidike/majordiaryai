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
import { colors, radius, spacing } from '@/theme';
import { FarmInput, farmById, useAppStore } from '@/store/useAppStore';
import { useAuthStore } from '@/store/useAuthStore';

/**
 * Add / edit a farm — the Farm Module from the requirements doc (name, owner,
 * address, contact, herd size, assigned technician, notes) plus the visit
 * schedule the General To-Do list runs on.
 *
 * One screen for both modes: with an `id` param it edits, without it creates.
 * The two differ only in initial values and the save call, and keeping them
 * together stops the field list drifting between "add" and "edit".
 */

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

const DAY_LABELS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const MON_FRI = [0, 1, 2, 3, 4];
const MON_SAT = [0, 1, 2, 3, 4, 5];

const sameDays = (a: number[], b: number[]) =>
  a.length === b.length && [...a].sort().every((d, i) => d === [...b].sort()[i]);

export default function FarmEditScreen() {
  const { id } = useLocalSearchParams<{ id?: string }>();
  const router = useRouter();
  const toast = useToast();
  const state = useAppStore();
  const { saveFarm, technicians, fetchTechnicians, demoMode } = state;
  const role = useAuthStore((s) => s.user?.role);

  const existing = id ? farmById(state, id) : undefined;
  const isEdit = !!id;

  const [name, setName] = useState('');
  const [owner, setOwner] = useState('');
  const [address, setAddress] = useState('');
  const [city, setCity] = useState('');
  const [province, setProvince] = useState('');
  const [postalCode, setPostalCode] = useState('');
  const [phone, setPhone] = useState('');
  const [email, setEmail] = useState('');
  const [herdSize, setHerdSize] = useState('');
  const [technicianId, setTechnicianId] = useState<string | undefined>();
  const [weekdays, setWeekdays] = useState<number[]>(MON_SAT);
  const [notes, setNotes] = useState('');
  const [saving, setSaving] = useState(false);
  const [touched, setTouched] = useState(false);

  useEffect(() => {
    fetchTechnicians();
  }, []);

  // Populate once the farm is available (it may arrive after a deep link).
  useEffect(() => {
    if (!existing) return;
    setName(existing.name);
    setOwner(existing.owner);
    setAddress(existing.address ?? '');
    setCity(existing.city ?? '');
    setProvince(existing.province ?? '');
    setPostalCode(existing.postalCode ?? '');
    setPhone(existing.phone ?? '');
    setEmail(existing.email ?? '');
    setHerdSize(existing.reportedHerdSize ? String(existing.reportedHerdSize) : '');
    setTechnicianId(existing.assignedTechnicianId);
    setWeekdays(existing.visitWeekdays?.length ? existing.visitWeekdays : MON_SAT);
    setNotes(existing.notes?.[0] ?? '');
  }, [existing?.id]);

  const errors = useMemo(() => {
    const e: Record<string, string> = {};
    if (!name.trim()) e.name = 'Farm name is required';
    if (!owner.trim()) e.owner = 'Owner name is required';
    if (email.trim() && !EMAIL_RE.test(email.trim())) e.email = 'Enter a valid email address';
    if (herdSize.trim() && !/^\d+$/.test(herdSize.trim())) e.herdSize = 'Numbers only';
    if (weekdays.length === 0) e.weekdays = 'Pick at least one visit day';
    return e;
  }, [name, owner, email, herdSize, weekdays]);

  const valid = Object.keys(errors).length === 0;

  // Admin-only: the API rejects anyone else, so don't present a form that 403s.
  if (role !== 'admin') {
    return (
      <Screen>
        <Header back title={isEdit ? 'Edit Farm' : 'Add Farm'} />
        <EmptyState
          icon="lock-closed-outline"
          title="Admins only"
          message="Farm details are managed by an administrator."
        />
      </Screen>
    );
  }

  if (isEdit && !existing) {
    return (
      <Screen>
        <Header back title="Edit Farm" />
        <EmptyState title="Farm not found" message="It may have been removed." />
      </Screen>
    );
  }

  const toggleDay = (day: number) =>
    setWeekdays((days) =>
      days.includes(day) ? days.filter((d) => d !== day) : [...days, day].sort(),
    );

  const submit = async () => {
    setTouched(true);
    if (!valid) return;
    if (demoMode) {
      toast.error('Demo mode — connect the API to save farms.');
      return;
    }
    setSaving(true);
    try {
      const input: FarmInput = {
        name: name.trim(),
        ownerName: owner.trim(),
        address: address.trim(),
        city: city.trim(),
        province: province.trim(),
        postalCode: postalCode.trim(),
        phone: phone.trim(),
        email: email.trim(),
        herdSize: herdSize.trim() ? Number(herdSize.trim()) : 0,
        assignedTechnicianId: technicianId,
        visitWeekdays: weekdays,
        notes: notes.trim(),
      };
      const savedId = await saveFarm(input, id);
      toast.success(isEdit ? 'Farm updated' : `${input.name} added`);
      // Replace so Back doesn't return to a stale form.
      router.replace({ pathname: '/farm/[id]', params: { id: savedId } });
    } catch (e: any) {
      toast.error(e?.message ?? 'Could not save the farm');
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
          title={isEdit ? 'Edit Farm' : 'Add Farm'}
          subtitle={isEdit ? existing?.name : 'New farm record'}
        />

        <SectionHeader title="Farm Details" />
        <FormRow
          label="Farm Name"
          value={name}
          onChangeText={setName}
          placeholder="Required"
          autoCapitalize="words"
          error={err('name')}
        />
        <FormRow
          label="Owner Name"
          value={owner}
          onChangeText={setOwner}
          placeholder="Required"
          autoCapitalize="words"
          error={err('owner')}
        />
        <FormRow
          label="Herd Size"
          value={herdSize}
          onChangeText={setHerdSize}
          placeholder="Owner-reported total"
          keyboardType="numeric"
          hint="Cows tracked in the app are counted separately."
          error={err('herdSize')}
        />

        <SectionHeader title="Location" />
        <FormRow label="Address" value={address} onChangeText={setAddress}
                 placeholder="Street address" autoCapitalize="words" />
        <View style={styles.row}>
          <View style={styles.flex1}>
            <FormRow label="City" value={city} onChangeText={setCity}
                     placeholder="City" autoCapitalize="words" />
          </View>
          <View style={styles.flex1}>
            <FormRow label="Province / State" value={province} onChangeText={setProvince}
                     placeholder="Province" autoCapitalize="words" />
          </View>
        </View>
        <FormRow label="Postal / Zip Code" value={postalCode} onChangeText={setPostalCode}
                 placeholder="Postal code" autoCapitalize="characters" />

        <SectionHeader title="Contact" />
        <FormRow label="Phone" value={phone} onChangeText={setPhone}
                 placeholder="+1 (555) 000-0000" keyboardType="phone-pad" />
        <FormRow label="Email" value={email} onChangeText={setEmail}
                 placeholder="office@farm.com" keyboardType="email-address"
                 hint="Dry-off and program notifications are sent here."
                 error={err('email')} />

        <SectionHeader title="Visit Schedule" />
        <Text variant="caption" color={colors.textSecondary} style={styles.blurb}>
          Which days this farm appears on the technician's To-Do list. A 5-day farm
          is Mon–Fri; a 6-day farm is Mon–Sat. Sunday is the day off.
        </Text>
        <View style={styles.presetRow}>
          <PresetChip label="5-day (Mon–Fri)" active={sameDays(weekdays, MON_FRI)}
                      onPress={() => setWeekdays(MON_FRI)} />
          <PresetChip label="6-day (Mon–Sat)" active={sameDays(weekdays, MON_SAT)}
                      onPress={() => setWeekdays(MON_SAT)} />
        </View>
        <FormLabel>Visit days</FormLabel>
        <View style={styles.dayRow}>
          {DAY_LABELS.map((label, day) => {
            const on = weekdays.includes(day);
            return (
              <Pressable
                key={label}
                onPress={() => toggleDay(day)}
                style={[styles.day, on && styles.dayOn]}
                accessibilityRole="checkbox"
                accessibilityState={{ checked: on }}
                accessibilityLabel={`${label}${on ? ', scheduled' : ', not scheduled'}`}
              >
                <Text variant="caption" color={on ? colors.textOnPrimary : colors.textSecondary}>
                  {label}
                </Text>
              </Pressable>
            );
          })}
        </View>
        {err('weekdays') ? (
          <Text variant="caption" color={colors.danger} style={styles.blurb}>{errors.weekdays}</Text>
        ) : null}

        <SectionHeader title="Assigned Technician" />
        {technicians.length === 0 ? (
          <Text variant="caption" color={colors.textMuted} style={styles.blurb}>
            No technicians found. You can assign one later.
          </Text>
        ) : (
          <View style={styles.techList}>
            <TechOption label="Unassigned" active={!technicianId}
                        onPress={() => setTechnicianId(undefined)} />
            {technicians.map((t) => (
              <TechOption key={t.id} label={t.name} sublabel={t.email}
                          active={technicianId === t.id}
                          onPress={() => setTechnicianId(t.id)} />
            ))}
          </View>
        )}

        <SectionHeader title="Notes" />
        <FormRow value={notes} onChangeText={setNotes}
                 placeholder="Gate codes, access instructions, preferences…"
                 multiline autoCapitalize="sentences" />

        <View style={styles.actions}>
          <Button variant="secondary" label="Cancel" onPress={() => router.back()}
                  style={styles.flex1} />
          <Button
            label={isEdit ? 'Save Changes' : 'Add Farm'}
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

function PresetChip({ label, active, onPress }: { label: string; active: boolean; onPress: () => void }) {
  return (
    <Pressable
      onPress={onPress}
      style={[styles.preset, active && styles.presetOn]}
      accessibilityRole="button"
      accessibilityState={{ selected: active }}
    >
      <Text variant="caption" color={active ? colors.primary : colors.textSecondary}>{label}</Text>
    </Pressable>
  );
}

function TechOption({
  label, sublabel, active, onPress,
}: { label: string; sublabel?: string; active: boolean; onPress: () => void }) {
  return (
    <Pressable
      onPress={onPress}
      style={[styles.techRow, active && styles.techRowOn]}
      accessibilityRole="radio"
      accessibilityState={{ selected: active }}
    >
      <Ionicons
        name={active ? 'radio-button-on' : 'radio-button-off'}
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
  row: { flexDirection: 'row', gap: spacing.md },
  flex1: { flex: 1 },
  blurb: { marginBottom: spacing.md },
  presetRow: { flexDirection: 'row', gap: spacing.sm, marginBottom: spacing.md },
  preset: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  presetOn: { borderColor: colors.primary, backgroundColor: colors.primarySoft },
  dayRow: { flexDirection: 'row', gap: spacing.xs + 2, marginBottom: spacing.md },
  day: {
    flex: 1,
    minHeight: 44,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: radius.sm,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  dayOn: { backgroundColor: colors.primary, borderColor: colors.primary },
  techList: { gap: spacing.xs, marginBottom: spacing.md },
  techRow: {
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
  techRowOn: { borderColor: colors.primary, backgroundColor: colors.primarySoft },
  actions: { flexDirection: 'row', gap: spacing.md, marginTop: spacing.lg },
});
