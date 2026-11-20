import { useLocalSearchParams, useRouter } from 'expo-router';
import React, { useEffect, useMemo, useState } from 'react';
import { KeyboardAvoidingView, Platform, ScrollView, StyleSheet, View } from 'react-native';
import {
  Button, EmptyState, FormRow, Header, Screen, SectionHeader, useToast,
} from '@/components';
import { spacing } from '@/theme';
import { staffById, useAppStore } from '@/store/useAppStore';
import { useAuthStore } from '@/store/useAuthStore';
import { errorMessage } from '@/lib/api';

/**
 * Admin, Technicians: add a technician, or edit one (feature notes, Nov 10).
 *
 * Adding makes a working login. The admin sets the first password and gives it
 * to the technician, who can change it with Forgot Password on the sign-in
 * screen. Changing the email changes the email they sign in with.
 */

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export default function TechnicianEditScreen() {
  const { id } = useLocalSearchParams<{ id?: string }>();
  const router = useRouter();
  const toast = useToast();
  const state = useAppStore();
  const { saveTechnician, fetchStaff, demoMode } = state;
  const role = useAuthStore((s) => s.user?.role);

  const isEdit = !!id;
  const existing = id ? staffById(state, id) : null;

  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [employeeId, setEmployeeId] = useState('');
  const [region, setRegion] = useState('');
  const [password, setPassword] = useState('');
  const [saving, setSaving] = useState(false);
  const [touched, setTouched] = useState(false);

  useEffect(() => { if (isEdit && !existing) fetchStaff(); }, []);
  useEffect(() => {
    if (!existing) return;
    setName(existing.name);
    setEmail(existing.email);
    setPhone(existing.phone ?? '');
    setEmployeeId(existing.employeeId ?? '');
    setRegion(existing.region ?? '');
  }, [existing?.id]);

  const errors = useMemo(() => {
    const e: Record<string, string> = {};
    if (!name.trim()) e.name = 'Their name is required';
    if (!EMAIL_RE.test(email.trim())) e.email = 'Enter the email they will sign in with';
    if (!isEdit && password.length < 8) e.password = 'At least 8 characters';
    return e;
  }, [name, email, password, isEdit]);
  const valid = Object.keys(errors).length === 0;
  const err = (key: string) => (touched ? errors[key] : undefined);

  if (role !== 'admin') {
    return (
      <Screen>
        <Header back title={isEdit ? 'Edit Technician' : 'Add Technician'} />
        <EmptyState icon="lock-closed-outline" title="Admins only"
                    message="Technicians are managed by an administrator." />
      </Screen>
    );
  }
  if (isEdit && !existing) {
    return (
      <Screen>
        <Header back title="Edit Technician" />
        <EmptyState title={state.staffLoading ? 'Loading…' : 'Technician not found'} />
      </Screen>
    );
  }

  const submit = async () => {
    setTouched(true);
    if (!valid) return;
    if (demoMode) {
      toast.error('Demo mode — connect the API to manage technicians.');
      return;
    }
    setSaving(true);
    try {
      const savedId = await saveTechnician({
        name: name.trim(),
        email: email.trim(),
        phone: phone.trim(),
        employeeId: employeeId.trim(),
        region: region.trim(),
        password: isEdit ? undefined : password,
      }, id);
      toast.success(isEdit ? 'Technician updated' : `${name.trim()} added — they can sign in now`);
      router.replace({ pathname: '/technician/[id]', params: { id: savedId } });
    } catch (e: any) {
      toast.error(errorMessage(e, 'Could not save the technician'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Screen scroll={false} padded={false}>
      {/* Without this the bottom fields sit under the iOS keyboard. */}
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={styles.flex1}>
        <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled"
                    showsVerticalScrollIndicator={false}>
          <Header back title={isEdit ? 'Edit Technician' : 'Add Technician'}
                  subtitle={isEdit ? existing?.name : 'New technician'} />

          <SectionHeader title="Details" />
          <FormRow label="Name" value={name} onChangeText={setName} placeholder="Required"
                   autoCapitalize="words" error={err('name')} />
          <FormRow label="Email" value={email} onChangeText={setEmail} placeholder="name@company.com"
                   keyboardType="email-address" error={err('email')}
                   hint={isEdit ? 'Changing it changes the email they sign in with.' : undefined} />
          <FormRow label="Phone" value={phone} onChangeText={setPhone}
                   placeholder="+1 (555) 000-0000" keyboardType="phone-pad" />
          <FormRow label="Employee ID" value={employeeId} onChangeText={setEmployeeId}
                   placeholder="Optional" autoCapitalize="characters" />
          <FormRow label="Region" value={region} onChangeText={setRegion}
                   placeholder="Optional" autoCapitalize="words" />

          {isEdit ? null : (
            <>
              <SectionHeader title="Sign-in" />
              <FormRow label="First password" value={password} onChangeText={setPassword}
                       placeholder="At least 8 characters" error={err('password')}
                       hint="Give this to the technician. They can change it with Forgot Password." />
            </>
          )}

          <View style={styles.actions}>
            <Button variant="secondary" label="Cancel" onPress={() => router.back()} style={styles.flex1} />
            <Button label={isEdit ? 'Save Changes' : 'Add Technician'} icon="checkmark" onPress={submit}
                    loading={saving} disabled={touched && !valid} style={styles.flex1} />
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  content: { paddingHorizontal: spacing.xl, paddingBottom: spacing.huge },
  flex1: { flex: 1 },
  actions: { flexDirection: 'row', gap: spacing.md, marginTop: spacing.lg },
});
