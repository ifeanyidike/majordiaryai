import { Ionicons } from '@expo/vector-icons';
import { useLocalSearchParams, useRouter } from 'expo-router';
import React, { useEffect, useMemo, useState } from 'react';
import { FlatList, Pressable, RefreshControl, StyleSheet, View } from 'react-native';
import Animated from 'react-native-reanimated';
import {
  EmptyState, ErrorBanner, FilterChips, Header, ListRow, Screen, SearchBar, StatusPill,
  SkeletonList, STATUS_LABELS, Text,
} from '@/components';
import { Cow, CowStatus } from '@/data/types';
import { colors, spacing, useMotion } from '@/theme';
import { cowsByFarm, farmById, useAppStore } from '@/store/useAppStore';
import { useAuthStore } from '@/store/useAuthStore';

// The order a farmer thinks of the cycle in, not alphabetical.
const STATUS_ORDER: CowStatus[] = [
  'fresh', 'open', 'needling', 'inseminated', 'pregnant', 'dry',
  'heifer', 'calf', 'cull', 'sold', 'dead',
];

type DimBand = 'any' | 'lt60' | '60to150' | '151to305' | 'gt305';
const DIM_BANDS: { value: DimBand; label: string; test: (dim: number) => boolean }[] = [
  { value: 'any', label: 'Any', test: () => true },
  { value: 'lt60', label: 'Under 60', test: (d) => d < 60 },
  { value: '60to150', label: '60–150', test: (d) => d >= 60 && d <= 150 },
  { value: '151to305', label: '151–305', test: (d) => d > 150 && d <= 305 },
  // 305 days is a standard lactation; past it she is running long.
  { value: 'gt305', label: 'Over 305', test: (d) => d > 305 },
];

/** Tags are written with spaces ("CA 124 578 1042") and typed without. */
const squash = (s: string) => s.toLowerCase().replace(/\s+/g, '');

function matchesSearch(cow: Cow, query: string): boolean {
  const q = squash(query);
  if (!q) return true;
  return squash(cow.earTag ?? '').includes(q) || squash(cow.name ?? '').includes(q);
}

/** Days in milk only means something for a cow that is milking. */
function inDimBand(cow: Cow, band: DimBand): boolean {
  if (band === 'any') return true;
  if (!cow.isMilking || !cow.lastCalvingDate) return false;
  return DIM_BANDS.find((b) => b.value === band)!.test(cow.daysInMilk);
}

