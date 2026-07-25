import { useLocalSearchParams, useRouter } from 'expo-router';
import React, { useEffect } from 'react';
import { ActivityIndicator, FlatList, RefreshControl } from 'react-native';
import Animated, { FadeInDown } from 'react-native-reanimated';
import { EmptyState, ErrorBanner, Header, ListRow, Screen, StatusPill } from '@/components';
import { colors, spacing } from '@/theme';
import { cowsByFarm, farmById, useAppStore } from '@/store/useAppStore';

export default function HerdScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const state = useAppStore();
  const farm = farmById(state, id);
  const herd = cowsByFarm(state, id);
  const { fetchCows, cowsLoading, cowsError } = state;

  useEffect(() => {
    fetchCows(id);
  }, [id]);

  const subtitle = farm
    ? `${farm.name} · ${herd.length} tracked cows`
    : `${herd.length} tracked cows`;
  const loading = cowsLoading && herd.length === 0;

  return (
    <Screen scroll={false} padded={false}>
      <FlatList
        data={herd}
        keyExtractor={(cow) => cow.id}
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
            <Header back title="Herd" subtitle={subtitle} />
            {cowsError ? <ErrorBanner message={cowsError} onRetry={() => fetchCows(id)} /> : null}
            {loading ? (
              <ActivityIndicator color={colors.primary} style={{ marginTop: spacing.xxl }} />
            ) : null}
          </>
        }
        ListEmptyComponent={
          loading || cowsError ? null : <EmptyState title="No cows tracked yet" />
        }
        renderItem={({ item: cow, index }) => (
          <Animated.View entering={FadeInDown.delay(Math.min(index, 8) * 50).duration(400)}>
            <ListRow
              icon="analytics-outline"
              title={cow.earTag}
              subtitle={`${cow.breed} · Lact ${cow.lactationNumber} · ${cow.daysInMilk} DIM`}
              right={<StatusPill kind={cow.status} />}
              onPress={() => router.push({ pathname: '/cow/[id]', params: { id: cow.id } })}
            />
          </Animated.View>
        )}
      />
    </Screen>
  );
}
