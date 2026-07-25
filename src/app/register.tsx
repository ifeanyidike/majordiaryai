import { Ionicons } from '@expo/vector-icons';
import { LinearGradient } from 'expo-linear-gradient';
import { useRouter } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { VideoView } from 'expo-video';
import React, { useEffect, useRef, useState } from 'react';
import {
  Image,
  ScrollView,
  StyleSheet,
  TextInput,
  View,
} from 'react-native';
import Animated, { FadeInDown, FadeInUp } from 'react-native-reanimated';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Button, PressableScale, Text, useToast } from '@/components';
import { alpha, colors, radius, spacing, typography } from '@/theme';
import { useAmbientVideo } from '@/hooks/useAmbientVideo';
import { Role, useAuthStore } from '@/store/useAuthStore';

const videoSource = require('@/assets/video/cow_field.mp4');
const poster = require('@/assets/images/login-poster.jpg');
const logoImage = require('@/assets/images/logo.png');

type RoleOption = { role: Role; label: string; icon: keyof typeof Ionicons.glyphMap };

const ROLES: RoleOption[] = [
  { role: 'technician', label: 'Technician', icon: 'construct' },
  { role: 'farm', label: 'Farm Manager', icon: 'home' },
  { role: 'vet', label: 'Veterinarian', icon: 'medkit' },
];

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export default function RegisterScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const showToast = useToast((s) => s.show);
  const { signUp, loading, error, needsConfirmation, user, clearError } = useAuthStore();

  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [role, setRole] = useState<Role>('technician');
  const [phone, setPhone] = useState('');

  const emailRef = useRef<TextInput>(null);
  const passwordRef = useRef<TextInput>(null);
  const confirmRef = useRef<TextInput>(null);
  const phoneRef = useRef<TextInput>(null);

  const { player, videoFailed } = useAmbientVideo(videoSource);

  // Navigate to dashboard once profile is loaded
  useEffect(() => {
    if (user) router.replace('/(tabs)/dashboard');
  }, [user]);

  // Show error toast
  useEffect(() => {
    if (error) {
      showToast(error, 'alert-circle');
      clearError();
    }
  }, [error]);

  const handleSignUp = async () => {
    if (!name.trim()) return showToast('Please enter your full name', 'person');
    if (!EMAIL_RE.test(email.trim())) return showToast('Please enter a valid email address', 'mail');
    if (password.length < 6) return showToast('Password must be at least 6 characters', 'lock-closed');
    if (password !== confirmPassword) return showToast('Passwords do not match', 'alert-circle');
    await signUp(name.trim(), email.trim(), password, role, phone.trim() || undefined);
  };

  // Email confirmation required — show success state
  if (needsConfirmation) {
    return (
      <View style={[styles.root, styles.confirmRoot]}>
        <StatusBar style="light" />
        <Image source={poster} style={StyleSheet.absoluteFill} resizeMode="cover" />
        <LinearGradient
          colors={['rgba(29,27,26,0.85)', 'rgba(29,27,26,0.92)']}
          style={StyleSheet.absoluteFill}
        />
        <Animated.View
          entering={FadeInDown.duration(600).springify()}
          style={[styles.confirmCard, { paddingBottom: insets.bottom + spacing.xl, paddingTop: insets.top + spacing.huge }]}
        >
          <Text style={styles.confirmEmoji}>📬</Text>
          <Text variant="title" color={colors.cream.base} style={styles.centerText}>
            Check Your Email
          </Text>
          <Text variant="body" color="rgba(252,251,249,0.75)" style={styles.centerText}>
            We sent a confirmation link to{'\n'}
            <Text variant="bodyBold" color={colors.cream.base}>{email}</Text>
            {'\n\n'}Click the link to activate your account, then sign in.
          </Text>
          <Button
            label="Back to Sign In"
            icon="log-in"
            variant="primary"
            onPress={() => router.replace('/')}
            style={styles.confirmBtn}
          />
        </Animated.View>
      </View>
    );
  }

  return (
    <View style={styles.root}>
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
        colors={['rgba(29,27,26,0.65)', 'rgba(29,27,26,0.2)', 'rgba(29,27,26,0.92)']}
        locations={[0, 0.4, 1]}
        style={StyleSheet.absoluteFill}
      />

      <ScrollView
        contentContainerStyle={[
          styles.scroll,
          { paddingTop: insets.top + spacing.xl, paddingBottom: insets.bottom + spacing.xxl },
        ]}
        keyboardShouldPersistTaps="handled"
        keyboardDismissMode="on-drag"
        automaticallyAdjustKeyboardInsets
        showsVerticalScrollIndicator={false}
      >
        {/* Brand */}
        <Animated.View entering={FadeInDown.duration(600).springify()} style={styles.brand}>
          <Image source={logoImage} style={styles.logoImage} resizeMode="contain" />
        </Animated.View>

        <Animated.View entering={FadeInUp.delay(150).duration(600).springify()} style={styles.form}>
          <Text variant="title" color={colors.cream.base} style={styles.formTitle}>
            Create Account
          </Text>
          <Text variant="caption" color="rgba(252,251,249,0.6)" style={styles.formSubtitle}>
            Set up your Major Dairy AI profile
          </Text>

          {/* Role selector */}
          <View style={styles.roleRow}>
            {ROLES.map((r) => {
              const selected = role === r.role;
              const tint = selected ? colors.cream.base : 'rgba(252,251,249,0.6)';
              return (
                <PressableScale
                  key={r.role}
                  haptic={false}
                  onPress={() => setRole(r.role)}
                  style={[styles.roleChip, selected && styles.roleChipActive]}
                  accessibilityRole="radio"
                  accessibilityState={{ selected }}
                  accessibilityLabel={r.label}
                >
                  <Ionicons name={r.icon} size={22} color={tint} />
                  <Text style={styles.roleLabel} color={tint} numberOfLines={2}>
                    {r.label}
                  </Text>
                </PressableScale>
              );
            })}
          </View>

          {/* Form fields */}
          <TextInput
            style={styles.input}
            placeholder="Full name"
            placeholderTextColor="rgba(252,251,249,0.4)"
            value={name}
            onChangeText={setName}
            autoCapitalize="words"
            returnKeyType="next"
            onSubmitEditing={() => emailRef.current?.focus()}
          />
          <TextInput
            ref={emailRef}
            style={styles.input}
            placeholder="Email address"
            placeholderTextColor="rgba(252,251,249,0.4)"
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
            placeholder="Password (min. 6 characters)"
            placeholderTextColor="rgba(252,251,249,0.4)"
            secureTextEntry
            value={password}
            onChangeText={setPassword}
            returnKeyType="next"
            onSubmitEditing={() => confirmRef.current?.focus()}
          />
          <TextInput
            ref={confirmRef}
            style={styles.input}
            placeholder="Confirm password"
            placeholderTextColor="rgba(252,251,249,0.4)"
            secureTextEntry
            value={confirmPassword}
            onChangeText={setConfirmPassword}
            returnKeyType="next"
            onSubmitEditing={() => phoneRef.current?.focus()}
          />
          <TextInput
            ref={phoneRef}
            style={styles.input}
            placeholder="Phone number (optional)"
            placeholderTextColor="rgba(252,251,249,0.4)"
            keyboardType="phone-pad"
            value={phone}
            onChangeText={setPhone}
            returnKeyType="done"
            onSubmitEditing={handleSignUp}
          />

          <Button
            label="Create Account"
            icon="person-add"
            variant="primary"
            onPress={handleSignUp}
            loading={loading}
            style={styles.submitBtn}
          />

          <PressableScale haptic={false} onPress={() => router.back()} style={styles.signInLink}>
            <Text variant="body" color="rgba(252,251,249,0.65)">
              Already have an account?{' '}
              <Text variant="bodyBold" color={colors.cream.base}>Sign In</Text>
            </Text>
          </PressableScale>
        </Animated.View>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.charcoal[900] },
  scroll: {
    flexGrow: 1,
    paddingHorizontal: spacing.xxl,
    gap: spacing.xl,
  },
  brand: { alignItems: 'center' },
  logoImage: { width: 220, height: 100 },
  form: {
    backgroundColor: 'rgba(29,27,26,0.55)',
    borderRadius: radius.xl,
    borderWidth: 1,
    borderColor: 'rgba(252,251,249,0.12)',
    padding: spacing.xxl,
    gap: spacing.md,
  },
  formTitle: { textAlign: 'center' },
  formSubtitle: { textAlign: 'center', marginBottom: spacing.xs },
  roleRow: { flexDirection: 'row', gap: spacing.sm },
  roleChip: {
    flex: 1,
    minHeight: 78,
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.xs + 2,
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.xs,
    borderWidth: 1,
    borderColor: 'rgba(252,251,249,0.2)',
    borderRadius: radius.md,
    backgroundColor: 'rgba(252,251,249,0.06)',
  },
  roleChipActive: {
    borderColor: colors.primary,
    backgroundColor: alpha(colors.primary, 0.2),
  },
  roleLabel: {
    fontSize: 12,
    fontWeight: '600',
    lineHeight: 15,
    textAlign: 'center',
  },
  input: {
    backgroundColor: 'rgba(252,251,249,0.1)',
    borderWidth: 1,
    borderColor: 'rgba(252,251,249,0.18)',
    borderRadius: radius.md,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    color: colors.cream.base,
    ...typography.input,
  },
  submitBtn: { marginTop: spacing.xs },
  signInLink: { alignItems: 'center', paddingTop: spacing.xs },

  // Email confirmation state
  confirmRoot: { justifyContent: 'center' },
  confirmCard: {
    flex: 1,
    paddingHorizontal: spacing.xxl,
    justifyContent: 'center',
    alignItems: 'center',
    gap: spacing.lg,
  },
  confirmEmoji: { fontSize: 56 },
  centerText: { textAlign: 'center' },
  confirmBtn: { width: '100%', marginTop: spacing.xl },
});
