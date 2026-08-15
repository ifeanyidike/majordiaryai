import { Ionicons } from '@expo/vector-icons';
import { useLocalSearchParams, useRouter } from 'expo-router';
import React, { useEffect, useState } from 'react';
import { StyleSheet, View } from 'react-native';
import Animated from 'react-native-reanimated';
import {
  Button,
  Card,
  EmptyState,
  Header,
  HeroHeader,
  IconCircle,
  InfoRow,
  InputModal,
  Monogram,
  PressableScale,
  Screen,
  SectionHeader,
  StatCard,
  Text,
  useToast,
  FocusedStatusBar,
} from '@/components';
import { colors, gradients, onDark, radius, spacing, status, useMotion } from '@/theme';
import { dial, emailTo } from '@/lib/contact';
import { formatAddress, openDirections } from '@/lib/maps';
import {
  cowsByFarm, farmById, farmUpcomingActivities, pregnancyCounts, summarize,
  useAppStore, vetForFarm,
} from '@/store/useAppStore';
import { useAuthStore } from '@/store/useAuthStore';

const ACTIVITY_ICONS: Record<string, keyof typeof Ionicons.glyphMap> = {
  medkit: 'medkit',
  'shield-checkmark': 'shield-checkmark',
  heart: 'heart',
  walk: 'walk',
  dry: 'water-outline',
  calving: 'egg-outline',
};

