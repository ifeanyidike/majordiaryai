import { Ionicons } from '@expo/vector-icons';
import { useLocalSearchParams, useRouter } from 'expo-router';
import React, { useEffect } from 'react';
import { StyleSheet, View } from 'react-native';
import Animated from 'react-native-reanimated';
import {
  Button,
  Card,
  EmptyState,
  Header,
  HeroHeader,
  InfoRow,
  ListRow,
  Monogram,
  Screen,
  SectionHeader,
  StatCard,
  Text,
  FocusedStatusBar,
} from '@/components';
import { charcoal, colors, gradients, onDark, spacing, status, useMotion } from '@/theme';
import { dial } from '@/lib/contact';
import { cowsByFarm, pregnancyCounts, useAppStore, vetById } from '@/store/useAppStore';
import { useAuthStore } from '@/store/useAuthStore';

export default function VetProfileScreen() {
  const motion = useMotion();
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const state = useAppStore();
  const role = useAuthStore((s) => s.user?.role);

  useEffect(() => {
    // Same reason as the farm profile: unloaded work list would show 0 due.
    state.ensureWorklist();
  }, []);
  const vet = vetById(state, id);

  if (!vet) {
    return (
      <Screen>
        <Header back title="Vet Profile" />
        <EmptyState title="Vet not found" />
      </Screen>
    );
  }

  const assignedFarms = state.farms.filter((f) => vet.farmIds.includes(f.id));
  const herd = vet.farmIds.flatMap((fid) => cowsByFarm(state, fid));
  // THIS vet's farms only — an unscoped count would include every farm the
  // viewer can see, not the ones this vet covers.
  const { due, warning } = vet.farmIds.reduce(
    (acc, fid) => {
      const c = pregnancyCounts(state, fid);
      return { due: acc.due + c.due, warning: acc.warning + c.warning };
    },
    { due: 0, warning: 0 },
  );

  return (
    <Screen padded={false} topInset={false}>
      <FocusedStatusBar style="light" />
      {/* Deep-red clinical identity hero — brand palette only */}
      <HeroHeader gradient={gradients.vet} back>
        <Animated.View entering={motion.downAt(0, 500)} style={styles.heroRow}>
          <Monogram name={vet.name.replace('Dr. ', '')} size={64} bg={onDark.panelBorder} color={colors.cream.base} />
          <View style={styles.heroText}>
            <Text variant="title" color={onDark.text}>
              {vet.name}
            </Text>
            <View style={styles.clinicRow}>
              <Ionicons name="medkit" size={13} color={onDark.textSecondary} />
              <Text variant="caption" color={onDark.textSecondary}>
                {vet.clinic}
              </Text>
            </View>
          </View>
        </Animated.View>

        <Animated.View entering={motion.downAt(120, 500)} style={styles.heroActions}>
          <Button
            label="Contact Vet"
            icon="call"
            variant="onDark"
            onPress={() => dial(vet.phone)}
            style={styles.heroBtn}
            compact
          />
          <Button
            label="Pregnancy Report"
            icon="medkit"
            variant="onDark"
            onPress={() => router.push({ pathname: '/report/[type]', params: { type: 'pregnancy-check' } })}
            style={styles.heroBtn}
            compact
          />
        </Animated.View>
      </HeroHeader>

      <View style={styles.body}>
        {/* Summary — overlapping stats (pregnancy-diagnosis focused) */}
        <Animated.View entering={motion.upAt(150, 500)}>
          <View style={styles.statRow}>
            <StatCard value={assignedFarms.length} label="Active Farms" accent={colors.primary} />
            <StatCard value={herd.length} label="Cows Under Care" accent={charcoal[600]} />
          </View>
          <View style={styles.statRow}>
            <StatCard value={due} label="Due for Check" accent={colors.primary} />
            <StatCard value={warning} label="Overdue" accent={warning > 0 ? status.heat.fg : colors.textMuted} />
          </View>
        </Animated.View>

        {/* Vet information */}
        <SectionHeader title="Vet Information" />
        <Animated.View entering={motion.upAt(220, 500)}>
          <Card style={styles.infoCard}>
            <InfoRow label="Phone" value={vet.phone} />
            <InfoRow label="Email" value={vet.email} />
            <InfoRow label="Notes" value={vet.notes} hideIfEmpty />
          </Card>
        </Animated.View>

        {/* Assigned farms with per-farm due counts */}
        <SectionHeader title="Assigned Farms" />
        <Animated.View entering={motion.upAt(290, 500)}>
          {assignedFarms.length === 0 ? (
            <Card style={styles.infoCard}>
              <Text variant="body" color={colors.textMuted}>
                No farms assigned yet.
              </Text>
            </Card>
          ) : (
            assignedFarms.map((f) => {
              const c = pregnancyCounts(state, f.id);
              return (
                <ListRow
                  key={f.id}
                  icon="business"
                  iconColor={colors.primary}
                  iconBg={colors.primarySoft}
                  title={f.name}
                  subtitle={`${f.city} · ${c.due} due${c.warning > 0 ? ` · ${c.warning} overdue` : ''}`}
                  onPress={() => router.push({ pathname: '/farm/[id]', params: { id: f.id } })}
                />
              );
            })
          )}
        </Animated.View>

        <Animated.View entering={motion.upAt(360, 500)} style={styles.footerRow}>
          <Button
            compact
            variant="secondary"
            label="View Reports"
            icon="bar-chart-outline"
            onPress={() => router.push('/(tabs)/reports')}
            style={styles.footerBtn}
          />
          {role === 'admin' && (
            <Button
              compact
              variant="secondary"
              label="Edit Vet"
              icon="create-outline"
              onPress={() => router.push({ pathname: '/vet/edit', params: { id: vet.id } })}
              style={styles.footerBtn}
            />
          )}
        </Animated.View>
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  heroRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.lg },
  heroText: { flex: 1, gap: spacing.hairline },
  clinicRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.xs },
  heroActions: {
    flexDirection: 'row',
    gap: spacing.md,
    marginTop: spacing.xxl,
  },
  heroBtn: { flex: 1 },
  body: {
    paddingHorizontal: spacing.xl,
    marginTop: -spacing.xxxl,
  },
  statRow: { flexDirection: 'row', gap: spacing.md, marginBottom: spacing.md },
  infoCard: { paddingVertical: spacing.sm },
  footerRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.sm,
    marginTop: spacing.sm,
  },
  footerBtn: { flexGrow: 1, flexBasis: '45%', minWidth: 140 },
});
