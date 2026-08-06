import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import React, { useEffect } from 'react';
import { StyleSheet, View } from 'react-native';
import {
  ActionCard,
  HeroHeader,
  HeroStats,
  ListRow,
  Screen,
  SectionHeader,
  Text,
  FocusedStatusBar,
} from '@/components';
import { colors, gradients, onDark, radius, shadows, spacing, status } from '@/theme';
import { summarize, useAppStore, worklistTotal } from '@/store/useAppStore';

type IconName = keyof typeof Ionicons.glyphMap;

/** Admin — system-wide command center in the charcoal identity. */
export function AdminDashboard() {
  const router = useRouter();
  const store = useAppStore();
  const { farms, cows, vets, kpis, fetchKpis } = store;
  const summary = summarize(cows);
  // Outstanding cow-work across every farm, from the shared work list.
  const activeTasks = worklistTotal(store);
  const today = new Date().toLocaleDateString('en-CA', {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
  });

  useEffect(() => { fetchKpis(); }, []);

  const heroStats = [
    { value: farms.length, label: 'Farms' },
    { value: summary.total, label: 'Cows' },
    { value: vets.length, label: 'Vets' },
    { value: activeTasks, label: 'Cows to do' },
  ];

  const mainActions: { label: string; caption: string; icon: IconName; onPress: () => void }[] = [
    { label: 'Farms CRM', caption: `${farms.length} farms`, icon: 'business', onPress: () => router.push('/(tabs)/farms') },
    { label: 'Reports', caption: 'System-wide', icon: 'bar-chart', onPress: () => router.push('/(tabs)/reports') },
    { label: 'Cow Search', caption: `${summary.total} cows`, icon: 'search', onPress: () => router.push('/cow-search') },
    { label: 'Veterinarians', caption: `${vets.length} partners`, icon: 'medkit', onPress: () => router.push('/vets') },
  ];

  const kpiRow = [
    { label: 'Preg Rate', value: kpis?.pregnancyRate != null ? `${kpis.pregnancyRate}%` : '—' },
    { label: 'Conception', value: kpis?.conceptionRate != null ? `${kpis.conceptionRate}%` : '—' },
    { label: 'Serv/Conc', value: kpis?.servicesPerConception != null ? String(kpis.servicesPerConception) : '—' },
    { label: 'Calvings 30d', value: kpis ? String(kpis.upcomingCalvings30d) : '—' },
  ];

  return (
    <Screen padded={false} topInset={false}>
      <FocusedStatusBar style="light" />
      <HeroHeader gradient={gradients.charcoal}>
        <View>
          <Text variant="caption" color={onDark.textSecondary}>
            {today}
          </Text>
          <Text variant="display" color={onDark.text}>
            System Overview
          </Text>
          <Text variant="caption" color={colors.red[300]}>
            Administrator
          </Text>
        </View>

        <HeroStats tone="panel" items={heroStats} style={styles.heroStats} />
      </HeroHeader>

      <View style={styles.body}>
        <View style={styles.grid}>
          {mainActions.map((a) => (
            <ActionCard
              key={a.label}
              icon={a.icon}
              label={a.label}
              sublabel={a.caption}
              onPress={a.onPress}
              style={styles.gridItem}
            />
          ))}
        </View>

        <SectionHeader title="Herd Across All Farms" />
        <View style={styles.summaryCard}>
          {(
            [
              { label: 'Pregnant', value: summary.pregnant, c: status.pregnant.fg },
              { label: 'Open', value: summary.open, c: status.open.fg },
              { label: 'Dry', value: summary.dry, c: status.dry.fg },
              { label: 'Fresh', value: summary.fresh, c: status.fresh.fg },
              { label: 'Cull', value: summary.cull, c: status.cull.fg },
              { label: 'In Heat', value: summary.heat, c: status.heat.fg },
            ] as const
          ).map((s) => (
            <View key={s.label} style={styles.summaryItem}>
              <View style={[styles.summaryDot, { backgroundColor: s.c }]} />
              <Text variant="statSmall">{s.value}</Text>
              <Text variant="caption" color={colors.textSecondary}>
                {s.label}
              </Text>
            </View>
          ))}
        </View>

        <SectionHeader title="Performance" />
        <View style={styles.summaryCard}>
          {kpiRow.map((k) => (
            <View key={k.label} style={styles.kpiItem}>
              <Text variant="statSmall" color={colors.primary}>
                {k.value}
              </Text>
              <Text variant="caption" color={colors.textSecondary} numberOfLines={1}>
                {k.label}
              </Text>
            </View>
          ))}
        </View>

        <SectionHeader title="Farms" actionLabel="View all" onAction={() => router.push('/(tabs)/farms')} />
        {farms.slice(0, 3).map((f) => (
            <ListRow
              key={f.id}
              icon="business"
              title={f.name}
              subtitle={`${f.owner} · ${f.city} · ${f.herdSize} cows`}
              onPress={() => router.push({ pathname: '/farm/[id]', params: { id: f.id } })}
            />
          ))}
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  heroStats: {
    marginTop: spacing.xxl,
  },
  body: {
    paddingHorizontal: spacing.xl,
    marginTop: -spacing.xxxl,
  },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.md },
  gridItem: { width: '47%', flexGrow: 1 },
  summaryCard: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.lg,
    ...shadows.card,
  },
  summaryItem: {
    width: '33.3%',
    alignItems: 'center',
    paddingVertical: spacing.md,
    gap: 1,
  },
  kpiItem: {
    width: '25%',
    alignItems: 'center',
    paddingVertical: spacing.md,
    gap: 1,
  },
  summaryDot: { width: 8, height: 8, borderRadius: 4, marginBottom: 2 },
});