export default function FarmProfileScreen() {
  const motion = useMotion();
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const toast = useToast();
  const state = useAppStore();
  const farm = farmById(state, id);
  const role = useAuthStore((s) => s.user?.role);
  const [noteOpen, setNoteOpen] = useState(false);

  useEffect(() => {
    state.fetchCows(id);
    // Pregnancy counts come from the work list; on a deep link it may not be
    // loaded yet, and an unloaded list reads as "0 due" rather than "unknown".
    state.ensureWorklist();
  }, [id]);

  if (!farm) {
    return (
      <Screen>
        <Header back title="Farm Profile" />
        <EmptyState title="Farm not found" />
      </Screen>
    );
  }

  const herd = cowsByFarm(state, farm.id);
  const summary = summarize(herd);
  // Coverage lives on the vet, not on the farm — farm.vetId is always ''.
  const vet = vetForFarm(state, farm.id);
  const upcoming = farmUpcomingActivities(state.cows, farm.id);
  const preg = pregnancyCounts(state, id);

  const call = () => dial(farm.phone);
  const email = () => emailTo(farm.email);
  const directions = () =>
    openDirections(formatAddress(farm.address, farm.city, farm.province));

  const canManage = role === 'admin' || role === 'technician';
  const canNote = canManage || role === 'farm';

  const contactChips: { icon: keyof typeof Ionicons.glyphMap; label: string; onPress: () => void }[] = [
    { icon: 'call', label: 'Call', onPress: call },
    { icon: 'mail', label: 'Email', onPress: email },
    { icon: 'navigate', label: 'Directions', onPress: directions },
    // Note sat alongside Call/Email/Directions and was offered to every role,
    // including vets, whose write the API refuses. A farm manager CAN note
    // their own farm — that is how they tell the technician something — so the
    // gate is "may record on this farm", not "may manage it".
    ...(canNote
      ? [{ icon: 'create' as const, label: 'Note', onPress: () => setNoteOpen(true) }]
      : []),
  ];
  const manageActions: {
    label: string; icon: keyof typeof Ionicons.glyphMap; onPress: () => void;
  }[] = [
    ...(canManage ? [
      {
        label: 'Visits',
        icon: 'calendar-outline' as const,
        onPress: () => router.push({ pathname: '/farm/visits' as const, params: { id: farm.id } }),
      },
      {
        label: 'Bulls',
        icon: 'flask-outline' as const,
        onPress: () => router.push({ pathname: '/farm/bulls' as const, params: { id: farm.id } }),
      },
    ] : []),
    ...(role === 'admin' ? [{
      label: 'Edit',
      icon: 'create-outline' as const,
      onPress: () => router.push({ pathname: '/farm/edit' as const, params: { id: farm.id } }),
    }] : []),
  ];

  const addressLine = [farm.address, farm.city, farm.province, farm.postalCode]
    .filter(Boolean)
    .join(', ');

  return (
    <Screen padded={false} topInset={false}>
      <FocusedStatusBar style="light" />
      {/* Farm identity hero */}
      <HeroHeader gradient={gradients.primary} back>
        <Animated.View entering={motion.downAt(0, 500)} style={styles.heroRow}>
          <Monogram name={farm.name} size={64} bg={onDark.panelBorder} color={colors.cream.base} />
          <View style={styles.heroText}>
            <Text variant="title" color={onDark.text}>
              {farm.name}
            </Text>
            <Text variant="caption" color={onDark.textSecondary}>
              {farm.owner} · {farm.city}, {farm.province}
            </Text>
          </View>
        </Animated.View>

        <Animated.View entering={motion.downAt(120, 500)} style={styles.chipsRow}>
          {contactChips.map((c) => (
            <PressableScale
              key={c.label}
              onPress={c.onPress}
              style={styles.chip}
              accessibilityRole="button"
              accessibilityLabel={`${c.label} ${farm.name}`}
            >
              <Ionicons name={c.icon} size={18} color={onDark.text} />
              <Text variant="label" color={onDark.text} style={styles.chipLabel}>
                {c.label}
              </Text>
            </PressableScale>
          ))}
        </Animated.View>
      </HeroHeader>

      <View style={styles.body}>
        {/* Summary stats overlapping hero */}
        <Animated.View entering={motion.upAt(150, 500)}>
          <View style={styles.statRow}>
            <StatCard value={summary.total} label="Tracked Cows" />
            <StatCard value={summary.pregnant} label="Pregnant" accent={status.pregnant.fg} />
            <StatCard value={summary.open} label="Open" accent={status.open.fg} />
          </View>
          <View style={styles.statRow}>
            <StatCard value={summary.dry} label="Dry" accent={status.dry.fg} />
            <StatCard value={summary.fresh} label="Fresh" accent={status.fresh.fg} />
            <StatCard value={summary.cull} label="Cull" accent={status.cull.fg} />
          </View>
        </Animated.View>

        {/* "View Herd" is the job; the rest are management. Four equal buttons
            in one row squeezed every label — primary first, then a wrapping
            row of compact actions that stays readable at any role. */}
        <Animated.View entering={motion.upAt(220, 500)}>
          <Button
            label="View Herd"
            icon="list"
            onPress={() => router.push({ pathname: '/farm/herd', params: { id: farm.id } })}
            style={styles.primaryAction}
          />
          {manageActions.length > 0 && (
            <View style={styles.manageRow}>
              {manageActions.map((a) => (
                <Button
                  key={a.label}
                  compact
                  variant="secondary"
                  label={a.label}
                  icon={a.icon}
                  onPress={a.onPress}
                  style={styles.manageBtn}
                />
              ))}
            </View>
          )}
        </Animated.View>

        {/* Farm information */}
        <SectionHeader title="Farm Information" />
        <Animated.View entering={motion.upAt(280, 500)}>
          <Card style={styles.infoCard}>
            <InfoRow label="Address" value={addressLine} />
            <InfoRow label="Phone" value={farm.phone} />
            <InfoRow label="Email" value={farm.email} />
            <InfoRow label="Tracked Cows" value={summary.total} />
            <InfoRow label="Milking" value={summary.milking} />
            <InfoRow label="Not Milking (dry)" value={summary.dry} />
            <InfoRow label="Active (non-cull)" value={summary.total - summary.cull} />
            <InfoRow label="Reported Herd Size" value={farm.reportedHerdSize} hideIfEmpty />
            <InfoRow label="Technician" value={farm.assignedTechnician} hideIfEmpty />
          </Card>
        </Animated.View>

        {/* Vet link */}
        {vet ? (
          <Animated.View entering={motion.upAt(340, 500)}>
            <PressableScale
              style={styles.vetRow}
              onPress={() => router.push({ pathname: '/vet/[id]', params: { id: vet.id } })}
              accessibilityRole="button"
              accessibilityLabel={`Open veterinarian ${vet.name}`}
            >
              <IconCircle name="medkit" size={40} color={colors.primary} bg={colors.primarySoft} />
              <View style={styles.vetText}>
                <Text variant="bodyBold">{vet.name}</Text>
                <Text variant="caption" color={colors.textSecondary}>
                  Herd Veterinarian · {vet.clinic}
                </Text>
              </View>
              <Ionicons name="chevron-forward" size={18} color={colors.textMuted} />
            </PressableScale>
          </Animated.View>
        ) : null}

        {/* Pregnancy checks — cows due for vet diagnosis (Day 30+, warning at Day 50+) */}
        <SectionHeader title="Pregnancy Checks" />
        <Animated.View entering={motion.upAt(370, 500)}>
          <PressableScale
            scaleTo={0.98}
            onPress={() => router.push({ pathname: '/report/[type]', params: { type: 'pregnancy-check' } })}
            accessibilityRole="button"
            accessibilityLabel="Open the pregnancy report"
          >
            <Card style={styles.pregCard}>
              <IconCircle name="medkit" size={40} color={colors.primary} bg={colors.primarySoft} />
              <View style={styles.flex1}>
                <Text variant="bodyBold">
                  {preg.due === 0
                    ? 'No cows awaiting a check'
                    : `${preg.due} ${preg.due === 1 ? 'cow' : 'cows'} due for pregnancy check`}
                </Text>
                <Text variant="caption" color={preg.warning > 0 ? status.heat.fg : colors.textSecondary}>
                  {preg.warning > 0
                    ? `${preg.warning} overdue (50+ days) — consider requesting a vet visit`
                    : 'Cows appear 30 days after insemination'}
                </Text>
              </View>
              <Ionicons name="chevron-forward" size={18} color={colors.textMuted} />
            </Card>
          </PressableScale>
        </Animated.View>

        {/* Upcoming activities */}
        <SectionHeader title="Upcoming Activities" />
        <Animated.View entering={motion.upAt(400, 500)}>
          <Card style={styles.activityCard}>
            {upcoming.length === 0 ? (
              <Text variant="body" color={colors.textMuted}>
                Nothing scheduled — dry-offs and calvings appear here as they come due.
              </Text>
            ) : (
              upcoming.map((a, i) => (
                <View key={a.id} style={[styles.activityRow, i > 0 && styles.activityDivider]}>
                  <IconCircle name={ACTIVITY_ICONS[a.icon] ?? 'calendar'} size={38} />
                  <View style={styles.activityText}>
                    <Text variant="bodyBold">{a.label}</Text>
                    <Text variant="caption" color={colors.textSecondary}>
                      {a.date}
                    </Text>
                  </View>
                </View>
              ))
            )}
          </Card>
        </Animated.View>

        {/* Notes */}
        {farm.notes.length > 0 && (
          <>
            <SectionHeader title="Notes" />
            <Card style={styles.notesCard}>
              {farm.notes.map((n, i) => (
                <View key={i} style={styles.noteRow}>
                  <Ionicons name="document-text-outline" size={15} color={colors.textSecondary} />
                  <Text variant="body" color={colors.textSecondary} style={styles.noteText}>
                    {n}
                  </Text>
                </View>
              ))}
            </Card>
          </>
        )}
      </View>

      {/* Add note modal */}
      <InputModal
        visible={noteOpen}
        title="Add Farm Note"
        placeholder="Write your note…"
        submitLabel="Save Note"
        onClose={() => setNoteOpen(false)}
        // Awaited and caught: this used to fire and forget, so the success
        // toast showed before the request had happened and a 403 or a dropped
        // connection lost the note with the user told it was saved.
        onSubmit={async (text) => {
          setNoteOpen(false);
          try {
            await state.addFarmNote(farm.id, text);
            toast.show('Note added to farm', 'document-text');
          } catch (e: any) {
            toast.error(e?.message ?? 'Could not save that note');
          }
        }}
      />
    </Screen>
  );
}

