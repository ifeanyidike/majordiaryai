import { Ionicons } from '@expo/vector-icons';
import { useLocalSearchParams, useRouter } from 'expo-router';
import React, { useEffect, useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import Animated, { FadeInDown, FadeInUp } from 'react-native-reanimated';
import {
  Card,
  CowActionsSheet,
  EmptyState,
  Header,
  HeroHeader,
  HeroStats,
  InfoRow,
  Screen,
  SectionHeader,
  StatusPill,
  Text,
  FocusedStatusBar,
} from '@/components';
import { colors, gradients, onDark, radius, spacing } from '@/theme';
import { daysSince } from '@/lib/dates';
import { HistoryEvent } from '@/data/types';
import { cowById, farmById, useAppStore } from '@/store/useAppStore';

const fmt = (iso?: string) =>
  iso
    ? new Date(iso + 'T00:00:00').toLocaleDateString('en-CA', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
      })
    : '—';

const fmtShort = (iso?: string) =>
  iso
    ? new Date(iso + 'T00:00:00').toLocaleDateString('en-CA', { month: 'short', day: 'numeric' })
    : '—';

type HistoryTab = 'inseminations' | 'pregnancyChecks' | 'vaccinations' | 'treatments' | 'calvings';

const HISTORY_TABS: { key: HistoryTab; label: string; icon: keyof typeof Ionicons.glyphMap }[] = [
  { key: 'inseminations', label: 'AI', icon: 'flask' },
  { key: 'pregnancyChecks', label: 'Preg Checks', icon: 'medkit' },
  { key: 'vaccinations', label: 'Vaccines', icon: 'shield-checkmark' },
  { key: 'treatments', label: 'Treatments', icon: 'bandage' },
  { key: 'calvings', label: 'Calvings', icon: 'heart' },
];

