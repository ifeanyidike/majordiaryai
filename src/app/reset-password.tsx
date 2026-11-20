import * as Linking from 'expo-linking';
import { useRouter } from 'expo-router';
import React, { useMemo, useState } from 'react';
import { KeyboardAvoidingView, Platform, ScrollView, StyleSheet, View } from 'react-native';
import { Button, EmptyState, FormRow, Header, Screen, useToast } from '@/components';
import { spacing } from '@/theme';
import { supabase } from '@/lib/supabase';
import { useAuthStore } from '@/store/useAuthStore';
import { friendlyAuthError } from '@/lib/authErrors';

/**
 * Set a new password, from the Forgot Password email.
 *
 * The email's link signs the person in for this one purpose and opens
 * majordairyai://reset-password#access_token=…&refresh_token=…&type=recovery.
 * The link works once; a used or old one comes back with an error instead,
 * which is shown here. After the new password is saved they are signed out,
 * so they sign in with it and know it works.
 *
 * Needs "majordairyai://reset-password" in Supabase, Authentication, URL
 * Configuration, Redirect URLs. Without it Supabase sends them to its Site URL.
 */

/** The tokens or the error Supabase puts after the # of the link. */
function readLink(url: string | null): { access?: string; refresh?: string; error?: string } {
  if (!url) return {};
  const hash = url.split('#')[1] ?? url.split('?')[1] ?? '';
  // By hand: React Native's URLSearchParams has not always implemented get().
  const p: Record<string, string> = {};
  for (const pair of hash.split('&')) {
    const [k, v = ''] = pair.split('=');
    if (k) p[decodeURIComponent(k)] = decodeURIComponent(v.replace(/\+/g, ' '));
  }
  return {
    access: p.access_token || undefined,
    refresh: p.refresh_token || undefined,
    error: p.error_description || p.error || undefined,
  };
}

export default function ResetPasswordScreen() {
  const router = useRouter();
  const toast = useToast();
  const url = Linking.useURL();
  const link = useMemo(() => readLink(url), [url]);
  const signOut = useAuthStore((s) => s.signOut);

  const [password, setPassword] = useState('');
  const [again, setAgain] = useState('');
  const [touched, setTouched] = useState(false);
  const [saving, setSaving] = useState(false);

  const tooShort = password.length < 8;
  const differs = password !== again;

  if (!link.access || !link.refresh) {
    return (
      <Screen>
        <Header back title="New Password" />
        <EmptyState
          icon="lock-closed-outline"
          title={url ? 'This link cannot be used' : 'Opening the link…'}
          message={url
            ? `${link.error ? `${link.error}. ` : ''}A reset link works once and expires. On the sign-in screen, enter your email and tap Forgot Password for a new one.`
            : undefined}
        />
        {url ? (
          <View style={styles.actions}>
            <Button label="Back to sign in" onPress={() => router.replace('/')} />
          </View>
        ) : null}
      </Screen>
    );
  }

  const save = async () => {
    setTouched(true);
    if (tooShort || differs) return;
    setSaving(true);
    try {
      const { error: sessionError } = await supabase.auth.setSession({
        access_token: link.access!, refresh_token: link.refresh!,
      });
      if (sessionError) throw sessionError;
      const { error } = await supabase.auth.updateUser({ password });
      if (error) throw error;
      await signOut();
      toast.success('Password changed — sign in with your new password');
      router.replace('/');
    } catch (e: any) {
      toast.error(friendlyAuthError(e, 'Could not change the password — try again.'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Screen scroll={false} padded={false}>
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={styles.flex1}>
        <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
          <Header back title="New Password" subtitle="Choose the password you will sign in with" />
          <FormRow label="New password" value={password} onChangeText={setPassword}
                   placeholder="At least 8 characters" secureTextEntry
                   error={touched && tooShort ? 'At least 8 characters' : undefined} />
          <FormRow label="Type it again" value={again} onChangeText={setAgain}
                   placeholder="The same password" secureTextEntry
                   error={touched && !tooShort && differs ? 'The two do not match' : undefined} />
          <View style={styles.actions}>
            <Button label="Save Password" icon="checkmark" onPress={save} loading={saving}
                    disabled={touched && (tooShort || differs)} />
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  flex1: { flex: 1 },
  content: { paddingHorizontal: spacing.xl, paddingBottom: spacing.huge },
  actions: { marginTop: spacing.lg, paddingHorizontal: spacing.xl },
});
