import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import React from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import {
  Button,
  Card,
  HeroHeader,
  HeroStats,
  ListRow,
  Monogram,
  Screen,
  SectionHeader,
  Text,
  FocusedStatusBar,
} from '@/components';
import { colors, gradients, onDark, radius, spacing, status } from '@/theme';
import { pregnancyCounts, useAppStore } from '@/store/useAppStore';
import { useAuthStore } from '@/store/useAuthStore';

/**
 * Vet — the vet area is pregnancy diagnosis only. It does NOT schedule visits;
 * it surfaces which cows are approaching (Day 30) or overdue (Day 50) for a
 * pregnancy check so the vet can act on their own visit cadence.
 */
export function VetDashboard() {
  const router = useRouter();
  const store = useAppStore();
  const { farms, cows } = store;
  const { user } = useAuthStore();
  const { due, warning } = pregnancyCounts(store);

  return (
    <Screen padded={false} topInset={false}>
      <FocusedStatusBar style="light" />
      <HeroHeader gradient={gradients.vet}>
        <View style={styles.heroRow}>
          <Monogram name={user?.name ?? 'V'} size={64} bg={onDark.panelBorder} color={colors.cream.base} />
          <View style={styles.heroText}>
            <Text variant="caption" color={onDark.textSecondary}>
              Welcome back
            </Text>
            <Text variant="title" color={onDark.text}>
              {user?.name ?? 'Vet'}
            </Text>
            <View style={styles.clinicRow}>
              <Ionicons name="medkit" size={13} color={onDark.textSecondary} />
              <Text variant="caption" color={onDark.textSecondary}>
                Veterinarian · Pregnancy Diagnosis
              </Text>
            </View>
          </View>
        </View>

        <HeroStats
          tone="panel"
          style={styles.heroStats}
          items={[
            { value: farms.length, label: 'Assigned farms' },
            { value: due, label: 'Due for check' },
            { value: warning, label: 'Overdue' },
          ]}
        />
      </HeroHeader>

      <View style={styles.body}>
        {/* Overdue warning */}
        {warning > 0 ? (
          <View style={styles.warnBanner}>
            <Ionicons name="alert-circle" size={20} color={status.heat.fg} />
            <Text variant="body" color={colors.text} style={styles.warnText}>
              {warning} {warning === 1 ? 'cow is' : 'cows are'} overdue for a pregnancy check (50+ days). Prioritize
              on your next visit.
            </Text>
          </View>
        ) : null}

        {/* Pregnancy Report — the vet's primary worklist */}
        <SectionHeader title="Pregnancy Report" />
        <Pressable
          onPress={() => router.push({ pathname: '/report/[type]', params: { type: 'pregnancy-check' } })}
          accessibilityRole="button"
          accessibilityLabel="Open the pregnancy report"
        >
          <Card style={styles.reportCard}>
            <View style={styles.reportTop}>
              <View style={styles.reportIcon}>
                <Ionicons name="medkit" size={26} color={colors.primary} />
              </View>
              <View style={styles.flex1}>
                <Text variant="heading">Cows ready for diagnosis</Text>
                <Text variant="caption" color={colors.textSecondary}>
                  Confirm pregnancy on your next farm visit
                </Text>
              </View>
              <Ionicons name="chevron-forward" size={20} color={colors.textMuted} />
            </View>
            <View style={styles.reportStats}>
              <View style={styles.reportStat}>
                <Text variant="stat" color={colors.primary}>{due}</Text>
                <Text variant="caption" color={colors.textSecondary}>Due (Day 30+)</Text>
              </View>
              <View style={styles.reportDivider} />
              <View style={styles.reportStat}>
                <Text variant="stat" color={warning > 0 ? status.heat.fg : colors.textMuted}>{warning}</Text>
                <Text variant="caption" color={colors.textSecondary}>Overdue (Day 50+)</Text>
              </View>
            </View>
          </Card>
        </Pressable>

        <Text variant="caption" color={colors.textMuted} style={styles.hint}>
          Cows appear here 30 days after insemination. Entering a result removes them from the report.
        </Text>

        {/* Assigned farms — per-farm due counts */}
        <SectionHeader title="Your Farms" />
        {farms.map((f) => {
          const c = pregnancyCounts(store, f.id);
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
        })}

        <Button
          variant="secondary"
          label="View Herd Reports"
          icon="bar-chart-outline"
          onPress={() => router.push('/(tabs)/reports')}
          style={styles.reportsBtn}
        />
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  heroRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.lg },
  heroText: { flex: 1, gap: 2 },
  clinicRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.xs },
  heroStats: { marginTop: spacing.xxl },
  body: { paddingHorizontal: spacing.xl, marginTop: -spacing.xxxl },
  flex1: { flex: 1 },
  warnBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    backgroundColor: status.heat.bg,
    borderWidth: 1,
    borderColor: status.heat.fg,
    borderRadius: radius.md,
    padding: spacing.md,
    marginBottom: spacing.sm,
  },
  warnText: { flex: 1 },
  reportCard: { gap: spacing.lg },
  reportTop: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  reportIcon: {
    width: 48, height: 48, borderRadius: radius.pill,
    backgroundColor: colors.primarySoft, alignItems: 'center', justifyContent: 'center',
  },
  reportStats: {
    flexDirection: 'row',
    backgroundColor: colors.surfaceSoft,
    borderRadius: radius.md,
    paddingVertical: spacing.md,
  },
  reportStat: { flex: 1, alignItems: 'center', gap: 1 },
  reportDivider: { width: 1, backgroundColor: colors.border },
  hint: { marginTop: spacing.sm, marginBottom: spacing.sm },
  reportsBtn: { marginTop: spacing.lg },
});
