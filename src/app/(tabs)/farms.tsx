import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import React, { useEffect, useMemo, useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import {
  EmptyState,
  ErrorBanner,
  Header,
  Monogram,
  PressableScale,
  Screen,
  SearchBar,
  Text,
  SkeletonList,
} from '@/components';
import { charcoal, colors, cream, radius, red, shadows, spacing, touch } from '@/theme';
import { dial } from '@/lib/contact';
import { Farm } from '@/data/types';
import { useAppStore } from '@/store/useAppStore';
import { useAuthStore, useRole } from '@/store/useAuthStore';

/**
 * Per-farm identity accents drawn from the brand ramps only — semantic
 * status colors are reserved for cow statuses.
 */
const ACCENTS = [
  { fg: colors.primary, bg: colors.primarySoft },
  { fg: charcoal[600], bg: charcoal[50] },
  { fg: red[700], bg: red[50] },
  { fg: charcoal[400], bg: cream.mist },
];

/** Stable accent per farm regardless of list order or filtering */
function accentFor(farm: Farm) {
  let hash = 0;
  for (let i = 0; i < farm.id.length; i++) hash = (hash + farm.id.charCodeAt(i)) % 997;
  return ACCENTS[hash % ACCENTS.length];
}

export default function FarmsScreen() {
  const router = useRouter();
  const [query, setQuery] = useState('');
  const { farms, farmsLoading, farmsError, fetchFarms } = useAppStore();
  const { user } = useAuthStore();

  useEffect(() => { fetchFarms(); }, []);

  const role = useRole();

  const totalCows = farms.reduce((n, f) => n + f.herdSize, 0);
  const cities = new Set(farms.map((f) => f.city)).size;

  const results = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return farms;
    return farms.filter(
      (f) =>
        f.name.toLowerCase().includes(q) ||
        f.owner.toLowerCase().includes(q) ||
        f.city.toLowerCase().includes(q),
    );
  }, [query, farms]);

  return (
    <Screen refreshing={farmsLoading && farms.length > 0} onRefresh={fetchFarms}>
      <Header
        title="Farms CRM"
        subtitle={
          role === 'admin'
            ? 'All farms in the system'
            : role === 'vet'
              ? 'Farms under your care'
              : 'Your assigned region'
        }
        right={
          role === 'admin' ? (
            <Pressable
              onPress={() => router.push('/farm/edit')}
              style={styles.addBtn}
              accessibilityRole="button"
              accessibilityLabel="Add farm"
            >
              <Ionicons name="add" size={20} color={colors.textOnPrimary} />
            </Pressable>
          ) : undefined
        }
      />

      {/* stats ribbon */}
      <View style={styles.ribbon}>
        <View style={styles.ribbonItem}>
          <Text variant="stat" color={colors.primary}>
            {farms.length}
          </Text>
          <Text variant="caption" color={colors.textSecondary}>
            Farms
          </Text>
        </View>
        <View style={[styles.ribbonItem, styles.ribbonDivider]}>
          <Text variant="stat">{totalCows.toLocaleString()}</Text>
          <Text variant="caption" color={colors.textSecondary}>
            Tracked cows
          </Text>
        </View>
        <View style={[styles.ribbonItem, styles.ribbonDivider]}>
          <Text variant="stat">{cities}</Text>
          <Text variant="caption" color={colors.textSecondary}>
            Cities
          </Text>
        </View>
      </View>

      <SearchBar value={query} onChangeText={setQuery} placeholder="Search farms, owners, cities" />

      <View style={styles.list}>
        {farmsError ? <ErrorBanner message={farmsError} onRetry={fetchFarms} /> : null}
        {farmsLoading && farms.length === 0 ? (
          <View style={{ marginTop: spacing.lg }}><SkeletonList count={5} /></View>
        ) : !farmsError && results.length === 0 ? (
          <EmptyState
            icon="business-outline"
            title={query ? 'No matches' : 'No farms yet'}
            message={query
              ? `Nothing matches "${query}".`
              : role === 'admin'
                ? 'Add the first farm to start tracking a herd.'
                : 'No farms are assigned to you yet — an administrator assigns them.'}
            action={query
              ? { label: 'Clear search', icon: 'close', onPress: () => setQuery('') }
              : role === 'admin'
                ? { label: 'Add farm', icon: 'add', onPress: () => router.push('/farm/edit') }
                : undefined}
          />
        ) : (
          results.map((farm) => {
            const accent = accentFor(farm);
            return (
              // Row container is a plain View so the phone button and the row
              // press are truly independent targets.
              <View key={farm.id} style={styles.farmRow}>
                <PressableScale
                  scaleTo={0.98}
                  onPress={() => router.push({ pathname: '/farm/[id]', params: { id: farm.id } })}
                  style={styles.farmMain}
                  accessibilityRole="button"
                  accessibilityLabel={`Open ${farm.name}`}
                >
                  <Monogram name={farm.name} bg={accent.bg} color={accent.fg} size={50} />
                  <View style={styles.farmText}>
                    <Text variant="subheading" numberOfLines={1}>
                      {farm.name}
                    </Text>
                    <Text variant="caption" color={colors.textSecondary} numberOfLines={1}>
                      {farm.owner} · {farm.city}
                    </Text>
                    <View style={styles.cowChip}>
                      <Ionicons name="analytics-outline" size={11} color={accent.fg} />
                      <Text variant="label" color={accent.fg} style={styles.cowChipText}>
                        {farm.herdSize} cows
                      </Text>
                    </View>
                  </View>
                </PressableScale>
                <Pressable
                  style={styles.phoneBtn}
                  onPress={() => dial(farm.phone)}
                  accessibilityRole="button"
                  accessibilityLabel={`Call ${farm.name}`}
                  hitSlop={4}
                >
                  <Ionicons name="call" size={18} color={colors.primary} />
                </Pressable>
              </View>
            );
          })
        )}
      </View>

      <Text variant="caption" color={colors.textMuted} style={styles.hint}>
        Tap a farm to open its profile
      </Text>
    </Screen>
  );
}

const styles = StyleSheet.create({
  addBtn: {
    width: 40, height: 40, borderRadius: 20,
    backgroundColor: colors.primary,
    alignItems: 'center', justifyContent: 'center',
  },
  ribbon: {
    flexDirection: 'row',
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    paddingVertical: spacing.lg,
    marginBottom: spacing.lg,
    ...shadows.card,
  },
  ribbonItem: { flex: 1, alignItems: 'center', gap: 1 },
  ribbonDivider: { borderLeftWidth: 1, borderLeftColor: colors.border },
  list: { marginTop: spacing.xl },
  farmRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.lg,
    marginBottom: spacing.sm + 2,
    minHeight: 64,
    ...shadows.card,
  },
  farmMain: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
  },
  farmText: { flex: 1, gap: 2 },
  cowChip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    alignSelf: 'flex-start',
    marginTop: 2,
  },
  cowChipText: { letterSpacing: 0.4 },
  phoneBtn: {
    width: touch.iconButton,
    height: touch.iconButton,
    borderRadius: touch.iconButton / 2,
    backgroundColor: colors.primarySoft,
    alignItems: 'center',
    justifyContent: 'center',
  },
  hint: { textAlign: 'center', marginTop: spacing.md },
});
