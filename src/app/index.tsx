import { LinearGradient } from 'expo-linear-gradient';
import { useRouter } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { VideoView } from 'expo-video';
import React, { useRef, useState } from 'react';
import { Image, StyleSheet, TextInput, View, KeyboardAvoidingView, Platform } from 'react-native';
import Animated from 'react-native-reanimated';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Button, PressableScale, Text, useToast } from '@/components';
import { colors, radius, spacing, typography, useMotion } from '@/theme';
import { useAmbientVideo } from '@/hooks/useAmbientVideo';
import { useAuthStore } from '@/store/useAuthStore';
import { supabase } from '@/lib/supabase';

const videoSource = require('@/assets/video/cow_field.mp4');
const poster = require('@/assets/images/login-poster.jpg');
const logoImage = require('@/assets/images/logo.png');

export default function LoginScreen() {
  const motion = useMotion();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const showToast = useToast((s) => s.show);
  const { signIn, loading, error, clearError } = useAuthStore();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const passwordRef = useRef<TextInput>(null);

  const { player, videoFailed } = useAmbientVideo(videoSource);

  const handleForgotPassword = async () => {
    const e = email.trim();
    if (!e) {
      showToast('Enter your email above first', 'mail-outline');
      return;
    }
    const { error: resetError } = await supabase.auth.resetPasswordForEmail(e);
    if (resetError) {
      showToast(resetError.message, 'alert-circle');
    } else {
      showToast('Password reset email sent', 'lock-closed');
    }
  };

  const handleSignIn = async () => {
    if (!email.trim() || !password.trim()) {
      showToast('Please enter your email and password', 'alert-circle');
      return;
    }
    await signIn(email.trim(), password);
    // _layout AuthGuard handles redirect once user is set
  };

  // Show error toast when error changes
  React.useEffect(() => {
    if (error) {
      showToast(error, 'alert-circle');
      clearError();
    }
  }, [error]);

  return (
    <KeyboardAvoidingView
      style={styles.root}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <StatusBar style="light" />

      <Image source={poster} style={StyleSheet.absoluteFill} resizeMode="cover" />
      {!videoFailed && (
        <VideoView
          player={player}
          style={StyleSheet.absoluteFill}
          contentFit="cover"
          nativeControls={false}
        />
      )}
      <LinearGradient
        colors={['rgba(29,27,26,0.55)', 'rgba(29,27,26,0.15)', 'rgba(29,27,26,0.88)']}
        locations={[0, 0.45, 1]}
        style={StyleSheet.absoluteFill}
      />

      <View style={[styles.content, { paddingTop: insets.top + spacing.huge, paddingBottom: insets.bottom + spacing.xl }]}>
        {/* Brand */}
        <Animated.View entering={motion.downSpring(0, 700)} style={styles.brand}>
          <Image source={logoImage} style={styles.logoImage} resizeMode="contain" />
          <View style={styles.taglineRule} />
          <Text variant="subheading" color="rgba(252,251,249,0.92)" style={styles.tagline}>
            Driven By Passion and Results
          </Text>
        </Animated.View>

        <View style={styles.spacer} />

        {/* Login form */}
        <Animated.View entering={motion.upSpring(250, 700)} style={styles.actions}>
          <TextInput
            style={styles.input}
            placeholder="Email address"
            placeholderTextColor="rgba(252,251,249,0.45)"
            keyboardType="email-address"
            autoCapitalize="none"
            autoCorrect={false}
            value={email}
            onChangeText={setEmail}
            returnKeyType="next"
            onSubmitEditing={() => passwordRef.current?.focus()}
          />
          <TextInput
            ref={passwordRef}
            style={styles.input}
            placeholder="Password"
            placeholderTextColor="rgba(252,251,249,0.45)"
            secureTextEntry
            value={password}
            onChangeText={setPassword}
            onSubmitEditing={handleSignIn}
            returnKeyType="go"
          />

          <Button
            label="Sign In"
            icon="log-in"
            variant="primary"
            onPress={handleSignIn}
            loading={loading}
          />

          <View style={styles.linksRow}>
            <PressableScale haptic={false} onPress={() => router.push('/register' as any)}>
              <Text variant="bodyBold" color={colors.cream.base}>Register</Text>
            </PressableScale>
            <View style={styles.linkDot} />
            <PressableScale haptic={false} onPress={handleForgotPassword}>
              <Text variant="bodyBold" color={colors.cream.base}>Forgot Password</Text>
            </PressableScale>
            <View style={styles.linkDot} />
            <PressableScale haptic={false} onPress={() => showToast('Support: help@majordairy.ai', 'help-buoy')}>
              <Text variant="bodyBold" color={colors.cream.base}>Support</Text>
            </PressableScale>
          </View>
        </Animated.View>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.charcoal[900] },
  content: {
    flex: 1,
    paddingHorizontal: spacing.xxl,
  },
  brand: { alignItems: 'center', gap: spacing.md },
  logoImage: { width: 280, height: 129 },
  taglineRule: {
    width: 44,
    height: 3,
    borderRadius: 2,
    backgroundColor: colors.primary,
  },
  tagline: { textAlign: 'center' },
  spacer: { flex: 1 },
  actions: { gap: spacing.md },
  input: {
    backgroundColor: 'rgba(252,251,249,0.12)',
    borderWidth: 1,
    borderColor: 'rgba(252,251,249,0.2)',
    borderRadius: radius.md,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    color: colors.cream.base,
    ...typography.input,
  },
  linksRow: {
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    gap: spacing.md,
    marginTop: spacing.lg,
  },
  linkDot: {
    width: 4,
    height: 4,
    borderRadius: 2,
    backgroundColor: 'rgba(252,251,249,0.5)',
  },
});
