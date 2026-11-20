import { Ionicons } from '@expo/vector-icons';
import { useLocalSearchParams, useRouter } from 'expo-router';
import React, { useEffect, useMemo, useState } from 'react';
import { FlatList, Modal, Pressable, RefreshControl, ScrollView, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import {
  Button, EmptyState, Header, ModalToastHost, Screen, SkeletonList, Text, useToast,
} from '@/components';
import { colors, radius, shadows, spacing, status } from '@/theme';
import { AppMessage, MessageChannel, useAppStore } from '@/store/useAppStore';
import { useAuthStore, useRole } from '@/store/useAuthStore';
import { errorMessage } from '@/lib/api';

/**
 * Alarms and Office Alerts share this screen, because they are the same
 * object seen from two directions: one person wrote to this technician.
 * What differs is who, and that is the whole reason they are separate feeds —
 * so the sender leads every row, and the two channels never mix.
 */
const CHANNELS: Record<
  MessageChannel,
  { title: string; subtitle: string; icon: keyof typeof Ionicons.glyphMap; color: string;
    empty: string }
> = {
  alarm: {
    title: 'Alarms',
    subtitle: 'From the farm owners on your route',
    icon: 'alert-circle',
    color: status.heat.fg,
    empty: 'When a farm owner needs you, their message lands here.',
  },
  office_alert: {
    title: 'Office Alerts',
    subtitle: 'From the office',
    icon: 'briefcase',
    color: status.inseminated.fg,
    empty: 'Route changes and anything else from the office lands here.',
  },
};

/**
 * The CHANNELS wording is the technician's (he receives both). A farm owner
 * reading Alarms is reading what HE sent, and the office reading Office
 * Alerts is reading its own outbox — "From the farm owners on your route"
 * was wrong for both.
 */
function wordingFor(channel: MessageChannel, role: string | null | undefined) {
  const base = CHANNELS[channel];
  if (channel === 'alarm' && role === 'farm') {
    return { subtitle: 'Sent to your technician',
             empty: 'Alarms you raise are listed here. Use the pencil to raise one.' };
  }
  if (channel === 'alarm' && role === 'admin') {
    return { subtitle: 'From farms with no technician',
             empty: 'An alarm from a farm with no technician comes here.' };
  }
  if (channel === 'office_alert' && role === 'admin') {
    return { subtitle: 'Sent to technicians',
             empty: 'Office alerts you send are listed here. Use the pencil to send one.' };
  }
  return { subtitle: base.subtitle, empty: base.empty };
}

function relativeTime(iso: string): string {
  if (!iso) return '';
  const minutes = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (minutes < 1) return 'just now';
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  return days === 1 ? 'yesterday' : `${days}d ago`;
}

function isChannel(value: unknown): value is MessageChannel {
  return value === 'alarm' || value === 'office_alert';
}

export default function MessageFeedScreen() {
  const router = useRouter();
  const { channel: raw } = useLocalSearchParams<{ channel?: string }>();
  const channel: MessageChannel = isChannel(raw) ? raw : 'alarm';
  const meta = CHANNELS[channel];

  const {
    messages, messagesLoading, fetchMessages, markMessageRead, acknowledgeMessage,
  } = useAppStore();
  const toast = useToast();
  const insets = useSafeAreaInsets();
  // Josh's change requests (Nov 20): an alarm opens in a larger view with
  // "Not yet" or "Acknowledge"; neither is chosen for them.
  const [viewing, setViewing] = useState<AppMessage | null>(null);
  const [acking, setAcking] = useState(false);
  const myId = useAuthStore((s) => s.user?.id);
  const role = useRole();
  const wording = wordingFor(channel, role);
  // Mirrors SENDER_ROLES in routers/messages.py: owners raise alarms, only the
  // office writes office alerts. Technicians read both and write neither.
  const canWrite =
    (channel === 'alarm' && (role === 'farm' || role === 'admin')) ||
    (channel === 'office_alert' && role === 'admin');
  const feed = messages[channel];

  useEffect(() => { fetchMessages(channel); }, [channel]);

  // An alarm waits until it is acknowledged (acknowledged ones have left the
  // list); an office alert until it is read.
  const waiting = (m: AppMessage) =>
    m.recipientId === myId && (channel === 'alarm' ? !m.acknowledgedAt : !m.readAt);
  const unread = useMemo(() => feed.filter(waiting).length, [feed, myId, channel]);

  const goTo = (m: AppMessage) => {
    if (m.cowId) router.push({ pathname: '/cow/[id]', params: { id: m.cowId } });
    else if (m.farmId) router.push({ pathname: '/farm/[id]', params: { id: m.farmId } });
  };

  const acknowledge = async (m: AppMessage) => {
    setAcking(true);
    try {
      await acknowledgeMessage(m.id);
      setViewing(null);
      toast.success(m.kind === 'note' ? 'Note acknowledged' : 'Alarm acknowledged');
    } catch (e: any) {
      toast.error(errorMessage(e, 'Could not acknowledge it'));
    } finally {
      setAcking(false);
    }
  };

  const open = (m: AppMessage) => {
    // The feed carries your outbox as well as your inbox, and only the
    // RECIPIENT can mark a message read — marking your own sent message
    // decremented a badge that never counted it, and the request 404s.
    if (!m.readAt && m.recipientId === myId) markMessageRead(m.id);
    if (channel === 'alarm') {
      setViewing(m);
      return;
    }
    // A message about a specific cow is nearly always a request to go look at
    // her, so opening it goes where the work is.
    goTo(m);
  };

  return (
    // The list scrolls itself. Inside the Screen's own scroll view it could
    // not (React Native's "VirtualizedLists should never be nested" warning)
    // and drew every row at once.
    <Screen scroll={false}>
      <Header
        title={meta.title}
        subtitle={unread ? `${unread} unread · ${wording.subtitle}` : wording.subtitle}
        back
        right={
          canWrite ? (
            <Pressable
              onPress={() => router.push({ pathname: '/messages/compose', params: { channel } })}
              accessibilityRole="button"
              accessibilityLabel={channel === 'alarm' ? 'Raise an alarm' : 'New office alert'}
              hitSlop={12}
            >
              <Ionicons name="create-outline" size={24} color={colors.primary} />
            </Pressable>
          ) : undefined
        }
      />
      <FlatList
        data={feed}
        keyExtractor={(m) => m.id}
        style={styles.flex1}
        // Clear of Android's navigation bar, which draws over the app.
        contentContainerStyle={[
          feed.length ? styles.list : styles.listEmpty,
          { paddingBottom: spacing.huge + insets.bottom },
        ]}
        refreshControl={
          <RefreshControl refreshing={messagesLoading} onRefresh={() => fetchMessages(channel)} />
        }
        ListEmptyComponent={
          messagesLoading ? (
            <SkeletonList count={4} />
          ) : (
            <EmptyState icon={meta.icon} title={`No ${meta.title.toLowerCase()}`} message={wording.empty} />
          )
        }
        renderItem={({ item: m }) => (
          <Pressable
            onPress={() => open(m)}
            style={[styles.row, waiting(m) && styles.rowUnread]}
            accessibilityRole="button"
            accessibilityLabel={`${m.senderName ?? 'Message'}: ${m.body}`}
          >
            <View style={[styles.iconWrap, { backgroundColor: `${meta.color}1A` }]}>
              <Ionicons name={m.kind === 'note' ? 'chatbubble-ellipses' : meta.icon} size={20}
                        color={meta.color} />
            </View>
            <View style={styles.body}>
              {/* Who sent it, and from where — the same shape as a
                  notification row, where the farm leads and the cow closes. */}
              <View style={styles.topLine}>
                <Text variant="label" color={meta.color} numberOfLines={1} style={styles.flex1}>
                  {m.farmName ?? m.senderName ?? 'Message'}
                </Text>
                <Text variant="caption" color={colors.textMuted}>
                  {relativeTime(m.createdAt)}
                </Text>
              </View>
              <Text variant="body" numberOfLines={channel === 'alarm' ? 3 : undefined}>
                {m.kind === 'note' ? `Note · ${m.body}` : m.body}
              </Text>
              {/* With no farm, the sender already leads the row; don't say it twice. */}
              {(m.senderName && m.farmName) || m.cowLabel ? (
              <View style={styles.footLine}>
                {m.senderName && m.farmName ? (
                  <Text variant="caption" color={colors.textMuted} numberOfLines={1}>
                    {m.senderName}
                  </Text>
                ) : null}
                {m.cowLabel ? (
                  <View style={styles.cowLine}>
                    <Ionicons name="pricetag-outline" size={13} color={colors.textMuted} />
                    <Text variant="caption" color={colors.textMuted} numberOfLines={1}>
                      {m.cowLabel}
                    </Text>
                  </View>
                ) : null}
              </View>
              ) : null}
            </View>
            {waiting(m) ? (
              <View style={[styles.dot, { backgroundColor: meta.color }]} />
            ) : null}
          </Pressable>
        )}
      />

      <Modal visible={!!viewing} transparent animationType="slide" onRequestClose={() => setViewing(null)}>
        <View style={styles.modalRoot}>
          <Pressable style={styles.backdrop} onPress={() => setViewing(null)}
                     accessibilityRole="button" accessibilityLabel="Close" />
          {viewing ? (
            <View style={[styles.sheet, { paddingBottom: insets.bottom + spacing.lg }]}>
              <ModalToastHost />
              <View style={styles.handle} />
              <View style={styles.topLine}>
                <Ionicons name={viewing.kind === 'note' ? 'chatbubble-ellipses' : meta.icon}
                          size={20} color={meta.color} />
                <Text variant="heading" style={styles.flex1}>
                  {viewing.kind === 'note' ? 'Note' : 'Alarm'}
                  {viewing.farmName ? ` · ${viewing.farmName}` : ''}
                </Text>
              </View>
              <Text variant="caption" color={colors.textMuted} style={styles.sheetMeta}>
                {[viewing.senderName, relativeTime(viewing.createdAt), viewing.cowLabel]
                  .filter(Boolean).join(' · ')}
              </Text>
              <ScrollView style={styles.sheetBody}>
                <Text variant="title">{viewing.body}</Text>
              </ScrollView>
              {viewing.recipientId === myId && !viewing.acknowledgedAt ? (
                <View style={styles.actions}>
                  {/* Josh: "Neither is selected by default", so the two
                      carry the same weight; neither looks pre-chosen. */}
                  <Button variant="secondary" label="Not yet" icon="time-outline" style={styles.flex1}
                          disabled={acking} onPress={() => setViewing(null)} />
                  <Button variant="secondary" label="Acknowledge" icon="checkmark" style={styles.flex1}
                          loading={acking} onPress={() => acknowledge(viewing)} />
                </View>
              ) : null}
            </View>
          ) : null}
        </View>
      </Modal>
    </Screen>
  );
}

const styles = StyleSheet.create({
  flex1: { flex: 1 },
  list: { paddingBottom: spacing.xxl, gap: spacing.sm },
  listEmpty: { flexGrow: 1, justifyContent: 'center' },
  row: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: spacing.md,
    padding: spacing.lg,
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
  },
  rowUnread: { borderColor: colors.primary },
  iconWrap: {
    width: 38,
    height: 38,
    borderRadius: radius.pill,
    alignItems: 'center',
    justifyContent: 'center',
  },
  body: { flex: 1, gap: spacing.xs },
  topLine: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  footLine: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    flexWrap: 'wrap',
  },
  cowLine: { flexDirection: 'row', alignItems: 'center', gap: spacing.xs },
  dot: { width: 8, height: 8, borderRadius: 4, marginTop: spacing.xs },
  modalRoot: { flex: 1, justifyContent: 'flex-end' },
  backdrop: { ...StyleSheet.absoluteFill, backgroundColor: 'rgba(0,0,0,0.4)' },
  sheet: {
    backgroundColor: colors.background, borderTopLeftRadius: radius.lg, borderTopRightRadius: radius.lg,
    paddingHorizontal: spacing.xl, paddingTop: spacing.md, maxHeight: '85%', gap: spacing.sm,
    ...shadows.card,
  },
  handle: {
    alignSelf: 'center', width: 40, height: 4, borderRadius: 2,
    backgroundColor: colors.border, marginBottom: spacing.sm,
  },
  sheetMeta: { marginBottom: spacing.xs },
  sheetBody: { flexGrow: 0, maxHeight: 320, marginVertical: spacing.sm },
  actions: { flexDirection: 'row', gap: spacing.md, marginTop: spacing.sm },
});
