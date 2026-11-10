import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import React, { useEffect } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import Animated from 'react-native-reanimated';
import { EmptyState, ErrorBanner, Header, ListRow, Screen, SkeletonList, Text } from '@/components';
import { colors, spacing, useMotion } from '@/theme';
import { allTechnicians, farmsOnRoute, useAppStore } from '@/store/useAppStore';
import { useAuthStore } from '@/store/useAuthStore';

/**
 * Admin, Technicians (feature notes, Nov 10): every technician; tap one for
 * their profile, which the admin can edit; + adds a new one.
 */
export default function TechniciansScreen() {
  const motion = useMotion();
  const router = useRouter();
  const state = useAppStore();
  const { staffLoading, staffError, fetchStaff, fetchFarms } = state;
  const role = useAuthStore((s) => s.user?.role);
  const technicians = allTechnicians(state);

  const refresh = () => { fetchStaff(); fetchFarms(); };
  useEffect(refresh, []);

  if (role !== 'admin') {
    return (
      <Screen>
        <Header back title="Technicians" />
        <EmptyState icon="lock-closed-outline" title="Admins only"
                    message="Technicians are managed by an administrator." />
      </Screen>
    );
  }

  return (
    <Screen refreshing={staffLoading && technicians.length > 0} onRefresh={refresh}>
      <Header
        back
        title="Technicians"
        subtitle={`${technicians.length} ${technicians.length === 1 ? 'technician' : 'technicians'}`}
        right={
          <Pressable
            onPress={() => router.push('/technician/edit')}
            style={styles.addBtn}
            accessibilityRole="button"
            accessibilityLabel="Add technician"
          >
            <Ionicons name="add" size={20} color={colors.textOnPrimary} />
          </Pressable>
        }
      />
      {staffError ? <ErrorBanner message={staffError} onRetry={refresh} /> : null}
      {staffLoading && technicians.length === 0 ? (
        <View style={{ marginTop: spacing.lg }}><SkeletonList count={4} /></View>
      ) : !staffError && technicians.length === 0 ? (
        <EmptyState icon="person-add-outline" title="No technicians yet"
                    message="Add one with the + button above." />
      ) : (
        technicians.map((t, i) => {
          const farms = farmsOnRoute(state, t.id).length;
          return (
            <Animated.View key={t.id} entering={motion.down(i)}>
              <ListRow
                icon="person"
                iconColor={colors.primary}
                iconBg={colors.primarySoft}
                title={t.name}
                subtitle={[`${farms} ${farms === 1 ? 'farm' : 'farms'}`, t.region, t.phone]
                  .filter(Boolean).join(' · ')}
                badge={t.isActive ? undefined : (
                  <Text variant="caption" color={colors.warning}>Waiting for approval under People</Text>
                )}
                onPress={() => router.push({ pathname: '/technician/[id]', params: { id: t.id } })}
              />
            </Animated.View>
          );
        })
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
