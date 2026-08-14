import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import React, { useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, View } from 'react-native';
import {
  Button,
  EmptyState,
  Header,
  Screen,
  SectionHeader,
  SegmentedControl,
  Text,
  useToast,
} from '@/components';
import { colors, radius, spacing } from '@/theme';
import { StaffUser } from '@/data/types';
import { useAppStore } from '@/store/useAppStore';
import { useAuthStore } from '@/store/useAuthStore';

/**
 * People — assign roles and farms.
 *
 * This is how a Farm Manager is made. Signup refuses the admin role and ignores
 * farm_id, so an account created in the app arrives with no farm attached; a
 * farm manager without one logs in to a completely empty system with no
 * explanation. There was previously no way to fix that from anywhere.
 */

const ROLES = [
  { value: 'admin', label: 'Admin' },
  { value: 'technician', label: 'Technician' },
  { value: 'farm', label: 'Farm Mgr' },
  { value: 'vet', label: 'Vet' },
] as const;

type Role = (typeof ROLES)[number]['value'];

const ROLE_BLURB: Record<Role, string> = {
  admin: 'Full access to every farm, and the only role that can manage people.',
  technician: 'Sees the daily To-Do route for farms they are assigned to.',
  farm: 'Sees one farm only — pick it below, or they see nothing.',
  vet: 'Pregnancy checks. Assign their farms on the vet record.',
};

export default function UsersScreen() {
  const router = useRouter();
  const toast = useToast();
  const state = useAppStore();
  const { staff, staffLoading, fetchStaff, updateStaffUser, farms, fetchFarms } = state;
  const me = useAuthStore((s) => s.user);

  const [editing, setEditing] = useState<StaffUser | null>(null);
  const [role, setRole] = useState<Role>('technician');
  const [farmId, setFarmId] = useState<string | undefined>();
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    fetchStaff();
    if (farms.length === 0) fetchFarms();
  }, []);

  if (me?.role !== 'admin') {
    return (
      <Screen>
        <Header back title="People" />
        <EmptyState
          icon="lock-closed-outline"
          title="Admins only"
          message="Roles and farm assignments are managed by an administrator."
        />
      </Screen>
    );
  }

  const open = (u: StaffUser) => {
    setEditing(u);
    setRole((u.role as Role) ?? 'technician');
    setFarmId(u.farmId);
  };

  const save = async () => {
    if (!editing) return;
    if (role === 'farm' && !farmId) {
      toast.error('Pick the farm this manager belongs to.');
      return;
    }
    setSaving(true);
    try {
      await updateStaffUser(editing.id, {
        role,
        farmId: role === 'farm' ? farmId : undefined,
      });
      toast.success(`${editing.name} updated`);
      setEditing(null);
    } catch (e: any) {
      toast.error(e?.message ?? 'Could not update this person');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Screen scroll={false} padded={false}>
      <ScrollView
        contentContainerStyle={styles.content}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
      >
        <Header back title="People" subtitle={`${staff.length} accounts`} />

        {staffLoading && staff.length === 0 ? (
          <ActivityIndicator color={colors.primary} style={{ marginTop: spacing.xxl }} />
        ) : staff.length === 0 ? (
          <EmptyState
            icon="people-outline"
            title="No accounts yet"
            message="People appear here once they sign up in the app."
          />
        ) : (
          ROLES.map((r) => {
            const group = staff.filter((u) => u.role === r.value);
            if (group.length === 0) return null;
            return (
              <View key={r.value}>
                <SectionHeader title={`${r.label} (${group.length})`} />
                {group.map((u) => (
                  <Pressable
                    key={u.id}
                    onPress={() => open(u)}
                    style={styles.row}
                    accessibilityRole="button"
                    accessibilityLabel={`Edit ${u.name}`}
                  >
                    <View style={styles.flex1}>
                      <Text variant="bodyBold">{u.name}</Text>
                      <Text variant="caption" color={colors.textMuted} numberOfLines={1}>
                        {u.email}
                        {u.role === 'farm'
                          ? u.farmName
                            ? ` · ${u.farmName}`
                            : ' · NO FARM — sees nothing'
                          : ''}
                      </Text>
                    </View>
                    <Ionicons name="chevron-forward" size={18} color={colors.textMuted} />
                  </Pressable>
                ))}
              </View>
            );
          })
        )}

        {editing && (
          <View style={styles.editor}>
            <SectionHeader title={`Edit ${editing.name}`} />
            <Text variant="caption" color={colors.textMuted} style={styles.blurb}>
              {editing.email}
            </Text>

            <SegmentedControl
              options={ROLES.map((r) => ({ value: r.value, label: r.label }))}
              value={role}
              onChange={(v) => setRole(v as Role)}
              style={styles.segment}
            />
            <Text variant="caption" color={colors.textSecondary} style={styles.blurb}>
              {ROLE_BLURB[role]}
            </Text>

            {role === 'farm' && (
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
                      <Ionicons
                        name={on ? 'radio-button-on' : 'radio-button-off'}
                        size={18}
                        color={on ? colors.primary : colors.textMuted}
                      />
                      <Text variant="body">{f.name}</Text>
                    </Pressable>
                  );
                })}
              </View>
            )}

            {editing.id === me?.id && (
              <Text variant="caption" color={colors.textMuted} style={styles.blurb}>
                This is you — your own role can only be changed by another admin,
                so nobody can lock everyone out.
              </Text>
            )}

            <View style={styles.actions}>
              <Button compact variant="secondary" label="Cancel"
                      onPress={() => setEditing(null)} style={styles.flex1} />
              <Button compact label="Save" icon="checkmark" onPress={save}
                      loading={saving} style={styles.flex1} />
            </View>
          </View>
        )}
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  content: { paddingHorizontal: spacing.xl, paddingBottom: spacing.huge },
  flex1: { flex: 1 },
  blurb: { marginBottom: spacing.md },
  segment: { marginBottom: spacing.md },
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
    marginBottom: spacing.xs,
    minHeight: 56,
  },
  editor: {
    marginTop: spacing.lg,
    padding: spacing.lg,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.primary,
    backgroundColor: colors.surface,
  },
  farmList: { gap: spacing.xs, marginBottom: spacing.md },
  farmRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.md,
    borderRadius: radius.sm,
    borderWidth: 1,
    borderColor: colors.border,
    minHeight: 48,
  },
  farmRowOn: { borderColor: colors.primary, backgroundColor: colors.primarySoft },
  actions: { flexDirection: 'row', gap: spacing.md, marginTop: spacing.sm },
});
