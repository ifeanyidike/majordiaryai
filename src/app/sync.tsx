import { Ionicons } from '@expo/vector-icons';
import React from 'react';
import { StyleSheet, View } from 'react-native';
import { Button, Card, EmptyState, Header, Screen, Text, syncedLabel } from '@/components';
import { colors, spacing } from '@/theme';
import { useNet } from '@/lib/net';
import { discardSave, syncPending, useOutbox } from '@/lib/outbox';
import { useAppStore } from '@/store/useAppStore';
import { useAuthStore } from '@/store/useAuthStore';

/**
 * Saves made without signal (Josh's Part A platform tests: "Outcomes recorded
 * offline are saved as pending"). Each waits here until it is sent; one the
 * server refused stays, with the reason, until it is discarded.
 */
export default function SyncScreen() {
  const online = useNet((s) => s.online);
  const userId = useAuthStore((s) => s.user?.id);
  const lastSyncedAt = useAppStore((s) => s.lastSyncedAt);
  const items = useOutbox((s) => s.items);
  const syncing = useOutbox((s) => s.syncing);
  const mine = items.filter((i) => i.userId === userId);
  const waiting = mine.filter((i) => !i.failed).length;
  // A save for a cow waits behind an earlier one for her that was refused.
  const behindRefused = (index: number) => {
    const cowId = mine[index].cowId;
    return !!cowId && mine.slice(0, index).some((i) => i.cowId === cowId && i.failed);
  };

  return (
    <Screen>
      <Header back title="Sync"
              subtitle={online ? `Last synced ${syncedLabel(lastSyncedAt)}`
                               : `No signal · last synced ${syncedLabel(lastSyncedAt)}`} />
      {mine.length === 0 ? (
        <EmptyState icon="cloud-done-outline" title="Everything is saved"
                    message="Nothing is waiting to be sent." />
      ) : (
        <>
          {waiting > 0 ? (
            <Button
              label={syncing ? 'Sending…' : 'Send now'}
              icon="cloud-upload"
              loading={syncing}
              disabled={!online}
              onPress={() => syncPending()}
              style={styles.send}
            />
          ) : null}
          {!online && waiting > 0 ? (
            <Text variant="caption" color={colors.textMuted} style={styles.hint}>
              They will be sent by themselves when you have signal.
            </Text>
          ) : null}
          {mine.map((i, index) => (
            <Card key={i.key} style={styles.card}>
              <View style={styles.row}>
                <Ionicons name={i.failed ? 'alert-circle' : 'time-outline'} size={18}
                          color={i.failed ? colors.danger : colors.textSecondary} />
                <View style={styles.flex1}>
                  <Text variant="bodyBold">{i.label}</Text>
                  <Text variant="caption" color={colors.textMuted}>
                    Saved {syncedLabel(new Date(i.createdAt).getTime())}
                  </Text>
                  <Text variant="caption" color={i.failed ? colors.danger : colors.textSecondary}>
                    {i.failed
                      ? `Could not be saved: ${i.failed}`
                      : behindRefused(index)
                        ? 'Waiting — an earlier save for this cow could not be saved. Discard it to send this.'
                        : 'Waiting to be sent'}
                  </Text>
                </View>
              </View>
              {i.failed ? (
                <Button compact variant="secondary" label="Discard" icon="trash-outline"
                        onPress={() => discardSave(i.key)} style={styles.discard} />
              ) : null}
            </Card>
          ))}
        </>
      )}
    </Screen>
  );
}

const styles = StyleSheet.create({
  flex1: { flex: 1, gap: 2 },
  send: { marginBottom: spacing.sm },
  hint: { marginBottom: spacing.md },
  card: { marginBottom: spacing.sm, gap: spacing.sm },
  row: { flexDirection: 'row', gap: spacing.md, alignItems: 'flex-start' },
  discard: { alignSelf: 'flex-start' },
});