export default function HerdScreen() {
  const motion = useMotion();
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const state = useAppStore();
  const farm = farmById(state, id);
  const herd = cowsByFarm(state, id);
  const { fetchCows, cowsLoading, cowsError } = state;
  const role = useAuthStore((s) => s.user?.role);
  const canEdit = role === 'admin' || role === 'technician';

  useEffect(() => {
    fetchCows(id);
  }, [id]);

  const subtitle = farm
    ? `${farm.name} · ${herd.length} tracked cows`
    : `${herd.length} tracked cows`;
  const loading = cowsLoading && herd.length === 0;

  // Josh, Oct 2: search by name or tag; filter by status or days in milk.
  const [query, setQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<CowStatus | 'all'>('all');
  const [dimBand, setDimBand] = useState<DimBand>('any');
  const filtering = query.trim() !== '' || statusFilter !== 'all' || dimBand !== 'any';

  // Each chip counts what it would show alongside the OTHER active filters,
  // so a zero warns before the tap rather than after it.
  const statusChips = useMemo(() => {
    const base = herd.filter((c) => matchesSearch(c, query) && inDimBand(c, dimBand));
    // The selected status stays even if a refresh empties it — otherwise its
    // chip vanished while still filtering the list down to nothing.
    const present = STATUS_ORDER.filter(
      (st) => st === statusFilter || herd.some((c) => c.status === st),
    );
    return [
      { value: 'all' as const, label: 'All', count: base.length },
      ...present.map((st) => ({
        value: st,
        label: STATUS_LABELS[st as keyof typeof STATUS_LABELS] ?? st,
        count: base.filter((c) => c.status === st).length,
      })),
    ];
  }, [herd, query, dimBand, statusFilter]);

  const dimChips = useMemo(() => {
    const base = herd.filter(
      (c) => matchesSearch(c, query) && (statusFilter === 'all' || c.status === statusFilter),
    );
    return DIM_BANDS.map((b) => ({
      value: b.value, label: b.label,
      count: base.filter((c) => inDimBand(c, b.value)).length,
    }));
  }, [herd, query, statusFilter]);

  const shown = useMemo(
    () => herd.filter((c) =>
      matchesSearch(c, query)
      && (statusFilter === 'all' || c.status === statusFilter)
      && inDimBand(c, dimBand)),
    [herd, query, statusFilter, dimBand],
  );

  return (
    <Screen scroll={false} padded={false}>
      <FlatList
        data={shown}
        keyExtractor={(cow) => cow.id}
        // A chip tap with the keyboard up should filter, not just close it.
        keyboardShouldPersistTaps="handled"
        contentContainerStyle={{ paddingHorizontal: spacing.xl, paddingBottom: spacing.huge }}
        refreshControl={
          <RefreshControl
            refreshing={cowsLoading && herd.length > 0}
            onRefresh={() => fetchCows(id)}
            tintColor={colors.primary}
            colors={[colors.primary]}
          />
        }
        ListHeaderComponent={
          <>
            <Header
              back
              title="Herd"
              subtitle={subtitle}
              right={
                canEdit ? (
                  <Pressable
                    onPress={() => router.push({ pathname: '/cow/edit', params: { farmId: id } })}
                    style={styles.addBtn}
                    accessibilityRole="button"
                    accessibilityLabel="Add cow to this farm"
                  >
                    <Ionicons name="add" size={20} color={colors.textOnPrimary} />
                  </Pressable>
                ) : undefined
              }
            />
            {cowsError ? <ErrorBanner message={cowsError} onRetry={() => fetchCows(id)} /> : null}
            {herd.length > 0 ? (
              <View style={styles.filters}>
                <SearchBar
                  value={query}
                  onChangeText={setQuery}
                  placeholder="Search by name or ear tag"
                />
                <FilterChips
                  label="Status"
                  chips={statusChips}
                  value={statusFilter}
                  onChange={setStatusFilter}
                />
                <FilterChips
                  label="Days in milk"
                  chips={dimChips}
                  value={dimBand}
                  onChange={setDimBand}
                />
                {filtering ? (
                  <Text variant="caption" color={colors.textSecondary}>
                    {shown.length} of {herd.length} cows
                  </Text>
                ) : null}
              </View>
            ) : null}
            {loading ? (
              <View style={{ marginTop: spacing.lg }}><SkeletonList count={6} /></View>
            ) : null}
          </>
        }
        ListEmptyComponent={
          loading || cowsError ? null : herd.length > 0 ? (
            <EmptyState
              icon="search-outline"
              title="No cows match"
              message="Try another name or tag, or clear a filter."
            />
          ) : (
            <EmptyState title="No cows tracked yet" message={canEdit ? 'Add one with the + button above.' : undefined} />
          )
        }
        renderItem={({ item: cow, index }) => (
          <Animated.View entering={motion.down(index)}>
            <ListRow
              icon="analytics-outline"
              title={cow.label}
              // Blank parts are left out: a herd from DairyComp often has no
              // breed, and days in milk means nothing on a heifer.
              subtitle={[
                cow.breed, `Lact ${cow.lactationNumber}`,
                cow.isMilking ? `${cow.daysInMilk} DIM` : null,
              ].filter(Boolean).join(' · ')}
              badge={<StatusPill kind={cow.status} />}
              onPress={() => router.push({ pathname: '/cow/[id]', params: { id: cow.id } })}
            />
          </Animated.View>
        )}
      />
    </Screen>
  );
}

const styles = StyleSheet.create({
  filters: { gap: spacing.md, marginBottom: spacing.lg },
  addBtn: {
    width: 40, height: 40, borderRadius: 20,
    backgroundColor: colors.primary,
    alignItems: 'center', justifyContent: 'center',
  },
});
