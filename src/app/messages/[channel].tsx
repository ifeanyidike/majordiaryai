import { Ionicons } from '@expo/vector-icons';
import { useLocalSearchParams, useRouter } from 'expo-router';
import React, { useEffect, useMemo } from 'react';
import { FlatList, Pressable, RefreshControl, StyleSheet, View } from 'react-native';
import { EmptyState, Header, Screen, SkeletonList, Text } from '@/components';
import { colors, radius, spacing, status } from '@/theme';
import { AppMessage, MessageChannel, useAppStore } from '@/store/useAppStore';

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

  const { messages, messagesLoading, fetchMessages, markMessageRead } = useAppStore();
  const feed = messages[channel];

  useEffect(() => { fetchMessages(channel); }, [channel]);

  const unread = useMemo(() => feed.filter((m) => !m.readAt).length, [feed]);

  const open = (m: AppMessage) => {
    if (!m.readAt) markMessageRead(m.id);
    // A message about a specific cow is nearly always a request to go look at
    // her, so opening it goes where the work is.
    if (m.cowId) router.push({ pathname: '/cow/[id]', params: { id: m.cowId } });
    else if (m.farmId) router.push({ pathname: '/farm/[id]', params: { id: m.farmId } });
  };

  return (
    <Screen>
      <Header
        title={meta.title}
        subtitle={unread ? `${unread} unread · ${meta.subtitle}` : meta.subtitle}
        back
      />
      <FlatList
        data={feed}
        keyExtractor={(m) => m.id}
        contentContainerStyle={feed.length ? styles.list : styles.listEmpty}
        refreshControl={
          <RefreshControl refreshing={messagesLoading} onRefresh={() => fetchMessages(channel)} />
        }
        ListEmptyComponent={
          messagesLoading ? (
            <SkeletonList count={4} />
          ) : (
            <EmptyState icon={meta.icon} title={`No ${meta.title.toLowerCase()}`} message={meta.empty} />
          )
        }
        renderItem={({ item: m }) => (
          <Pressable
            onPress={() => open(m)}
            style={[styles.row, !m.readAt && styles.rowUnread]}
            accessibilityRole="button"
            accessibilityLabel={`${m.senderName ?? 'Message'}: ${m.body}`}
          >
            <View style={[styles.iconWrap, { backgroundColor: `${meta.color}1A` }]}>
              <Ionicons name={meta.icon} size={20} color={meta.color} />
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
              <Text variant="body">{m.body}</Text>
              <View style={styles.footLine}>
                {m.senderName ? (
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
            </View>
            {!m.readAt ? <View style={[styles.dot, { backgroundColor: meta.color }]} /> : null}
          </Pressable>
        )}
      />
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
});
