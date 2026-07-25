import { useRouter } from 'expo-router';
import React, { useEffect } from 'react';
import { ActivityIndicator } from 'react-native';
import Animated, { FadeInDown } from 'react-native-reanimated';
import { EmptyState, ErrorBanner, Header, ListRow, Screen } from '@/components';
import { colors, spacing } from '@/theme';
import { useAppStore } from '@/store/useAppStore';

export default function VetsScreen() {
  const router = useRouter();
  const { vets, vetsLoading, vetsError, fetchVets } = useAppStore();

  useEffect(() => { fetchVets(); }, []);

  return (
    <Screen refreshing={vetsLoading && vets.length > 0} onRefresh={fetchVets}>
      <Header back title="Veterinarians" subtitle={`${vets.length} clinic partners`} />
      {vetsError ? <ErrorBanner message={vetsError} onRetry={fetchVets} /> : null}
      {vetsLoading && vets.length === 0 ? (
        <ActivityIndicator color={colors.primary} style={{ marginTop: spacing.xxl }} />
      ) : !vetsError && vets.length === 0 ? (
        <EmptyState icon="medkit-outline" title="No vets assigned" message="Vets are added by an administrator." />
      ) : (
        vets.map((v, i) => (
          <Animated.View key={v.id} entering={FadeInDown.delay(Math.min(i, 8) * 70).duration(450)}>
            <ListRow
              icon="medkit"
              iconColor={colors.primary}
              iconBg={colors.primarySoft}
              title={v.name}
              subtitle={`${v.clinic} · ${v.farmIds.length} ${v.farmIds.length === 1 ? 'farm' : 'farms'}`}
              onPress={() => router.push({ pathname: '/vet/[id]', params: { id: v.id } })}
            />
          </Animated.View>
        ))
      )}
    </Screen>
  );
}
