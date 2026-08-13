import { Ionicons } from '@expo/vector-icons';
import { useLocalSearchParams, useRouter } from 'expo-router';
import React, { useEffect, useState } from 'react';
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
import { farmById, useAppStore } from '@/store/useAppStore';
import { useAuthStore } from '@/store/useAuthStore';

/**
 * A farm's bull list — the spec's "Bull Selection", which the AI form picks
 * from instead of relying on free text.
 *
 * ASSUMPTION (unconfirmed by the specs): bulls are per farm, because the spec
 * says the cow is inseminated "with semen selected by farmer". A shared stud
 * catalogue would be a different shape.
 *
 * Bulls are retired, never deleted: past inseminations reference them, and a
 * straw used last season is part of a cow's breeding history.
 */

type SemenType = 'sexed' | 'conventional' | 'beef';

export default function FarmBullsScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const toast = useToast();
  const state = useAppStore();
  const { bulls, fetchBulls, saveBull, retireBull, demoMode } = state;
  const role = useAuthStore((s) => s.user?.role);
  const farm = id ? farmById(state, id) : undefined;
  const list = (id ? bulls[id] : undefined) ?? [];

  const [name, setName] = useState('');
  const [code, setCode] = useState('');
  const [semenType, setSemenType] = useState<SemenType | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (id) fetchBulls(id);
  }, [id]);

  const canEdit = role === 'admin' || role === 'technician';

  if (!farm) {
    return (
      <Screen>
        <Header back title="Bulls" />
        <EmptyState title="Farm not found" />
      </Screen>
    );
  }

  const add = async () => {
    if (!name.trim()) {
      toast.error('Enter the bull name');
      return;
    }
    if (demoMode) {
      toast.error('Demo mode — connect the API to manage bulls.');
      return;
    }
    setSaving(true);
    try {
      await saveBull(farm.id, {
        name: name.trim(),
        code: code.trim(),
        semenType: semenType ?? undefined,
      });
      toast.success(`${name.trim()} added`);
      setName(''); setCode(''); setSemenType(null);
    } catch (e: any) {
      toast.error(e?.message ?? 'Could not add the bull');
    } finally {
      setSaving(false);
    }
  };

  const retire = async (bullId: string, bullName: string) => {
    try {
      await retireBull(farm.id, bullId);
      toast.success(`${bullName} retired — past records keep him`);
    } catch (e: any) {
      toast.error(e?.message ?? 'Could not retire the bull');
    }
  };

  return (
    <Screen scroll={false} padded={false}>
      <ScrollView
        contentContainerStyle={styles.content}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
      >
        <Header back title="Bulls" subtitle={`${farm.name} · ${list.length} in stock`} />

        <Text variant="caption" color={colors.textSecondary} style={styles.blurb}>
          Semen this farm stocks. The insemination form picks from this list, so
          the same bull is spelled the same way every time.
        </Text>

        {list.length === 0 ? (
          <EmptyState
            icon="flask-outline"
            title="No bulls listed"
            message={canEdit
              ? 'Add one below. Technicians can still type a bull name that is not listed.'
              : 'A technician or admin adds bulls to this list.'}
          />
        ) : (
          list.map((b) => (
            <View key={b.id} style={styles.row}>
              <View style={styles.flex1}>
                <Text variant="bodyBold">{b.name}</Text>
                <Text variant="caption" color={colors.textMuted}>
                  {[b.code, b.semenType].filter(Boolean).join(' · ') || 'No code'}
                </Text>
              </View>
              {canEdit && (
                <Pressable
                  onPress={() => retire(b.id, b.name)}
                  style={styles.retire}
                  accessibilityRole="button"
                  accessibilityLabel={`Retire ${b.name}`}
                >
                  <Ionicons name="archive-outline" size={16} color={colors.textSecondary} />
                  <Text variant="caption" color={colors.textSecondary}>Retire</Text>
                </Pressable>
              )}
            </View>
          ))
        )}

        {canEdit && (
          <>
            <SectionHeader title="Add a bull" />
            <FormRow label="Bull Name" value={name} onChangeText={setName}
                     placeholder="e.g. Delta-Lambda" autoCapitalize="words" />
            <FormRow label="Code" value={code} onChangeText={setCode}
                     placeholder="e.g. 7HO14454 (optional)"
                     autoCapitalize="characters" />
            <FormLabel>Semen Type</FormLabel>
            <SegmentedControl
              options={[
                { value: 'sexed', label: 'Sexed' },
                { value: 'conventional', label: 'Conv.' },
                { value: 'beef', label: 'Beef' },
              ]}
              value={semenType}
              onChange={setSemenType}
              style={styles.segment}
            />
            <Button label="Add Bull" icon="add" onPress={add} loading={saving} />
          </>
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
  retire: {
    flexDirection: 'row', alignItems: 'center', gap: spacing.xs,
    minHeight: 44, paddingHorizontal: spacing.sm,
  },
});
