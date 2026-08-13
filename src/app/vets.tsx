import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import React, { useEffect } from 'react';
import { ActivityIndicator, Pressable, StyleSheet } from 'react-native';
import Animated, { FadeInDown } from 'react-native-reanimated';
import { EmptyState, ErrorBanner, Header, ListRow, Screen } from '@/components';
import { colors, spacing } from '@/theme';
import { useAppStore } from '@/store/useAppStore';
import { useAuthStore } from '@/store/useAuthStore';

export default function VetsScreen() {
  const router = useRouter();
  const { vets, vetsLoading, vetsError, fetchVets } = useAppStore();
  const role = useAuthStore((s) => s.user?.role);

  useEffect(() => { fetchVets(); }, []);

  return (
    <Screen refreshing={vetsLoading && vets.length > 0} onRefresh={fetchVets}>
      <Header
        back
        title="Veterinarians"
        subtitle={`${vets.length} clinic partners`}
        right={
          role === 'admin' ? (
            <Pressable
              onPress={() => router.push('/vet/edit')}
              style={styles.addBtn}
              accessibilityRole="button"
              accessibilityLabel="Add veterinarian"
            >
              <Ionicons name="add" size={20} color={colors.textOnPrimary} />
            </Pressable>
          ) : undefined
        }
      />
      {vetsError ? <ErrorBanner message={vetsError} onRetry={fetchVets} /> : null}
      {vetsLoading && vets.length === 0 ? (
        <ActivityIndicator color={colors.primary} style={{ marginTop: spacing.xxl }} />
      ) : !vetsError && vets.length === 0 ? (
        <EmptyState
          icon="medkit-outline"
          title="No vets yet"
          message={role === 'admin'
            ? 'Add a veterinarian with the + button above.'
            : 'Vets are added by an administrator.'}
        />
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

const styles = StyleSheet.create({
  addBtn: {
    width: 40, height: 40, borderRadius: 20,
    backgroundColor: colors.primary,
    alignItems: 'center', justifyContent: 'center',
  },
});
