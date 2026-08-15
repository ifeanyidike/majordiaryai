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
import { VetInput, useAppStore, vetById } from '@/store/useAppStore';
import { useAuthStore } from '@/store/useAuthStore';

/**
 * Add / edit a veterinarian and the farms they cover.
 *
 * The farm assignments are the load-bearing part: a vet's whole app is scoped
 * by `vet_farm_assignments`, so an unassigned vet logs in to an empty system.
 * Until now the only way to create one was a database script.
 */

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export default function VetEditScreen() {
  const { id } = useLocalSearchParams<{ id?: string }>();
  const router = useRouter();
  const toast = useToast();
  const state = useAppStore();
  const { saveVet, farms, fetchFarms, fetchVets, demoMode } = state;
  const role = useAuthStore((s) => s.user?.role);

  const existing = id ? vetById(state, id) : undefined;
  const isEdit = !!id;

  const [name, setName] = useState('');
  const [clinic, setClinic] = useState('');
  const [phone, setPhone] = useState('');
  const [email, setEmail] = useState('');
  const [farmIds, setFarmIds] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [touched, setTouched] = useState(false);

  useEffect(() => {
    if (farms.length === 0) fetchFarms();
    fetchVets();
  }, []);

  useEffect(() => {
    if (!existing) return;
    setName(existing.name);
    setClinic(existing.clinic ?? '');
    setPhone(existing.phone ?? '');
    setEmail(existing.email ?? '');
    setFarmIds(existing.farmIds ?? []);
  }, [existing?.id]);

  const errors = useMemo(() => {
    const e: Record<string, string> = {};
    if (!name.trim()) e.name = "The veterinarian's name is required";
    if (email.trim() && !EMAIL_RE.test(email.trim())) e.email = 'Enter a valid email address';
    return e;
  }, [name, email]);

  const valid = Object.keys(errors).length === 0;

  if (role !== 'admin') {
    return (
      <Screen>
        <Header back title={isEdit ? 'Edit Vet' : 'Add Vet'} />
        <EmptyState
          icon="lock-closed-outline"
          title="Admins only"
          message="Veterinarians are managed by an administrator."
        />
      </Screen>
    );
  }

  if (isEdit && !existing) {
    return (
      <Screen>
        <Header back title="Edit Vet" />
        <EmptyState title="Vet not found" />
      </Screen>
    );
  }

  const toggleFarm = (farmId: string) =>
    setFarmIds((ids) =>
      ids.includes(farmId) ? ids.filter((f) => f !== farmId) : [...ids, farmId],
    );

  const submit = async () => {
    setTouched(true);
    if (!valid) return;
    if (demoMode) {
      toast.error('Demo mode — connect the API to save vets.');
      return;
    }
    setSaving(true);
    try {
      const input: VetInput = {
        name: name.trim(),
        clinic: clinic.trim(),
        phone: phone.trim(),
        email: email.trim(),
        farmIds,
      };
      const savedId = await saveVet(input, id);
      toast.success(isEdit ? 'Vet updated' : `${input.name} added`);
      router.replace({ pathname: '/vet/[id]', params: { id: savedId } });
    } catch (e: any) {
      toast.error(e?.message ?? 'Could not save the vet');
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
          title={isEdit ? 'Edit Vet' : 'Add Vet'}
          subtitle={isEdit ? existing?.name : 'New veterinarian'}
        />

        <SectionHeader title="Details" />
        <FormRow label="Name" value={name} onChangeText={setName}
                 placeholder="Required" autoCapitalize="words" error={err('name')} />
        <FormRow label="Clinic" value={clinic} onChangeText={setClinic}
                 placeholder="Practice or clinic name" autoCapitalize="words" />
        <FormRow label="Phone" value={phone} onChangeText={setPhone}
                 placeholder="+1 (555) 000-0000" keyboardType="phone-pad" />
        <FormRow label="Email" value={email} onChangeText={setEmail}
                 placeholder="vet@clinic.com" keyboardType="email-address"
                 error={err('email')} />

        <SectionHeader title="Farms Covered" />
        <Text variant="caption" color={colors.textSecondary} style={styles.blurb}>
          A vet only sees cows on the farms assigned here — with none selected they
          log in to an empty app.
        </Text>
        {farms.length === 0 ? (
          <Text variant="caption" color={colors.textMuted} style={styles.blurb}>
            No farms exist yet.
          </Text>
        ) : (
          <View style={styles.list}>
            {farms.map((f) => {
              const on = farmIds.includes(f.id);
              return (
                <Pressable
                  key={f.id}
                  onPress={() => toggleFarm(f.id)}
                  style={[styles.row, on && styles.rowOn]}
                  accessibilityRole="checkbox"
                  accessibilityState={{ checked: on }}
                >
                  <Ionicons
                    name={on ? 'checkbox' : 'square-outline'}
                    size={20}
                    color={on ? colors.primary : colors.textMuted}
                  />
                  <View style={styles.flex1}>
                    <Text variant="body">{f.name}</Text>
                    <Text variant="caption" color={colors.textMuted} numberOfLines={1}>
                      {[f.city, f.province].filter(Boolean).join(', ')}
                    </Text>
                  </View>
                </Pressable>
              );
            })}
          </View>
        )}

        <View style={styles.actions}>
          <Button variant="secondary" label="Cancel" onPress={() => router.back()}
                  style={styles.flex1} />
          <Button
            label={isEdit ? 'Save Changes' : 'Add Vet'}
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
  blurb: { marginBottom: spacing.md },
  list: { gap: spacing.xs, marginBottom: spacing.md },
  row: {
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
  rowOn: { borderColor: colors.primary, backgroundColor: colors.primarySoft },
  actions: { flexDirection: 'row', gap: spacing.md, marginTop: spacing.lg },
});
