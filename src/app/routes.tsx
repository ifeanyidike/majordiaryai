import { useRouter } from 'expo-router';
import React, { useEffect } from 'react';
import { View } from 'react-native';
import Animated from 'react-native-reanimated';
import { EmptyState, ErrorBanner, Header, ListRow, Screen, SkeletonList, Text } from '@/components';
import { colors, spacing, useMotion } from '@/theme';
import { allTechnicians, farmsOnRoute, useAppStore } from '@/store/useAppStore';
import { useAuthStore } from '@/store/useAuthStore';

/**
 * Admin, Routes (feature notes, Nov 10): all technicians, then one technician's
 * farms, where checked farms are reassigned.
 */
export default function RoutesScreen() {
  const motion = useMotion();
  const router = useRouter();
  const state = useAppStore();
  const { staffLoading, staffError, fetchStaff, fetchFarms, farms } = state;
  const role = useAuthStore((s) => s.user?.role);
  const technicians = allTechnicians(state);
  const unassigned = farms.filter((f) => !f.assignedTechnicianId).length;

  const refresh = () => { fetchStaff(); fetchFarms(); };
  useEffect(refresh, []);

  if (role !== 'admin') {
    return (
      <Screen>
        <Header back title="Routes" />
        <EmptyState icon="lock-closed-outline" title="Admins only"
                    message="Routes are managed by an administrator." />
      </Screen>
    );
  }

  return (
    <Screen refreshing={staffLoading && technicians.length > 0} onRefresh={refresh}>
      <Header back title="Routes" subtitle="Pick a technician to move their farms" />
      {staffError ? <ErrorBanner message={staffError} onRetry={refresh} /> : null}
      {staffLoading && technicians.length === 0 ? (
        <View style={{ marginTop: spacing.lg }}><SkeletonList count={4} /></View>
      ) : !staffError && technicians.length === 0 ? (
        <EmptyState icon="git-network-outline" title="No technicians yet"
                    message="Add technicians under Technicians first." />
      ) : (
        technicians.map((t, i) => {
          const n = farmsOnRoute(state, t.id).length;
          return (
            <Animated.View key={t.id} entering={motion.down(i)}>
              <ListRow
                icon="git-network"
                iconColor={colors.primary}
                iconBg={colors.primarySoft}
                title={t.name}
                subtitle={`${n} ${n === 1 ? 'farm' : 'farms'}${t.isActive ? '' : ' · waiting for approval'}`}
                onPress={() => router.push({ pathname: '/route/[id]', params: { id: t.id } })}
              />
            </Animated.View>
          );
        })
      )}
      {unassigned > 0 ? (
        <Text variant="caption" color={colors.textMuted} style={{ marginTop: spacing.md }}>
          {unassigned} {unassigned === 1 ? 'farm has' : 'farms have'} no technician. Give them one
          on the farm's Edit page.
        </Text>
      ) : null}
    </Screen>
  );
}
