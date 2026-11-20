import { Ionicons } from '@expo/vector-icons';
import { useLocalSearchParams, useRouter } from 'expo-router';
import React, { useEffect, useMemo, useState } from 'react';
import { Modal, Pressable, ScrollView, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import {
  Button, EmptyState, Header, ModalToastHost, Screen, Text, useToast,
} from '@/components';
import { colors, radius, shadows, spacing } from '@/theme';
import { allTechnicians, farmsOnRoute, staffById, useAppStore } from '@/store/useAppStore';
import { useAuthStore } from '@/store/useAuthStore';
import { StaffUser } from '@/data/types';
import { errorMessage } from '@/lib/api';

/**
 * Admin, Routes, one technician (feature notes, Nov 10): their farms, each with
 * a checkbox, and Reassign at the bottom. Reassign lists the technicians again;
 * the one picked receives every checked farm, and both are sent a message.
 */
export default function RouteScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const toast = useToast();
  const insets = useSafeAreaInsets();
  const state = useAppStore();
  const { reassignFarms, fetchStaff, fetchFarms, demoMode } = state;
  const role = useAuthStore((s) => s.user?.role);

  const tech = staffById(state, id);
  const farms = farmsOnRoute(state, id);
  const others = allTechnicians(state).filter((t) => t.id !== id);

  const [checked, setChecked] = useState<string[]>([]);
  const [picking, setPicking] = useState(false);
  const [target, setTarget] = useState<StaffUser | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (state.staff.length === 0) fetchStaff();
    fetchFarms();
  }, []);
  // A farm that has left this route since it was checked cannot stay checked.
  const onRoute = useMemo(() => new Set(farms.map((f) => f.id)), [farms]);
  const chosen = checked.filter((f) => onRoute.has(f));

  if (role !== 'admin') {
    return (
      <Screen>
        <Header back title="Route" />
        <EmptyState icon="lock-closed-outline" title="Admins only"
                    message="Routes are managed by an administrator." />
      </Screen>
    );
  }
  if (!tech) {
    return (
      <Screen>
        <Header back title="Route" />
        <EmptyState title={state.staffLoading ? 'Loading…' : 'Technician not found'} />
      </Screen>
    );
  }

  const toggle = (farmId: string) =>
    setChecked((ids) => (ids.includes(farmId) ? ids.filter((f) => f !== farmId) : [...ids, farmId]));
  const allChecked = farms.length > 0 && chosen.length === farms.length;

  const close = () => { setPicking(false); setTarget(null); };

  const move = async () => {
    // After a refused move the list is reloaded, and the checked farms may all
    // have left this route; there is then nothing to move.
    if (!target || chosen.length === 0) return;
    if (demoMode) {
      toast.error('Demo mode — connect the API to change routes.');
      return;
    }
    setSaving(true);
    try {
      await reassignFarms(tech.id, target.id, chosen);
      const n = chosen.length;
      toast.success(`${n} ${n === 1 ? 'farm' : 'farms'} moved to ${target.name}`);
      setChecked([]);
      close();
    } catch (e: any) {
      toast.error(errorMessage(e, 'Could not move the farms'));
      // The route may have changed under us; show it as it is now.
      fetchFarms();
    } finally {
      setSaving(false);
    }
  };

  return (
    <Screen scroll={false} padded={false}>
      <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
        <Header back title={tech.name} subtitle={`Route · ${farms.length} ${farms.length === 1 ? 'farm' : 'farms'}`} />
        {farms.length === 0 ? (
          <EmptyState icon="business-outline" title="No farms on this route" />
        ) : (
          <>
            <Pressable
              onPress={() => setChecked(allChecked ? [] : farms.map((f) => f.id))}
              style={styles.selectAll}
              accessibilityRole="button"
            >
              <Text variant="bodyBold" color={colors.primary}>
                {allChecked ? 'Clear all' : 'Check all'}
              </Text>
            </Pressable>
            <View style={styles.list}>
              {farms.map((f) => {
                const on = chosen.includes(f.id);
                return (
                  <Pressable
                    key={f.id}
                    onPress={() => toggle(f.id)}
                    style={[styles.row, on && styles.rowOn]}
                    accessibilityRole="checkbox"
                    accessibilityState={{ checked: on }}
                    accessibilityLabel={f.name}
                  >
                    <Ionicons name={on ? 'checkbox' : 'square-outline'} size={22}
                              color={on ? colors.primary : colors.textMuted} />
                    <View style={styles.flex1}>
                      <Text variant="body">{f.name}</Text>
                      <Text variant="caption" color={colors.textMuted} numberOfLines={1}>
                        {[f.city, f.province].filter(Boolean).join(', ') || f.owner}
                      </Text>
                    </View>
                  </Pressable>
                );
              })}
            </View>
          </>
        )}
      </ScrollView>

      {farms.length > 0 ? (
        <View style={[styles.bar, { paddingBottom: insets.bottom + spacing.md }]}>
          <Button
            label={chosen.length ? `Reassign ${chosen.length} ${chosen.length === 1 ? 'farm' : 'farms'}` : 'Reassign'}
            icon="swap-horizontal"
            disabled={chosen.length === 0}
            onPress={() => setPicking(true)}
          />
        </View>
      ) : null}

      <Modal visible={picking} transparent animationType="slide" onRequestClose={close}>
        <View style={styles.modalRoot}>
          <Pressable style={styles.backdrop} onPress={close} accessibilityRole="button"
                     accessibilityLabel="Dismiss" />
          <View style={[styles.sheet, { paddingBottom: insets.bottom + spacing.lg }]}>
            {picking && <ModalToastHost />}
            <View style={styles.handle} />
            {target ? (
              <>
                <Text variant="heading">Move to {target.name}?</Text>
                <Text variant="body" color={colors.textSecondary} style={styles.sheetText}>
                  {chosen.length} {chosen.length === 1 ? 'farm moves' : 'farms move'} from {tech.name} to{' '}
                  {target.name}. Both of them get a message.
                </Text>
                <View style={styles.actions}>
                  <Button variant="secondary" label="Back" onPress={() => setTarget(null)} style={styles.flex1} />
                  <Button label="Move" icon="checkmark" loading={saving} onPress={move}
                          disabled={chosen.length === 0} style={styles.flex1} />
                </View>
              </>
            ) : (
              <>
                <Text variant="heading">Reassign to</Text>
                <Text variant="caption" color={colors.textSecondary} style={styles.sheetText}>
                  The technician who takes the {chosen.length} checked {chosen.length === 1 ? 'farm' : 'farms'}.
                </Text>
                <ScrollView style={styles.picker}>
                  {others.length === 0 ? (
                    <Text variant="body" color={colors.textMuted}>No other technicians.</Text>
                  ) : others.map((t) => (
                    <Pressable
                      key={t.id}
                      disabled={!t.isActive}
                      onPress={() => setTarget(t)}
                      style={[styles.row, !t.isActive && styles.rowOff]}
                      accessibilityRole="button"
                    >
                      <Ionicons name="person-circle-outline" size={24}
                                color={t.isActive ? colors.primary : colors.textMuted} />
                      <View style={styles.flex1}>
                        <Text variant="body" color={t.isActive ? colors.text : colors.textMuted}>{t.name}</Text>
                        <Text variant="caption" color={colors.textMuted}>
                          {t.isActive
                            ? farmCount(farmsOnRoute(state, t.id).length)
                            : 'Waiting for approval under People'}
                        </Text>
                      </View>
                    </Pressable>
                  ))}
                </ScrollView>
              </>
            )}
          </View>
        </View>
      </Modal>
    </Screen>
  );
}