const styles = StyleSheet.create({
  primaryAction: { marginBottom: spacing.sm },
  manageRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.sm,
    marginBottom: spacing.lg,
  },
  // grow to fill, but wrap rather than squeeze a label past legibility
  manageBtn: { flexGrow: 1, flexBasis: '30%', minWidth: 104 },
  heroRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.lg },
  heroText: { flex: 1, gap: spacing.hairline },
  chipsRow: {
    flexDirection: 'row',
    gap: spacing.sm,
    marginTop: spacing.xxl,
  },
  chipLabel: { textAlign: 'center' },
  chip: {
    flex: 1,
    alignItems: 'center',
    gap: spacing.xs,
    backgroundColor: onDark.scrim,
    borderWidth: 1,
    borderColor: onDark.panelBorder,
    borderRadius: radius.md,
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.xs,
  },
  body: {
    paddingHorizontal: spacing.xl,
    marginTop: -spacing.xxxl,
  },
  statRow: { flexDirection: 'row', gap: spacing.md, marginBottom: spacing.md },
  herdBtn: { marginTop: spacing.sm },
  infoCard: { paddingVertical: spacing.sm },
  vetRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.md,
    marginTop: spacing.md,
  },
  vetText: { flex: 1, gap: spacing.hairline },
  activityCard: { gap: 0, paddingVertical: spacing.sm },
  pregCard: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  flex1: { flex: 1 },
  activityRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    paddingVertical: spacing.md - 2,
  },
  activityDivider: {
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.border,
  },
  activityText: { flex: 1, gap: spacing.hairline },
  notesCard: { gap: spacing.sm },
  noteRow: { flexDirection: 'row', gap: spacing.sm, alignItems: 'flex-start' },
  noteText: { flex: 1 },
});
