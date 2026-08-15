import { useRouter } from 'expo-router';
import React, { useMemo, useState } from 'react';
import { StyleSheet, View } from 'react-native';
import Animated from 'react-native-reanimated';
import { EmptyState, ErrorBanner, Header, ListRow, Screen, SearchBar, StatusPill, Text, SkeletonList } from '@/components';
import { colors, spacing, useMotion } from '@/theme';
import { farmById, useAppStore, visibleCows } from '@/store/useAppStore';

export default function CowSearchScreen() {
  const motion = useMotion();
  const router = useRouter();
  const state = useAppStore();
  const cows = visibleCows(state);
  const { cowsLoading, cowsError, fetchCows } = state;
  const [query, setQuery] = useState('');

  const results = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return cows;
    return cows.filter(
      (c) =>
        c.id.toLowerCase().includes(q) ||
        c.earTag.toLowerCase().includes(q) ||
        c.breed.toLowerCase().includes(q) ||
        farmById(state, c.farmId)?.name.toLowerCase().includes(q),
    );
  }, [query, state]);

  return (
    <Screen refreshing={cowsLoading && cows.length > 0} onRefresh={() => fetchCows()}>
      <Header back title="Cow Search" subtitle={`${cows.length} cows tracked`} />
      <SearchBar
        value={query}
        onChangeText={setQuery}
        placeholder="Search by ID, ear tag, breed, farm"
        autoFocus
      />

      <Animated.View entering={motion.downAt(80, 450)} style={styles.list}>
        {cowsError ? <ErrorBanner message={cowsError} onRetry={() => fetchCows()} /> : null}
        {cowsLoading && cows.length === 0 ? (
          <View style={{ marginTop: spacing.lg }}><SkeletonList count={5} /></View>
        ) : !cowsError && results.length === 0 ? (
          <EmptyState
            icon="search-outline"
            title="No cows found"
            message={query ? `Nothing matches “${query}”.` : 'No cows tracked yet.'}
          />
        ) : (
          results.map((cow) => (
            <ListRow
              key={cow.id}
              icon="analytics-outline"
              title={cow.earTag}
              subtitle={`${farmById(state, cow.farmId)?.name ?? 'Unknown farm'} · ${cow.breed} · Lact ${cow.lactationNumber}`}
              right={<StatusPill kind={cow.status} />}
              onPress={() => router.push({ pathname: '/cow/[id]', params: { id: cow.id } })}
            />
          ))
        )}
      </Animated.View>

      <Text variant="caption" color={colors.textMuted} style={styles.hint}>
        Tap a cow to open its full profile
      </Text>
    </Screen>
  );
}

const styles = StyleSheet.create({
  list: { marginTop: spacing.xl },
  hint: { textAlign: 'center', marginTop: spacing.md },
});