const farmCount = (n: number) => `${n} ${n === 1 ? 'farm' : 'farms'} now`;

const styles = StyleSheet.create({
  content: { paddingHorizontal: spacing.xl, paddingBottom: spacing.huge * 2 },
  flex1: { flex: 1 },
  selectAll: { alignSelf: 'flex-end', paddingVertical: spacing.sm, marginBottom: spacing.xs },
  list: { gap: spacing.xs },
  row: {
    flexDirection: 'row', alignItems: 'center', gap: spacing.md,
    paddingVertical: spacing.md, paddingHorizontal: spacing.md,
    borderRadius: radius.sm, borderWidth: 1, borderColor: colors.border,
    backgroundColor: colors.surface, minHeight: 56, marginBottom: spacing.xs,
  },
  rowOn: { borderColor: colors.primary, backgroundColor: colors.primarySoft },
  rowOff: { opacity: 0.6 },
  bar: {
    position: 'absolute', left: 0, right: 0, bottom: 0,
    paddingHorizontal: spacing.xl, paddingTop: spacing.md,
    backgroundColor: colors.background, borderTopWidth: 1, borderTopColor: colors.border,
    ...shadows.card,
  },
  modalRoot: { flex: 1, justifyContent: 'flex-end' },
  backdrop: { ...StyleSheet.absoluteFill, backgroundColor: 'rgba(0,0,0,0.4)' },
  sheet: {
    backgroundColor: colors.background, borderTopLeftRadius: radius.lg, borderTopRightRadius: radius.lg,
    paddingHorizontal: spacing.xl, paddingTop: spacing.md, maxHeight: '80%',
  },
  handle: {
    alignSelf: 'center', width: 40, height: 4, borderRadius: 2,
    backgroundColor: colors.border, marginBottom: spacing.md,
  },
  sheetText: { marginTop: spacing.xs, marginBottom: spacing.md },
  picker: { flexGrow: 0 },
  actions: { flexDirection: 'row', gap: spacing.md, marginTop: spacing.sm },
});
