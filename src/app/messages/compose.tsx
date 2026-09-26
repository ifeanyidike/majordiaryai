import { useLocalSearchParams, useRouter } from 'expo-router';
import React, { useEffect, useState } from 'react';
import { KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, View } from 'react-native';
import { Button, FormLabel, FormRow, Header, Screen, Text, useToast } from '@/components';
import { colors, radius, spacing } from '@/theme';
import { MessageChannel, useAppStore } from '@/store/useAppStore';
import { useRole } from '@/store/useAuthStore';

/**
 * Write an Alarm (farm owner → their technician) or an Office Alert
 * (administrator → a technician they choose).
 *
 * The feeds existed without this screen, which meant nothing in the app could
 * ever put a message in them: an owner had no way to raise the alarm the
 * client described as the whole point — "when a farmer wants to send a note
 * to a technician" — and only automatic route changes ever reached the
 * office feed.
 */
function isChannel(value: unknown): value is MessageChannel {
  return value === 'alarm' || value === 'office_alert';
}

export default function ComposeMessageScreen() {
  const router = useRouter();
  const toast = useToast();
  const role = useRole();
  const { channel: raw } = useLocalSearchParams<{ channel?: string }>();
  // The role decides the channel as much as the link does: an owner can only
  // raise an alarm, an administrator's message is an office alert. The API
  // enforces the same, so this only keeps the screen honest.
  const channel: MessageChannel =
    role === 'farm' ? 'alarm' : isChannel(raw) ? raw : 'office_alert';

  const { sendMessage, technicians, fetchTechnicians, farms, demoMode } = useAppStore();
  const [body, setBody] = useState('');
  const [recipientId, setRecipientId] = useState<string | undefined>();
  const [sending, setSending] = useState(false);

  const isOffice = channel === 'office_alert';
  useEffect(() => { if (isOffice) fetchTechnicians(); }, [isOffice]);

  // An owner's alarm goes to the technician on their farm; the server resolves
  // who that is. Naming them here is so the owner knows who will read it.
  const myFarm = role === 'farm' ? farms[0] : undefined;
  const recipients = technicians.filter((t) => t.role === 'technician' && t.isActive);

  const send = async () => {
    const text = body.trim();
    if (!text) {
      toast.error('Write the message first');
      return;
    }
    if (isOffice && !recipientId) {
      toast.error('Choose which technician this is for');
      return;
    }
    if (demoMode) {
      toast.error('Demo mode — connect the API to send messages');
      return;
    }
    setSending(true);
    try {
      await sendMessage({ channel, body: text, recipientId: isOffice ? recipientId : undefined });
      toast.success(isOffice ? 'Office alert sent' : 'Alarm raised');
      router.back();
    } catch (e: any) {
      toast.error(e?.message ?? 'Could not send');
    } finally {
      setSending(false);
    }
  };

  return (
    <Screen>
      <Header
        title={isOffice ? 'New Office Alert' : 'Raise an Alarm'}
        subtitle={
          isOffice
            ? 'From the office to one technician'
            : myFarm?.assignedTechnician
              ? `Goes to ${myFarm.assignedTechnician}, your technician`
              : 'Goes to the technician assigned to your farm'
        }
        back
      />
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        style={styles.flex1}
      >
        <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
          {isOffice ? (
            <>
              <FormLabel>To</FormLabel>
              {recipients.length === 0 ? (
                <Text variant="caption" color={colors.textMuted} style={styles.hint}>
                  No active technicians found.
                </Text>
              ) : (
                <View style={styles.recipients}>
                  {recipients.map((t) => {
                    const on = recipientId === t.id;
                    return (
                      <Pressable
                        key={t.id}
                        onPress={() => setRecipientId(t.id)}
                        style={[styles.recipient, on && styles.recipientOn]}
                        accessibilityRole="radio"
                        accessibilityState={{ selected: on }}
                      >
                        <Text variant="bodyBold">{t.name}</Text>
                        <Text variant="caption" color={colors.textMuted}>{t.email}</Text>
                      </Pressable>
                    );
                  })}
                </View>
              )}
            </>
          ) : null}

          <FormRow
            label="Message"
            value={body}
            onChangeText={setBody}
            placeholder={
              isOffice
                ? 'e.g. Start at Cedar Lane on Friday.'
                : 'e.g. The cow in pen 4 is down — please come today.'
            }
            multiline
          />

          <Button
            label={isOffice ? 'Send Office Alert' : 'Raise Alarm'}
            icon={isOffice ? 'briefcase' : 'alert-circle'}
            onPress={send}
            loading={sending}
            style={styles.send}
          />
        </ScrollView>
      </KeyboardAvoidingView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  flex1: { flex: 1 },
  content: { paddingBottom: spacing.xxl, gap: spacing.md },
  hint: { marginBottom: spacing.md },
  recipients: { gap: spacing.sm },
  recipient: {
    padding: spacing.md,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
    gap: spacing.hairline,
  },
  recipientOn: { borderColor: colors.primary, borderWidth: 2 },
  send: { marginTop: spacing.lg },
});
