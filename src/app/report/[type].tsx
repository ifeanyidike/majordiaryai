import { useLocalSearchParams, useRouter } from 'expo-router';
import React, { useEffect } from 'react';
import { ActivityIndicator, FlatList, RefreshControl } from 'react-native';
import Animated, { FadeInDown } from 'react-native-reanimated';
import { EmptyState, ErrorBanner, Header, ListRow, Screen, StatusPill } from '@/components';
import { colors, spacing } from '@/theme';
import { reportByType } from '@/data/reports';
import { farmById, useAppStore, visibleCows } from '@/store/useAppStore';

export default function ReportDetailScreen() {
  const { type } = useLocalSearchParams<{ type: string }>();
  const router = useRouter();
  const state = useAppStore();
  const { cowsLoading, cowsError, fetchCows, fetchTasks, tasks } = state;

  const def = reportByType(type ?? '');

  useEffect(() => {
    // Task-driven reports (needling, timed breeding) need today's task list too.
    if (def && ['needling', 'timed-breeding'].includes(def.type)) fetchTasks();
  }, [def?.type]);

  if (!def) {
    return (
      <Screen>
        <Header back title="Report" />
        <EmptyState
          icon="help-circle-outline"
          title="Report not found"
          message="This report type doesn't exist. Head back and pick one from the Reports tab."
        />
      </Screen>
    );
  }

  const cows = visibleCows(state);
  const list = def.filter(cows, tasks);
  const loading = cowsLoading && cows.length === 0;

  return (
    <Screen scroll={false} padded={false}>
      <FlatList
        data={list}
        keyExtractor={(cow) => cow.id}
        contentContainerStyle={{ paddingHorizontal: spacing.xl, paddingBottom: spacing.huge }}
        refreshControl={
          <RefreshControl
            // Pull-to-refresh spinner only when there's already content on screen;
            // the first-load/retry state uses the single inline spinner below.
            refreshing={cowsLoading && cows.length > 0}
            onRefresh={() => fetchCows()}
            tintColor={colors.primary}
            colors={[colors.primary]}
          />
        }
        ListHeaderComponent={
          <>
            <Header back title={def.title} subtitle={`${list.length} ${list.length === 1 ? 'cow' : 'cows'}`} />
            {cowsError ? <ErrorBanner message={cowsError} onRetry={() => fetchCows()} /> : null}
            {loading ? (
              <ActivityIndicator color={colors.primary} style={{ marginTop: spacing.xxl }} />
            ) : null}
          </>
        }
        ListEmptyComponent={
          loading || cowsError ? null : (
            <EmptyState title="No cows in this report" message="Nothing due here right now." />
          )
        }
        renderItem={({ item: cow, index }) => {
          const farm = farmById(state, cow.farmId);
          const pill = def.type === 'heat' ? 'heat' : cow.status;
          return (
            <Animated.View entering={FadeInDown.delay(Math.min(index, 8) * 50).duration(400)}>
              <ListRow
                icon="analytics-outline"
                title={cow.earTag}
                subtitle={def.detail(cow, farm?.name ?? 'Unknown farm')}
                right={<StatusPill kind={pill} />}
                onPress={() => router.push({ pathname: '/cow/[id]', params: { id: cow.id } })}
              />
            </Animated.View>
          );
        }}
      />
    </Screen>
  );
}
