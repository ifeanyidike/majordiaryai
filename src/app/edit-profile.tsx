import { useRouter } from 'expo-router';
import React, { useState } from 'react';
import { KeyboardAvoidingView, Platform, StyleSheet, TextInput, View } from 'react-native';
import { Button, Card, Header, Screen, Text, useToast } from '@/components';
import { colors, radius, spacing, typography } from '@/theme';
import { useAuthStore } from '@/store/useAuthStore';

function Field({
  label, value, onChangeText, placeholder, keyboardType, autoCapitalize,
}: {
  label: string;
  value: string;
  onChangeText: (t: string) => void;
  placeholder?: string;
  keyboardType?: 'default' | 'phone-pad';
  autoCapitalize?: 'none' | 'words';
}) {
  return (
    <View style={styles.field}>
      <Text variant="label" color={colors.textSecondary}>{label}</Text>
      <TextInput
        style={styles.input}
        value={value}
        onChangeText={onChangeText}
        placeholder={placeholder}
        placeholderTextColor={colors.textMuted}
        keyboardType={keyboardType}
        autoCapitalize={autoCapitalize}
      />
    </View>
  );
}

const ROLE_LABELS: Record<string, string> = {
  admin: 'System Administrator',
  farm: 'Farm Manager',
  vet: 'Veterinarian',
  technician: 'Field Technician',
};

export default function EditProfileScreen() {
  const router = useRouter();
  const toast = useToast();
  const { user, updateProfile } = useAuthStore();
  const [name, setName] = useState(user?.name ?? '');
  const [phone, setPhone] = useState(user?.phone ?? '');
  const [saving, setSaving] = useState(false);

  const dirty = name.trim() !== (user?.name ?? '') || phone.trim() !== (user?.phone ?? '');
  const valid = name.trim().length > 0;

  const save = async () => {
    setSaving(true);
    const ok = await updateProfile({ name: name.trim(), phone: phone.trim() || undefined });
    setSaving(false);
    if (ok) {
      toast.success('Profile updated');
      router.back();
    } else {
      toast.error('Could not save your profile');
    }
  };

  return (
    <Screen>
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <Header back title="Edit Profile" subtitle="Update your account details" />

        <Card style={styles.card}>
          <Field label="Full Name" value={name} onChangeText={setName} placeholder="Your name" autoCapitalize="words" />
          <Field label="Phone" value={phone} onChangeText={setPhone} placeholder="Optional" keyboardType="phone-pad" />

          <View style={styles.readonly}>
            <Text variant="label" color={colors.textSecondary}>Email</Text>
            <Text variant="body">{user?.email ?? '—'}</Text>
            <Text variant="caption" color={colors.textMuted}>Email can't be changed here.</Text>
          </View>
          <View style={styles.readonly}>
            <Text variant="label" color={colors.textSecondary}>Role</Text>
            <Text variant="body">{ROLE_LABELS[user?.role ?? 'technician']}</Text>
            <Text variant="caption" color={colors.textMuted}>Contact an administrator to change your role.</Text>
          </View>
        </Card>

        <Button
          label="Save Changes"
          icon="checkmark"
          onPress={save}
          loading={saving}
          disabled={!dirty || !valid}
          style={styles.save}
        />
      </KeyboardAvoidingView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  card: { gap: spacing.lg },
  field: { gap: spacing.xs + 2 },
  input: {
    ...typography.input,
    color: colors.text,
    backgroundColor: colors.surfaceSoft,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.sm,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.md,
  },
  readonly: {
    gap: spacing.hairline,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.border,
    paddingTop: spacing.md,
  },
  save: { marginTop: spacing.xl },
});