export default function CowProfileScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const state = useAppStore();
  const { refreshCow, fetchCowHistory } = state;
  const cow = cowById(state, id);
  const [tab, setTab] = useState<HistoryTab>('inseminations');

  useEffect(() => {
    if (id) {
      refreshCow(id);
      fetchCowHistory(id);
    }
  }, [id]);

  if (!cow) {
    return (
      <Screen>
        <Header back title="Cow Profile" />
        <EmptyState title="Cow not found" message="She may not be loaded yet — go back and retry." />
      </Screen>
    );
  }

  const farm = farmById(state, cow.farmId);
  const events: HistoryEvent[] = cow.history[tab];

  const dsi = cow.lastInseminationDate ? daysSince(cow.lastInseminationDate) : null;
  const inHeatWindow = cow.status === 'inseminated' && dsi !== null && dsi >= 20 && dsi <= 25;

  return (
    <Screen padded={false} topInset={false}>
      <FocusedStatusBar style="light" />
      {/* Livestock record hero — charcoal */}
      <HeroHeader gradient={gradients.charcoal} back>
        <Animated.View entering={FadeInDown.duration(500)}>
          <View style={styles.heroTop}>
            <View style={styles.heroTitleCol}>
              <Text variant="display" color={onDark.text}>
                {cow.earTag}
              </Text>
              <Text variant="caption" color={onDark.textSecondary}>
                {[cow.breed, `Lactation ${cow.lactationNumber}`].filter(Boolean).join(' · ')}
              </Text>
              <Pressable
                onPress={() => router.push({ pathname: '/farm/[id]', params: { id: cow.farmId } })}
                style={styles.farmLink}
                accessibilityRole="button"
                accessibilityLabel={`Open farm ${farm?.name ?? ''}`}
              >
                <Ionicons name="business-outline" size={13} color={colors.red[300]} />
                <Text variant="caption" color={colors.red[300]}>
                  {farm?.name ?? 'Unknown farm'}
                </Text>
              </Pressable>
            </View>
            <View style={styles.pills}>
              <StatusPill kind={cow.status} />
              {inHeatWindow ? <StatusPill kind="heat" /> : null}
            </View>
          </View>
        </Animated.View>

        <Animated.View entering={FadeInDown.delay(120).duration(500)} style={{ marginTop: spacing.xxl }}>
          <HeroStats
            tone="panel"
            items={[
              { value: cow.daysInMilk, label: 'Days in Milk' },
              { value: cow.daysOpen, label: 'Days Open' },
              { value: fmtShort(cow.dueDate), label: 'Due Date' },
            ]}
          />
        </Animated.View>
      </HeroHeader>

      <View style={styles.body}>
        {/* Sick-cow banner — recheck reminder */}
        {cow.healthStatus === 'sick' ? (
          <View style={styles.healthBanner}>
            <Ionicons name="medkit" size={18} color={colors.status.heat.fg} />
            <Text variant="caption" color={colors.text} style={styles.healthText}>
              Flagged sick — recheck due {fmt(cow.recheckDueDate)}. She stays on the Open list until healthy.
            </Text>
          </View>
        ) : null}

        {/* Cow information */}
        <SectionHeader title="Cow Information" />
        <Animated.View entering={FadeInUp.delay(150).duration(500)}>
          <Card style={styles.infoCard}>
            <InfoRow label="Breed" value={cow.breed} />
            <InfoRow label="Date of Birth" value={fmt(cow.dateOfBirth)} />
            <InfoRow label="Lactation Number" value={cow.lactationNumber} />
            <InfoRow label="Current Program" value={cow.currentProgram} />
            <InfoRow label="Current Location" value={cow.currentLocation} />
            <InfoRow label="Notes" value={cow.notes} hideIfEmpty />
          </Card>
        </Animated.View>

        {/* Reproductive information */}
        <SectionHeader title="Reproductive Information" />
        <Animated.View entering={FadeInUp.delay(220).duration(500)}>
          <Card style={styles.infoCard}>
            <InfoRow label="Last Calving Date" value={fmt(cow.lastCalvingDate)} />
            <InfoRow label="Last Insemination" value={fmt(cow.lastInseminationDate)} />
            <InfoRow label="Bull Used" value={cow.bullUsed} />
            <InfoRow
              label="Pregnancy Status"
              value={cow.status === 'pregnant' || cow.status === 'dry' ? 'Pregnant' : 'Not Pregnant'}
            />
            <InfoRow label="Due Date" value={fmt(cow.dueDate)} />
            <InfoRow label="Dry Date" value={fmt(cow.dryDate)} />
          </Card>
        </Animated.View>

        {/* Cull record, when applicable */}
        {cow.status === 'cull' && (cow.cullDate || cow.cullReason) ? (
          <>
            <SectionHeader title="Cull Record" />
            <Card style={styles.infoCard}>
              <InfoRow label="Cull Date" value={fmt(cow.cullDate)} />
              <InfoRow label="Cull Reason" value={cow.cullReason} />
            </Card>
          </>
        ) : null}

        {/* Status Actions */}
        <CowActionsSheet
          cow={cow}
          onRefresh={() => {
            refreshCow(id);
            fetchCowHistory(id);
          }}
        />

        {/* History */}
        <SectionHeader title="History" />
        <Animated.View entering={FadeInUp.delay(290).duration(500)}>
          <View style={styles.tabsRow} accessibilityRole="tablist">
            {HISTORY_TABS.map((t) => {
              const active = t.key === tab;
              return (
                <Pressable
                  key={t.key}
                  onPress={() => setTab(t.key)}
                  style={[styles.tab, active && styles.tabActive]}
                  accessibilityRole="tab"
                  accessibilityState={{ selected: active }}
                  accessibilityLabel={t.label}
                >
                  <Ionicons
                    name={t.icon}
                    size={15}
                    color={active ? colors.textOnPrimary : colors.textSecondary}
                  />
                  <Text variant="caption" color={active ? colors.textOnPrimary : colors.textSecondary}>
                    {t.label}
                  </Text>
                </Pressable>
              );
            })}
          </View>

          <Card style={styles.infoCard}>
            {events.length === 0 ? (
              <Text variant="body" color={colors.textMuted}>
                No records yet.
              </Text>
            ) : (
              events.map((e, i) => (
                <View key={e.id} style={[styles.eventRow, i > 0 && styles.eventDivider]}>
                  <View style={styles.eventDot} />
                  <View style={styles.eventText}>
                    <Text variant="bodyBold">{fmt(e.date)}</Text>
                    <Text variant="caption" color={colors.textSecondary}>
                      {e.detail}
                    </Text>
                  </View>
                </View>
              ))
            )}
          </Card>
        </Animated.View>
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  heroTop: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    gap: spacing.md,
  },
  heroTitleCol: { gap: 3, flex: 1 },
  farmLink: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    marginTop: spacing.xs,
    minHeight: 32,
    paddingVertical: spacing.xs,
    alignSelf: 'flex-start',
  },
  pills: { gap: spacing.xs, alignItems: 'flex-end' },
  body: {
    paddingHorizontal: spacing.xl,
    marginTop: -spacing.lg,
  },
  infoCard: { gap: 0, paddingVertical: spacing.sm },
  healthBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    backgroundColor: colors.status.heat.bg,
    borderWidth: 1,
    borderColor: colors.status.heat.fg,
    borderRadius: radius.md,
    padding: spacing.md,
    marginTop: spacing.lg,
  },
  healthText: { flex: 1 },
  tabsRow: {
    flexDirection: 'row',
    gap: spacing.xs + 2,
    marginBottom: spacing.md,
    flexWrap: 'wrap',
  },
  tab: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    minHeight: 44,
    paddingHorizontal: spacing.md,
    borderRadius: radius.pill,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
  },
  tabActive: {
    backgroundColor: colors.charcoal[900],
    borderColor: colors.charcoal[900],
  },
  eventRow: {
    flexDirection: 'row',
    gap: spacing.md,
    paddingVertical: spacing.md - 2,
    alignItems: 'flex-start',
  },
  eventDivider: {
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.border,
  },
  eventDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: colors.primary,
    marginTop: 6,
  },
  eventText: { flex: 1, gap: 1 },
});
