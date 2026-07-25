import { Ionicons } from '@expo/vector-icons';
import { LinearGradient } from 'expo-linear-gradient';
import { useRouter } from 'expo-router';
import React from 'react';
import { StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { colors, radius, spacing, touch } from '@/theme';
import { PressableScale } from './PressableScale';

interface HeroHeaderProps {
  /** Gradient colors, e.g. gradients.primary */
  gradient: readonly [string, string, ...string[]];
  children: React.ReactNode;
  back?: boolean;
  right?: React.ReactNode;
}

/**
 * Immersive gradient hero header with curved bottom.
 * Gives each screen family its own identity while sharing one component.
 * Place content that should overlap it with negative marginTop.
 */
export function HeroHeader({ gradient, children, back, right }: HeroHeaderProps) {
  const router = useRouter();
  const insets = useSafeAreaInsets();

  const goBack = () => {
    if (router.canGoBack()) router.back();
    else router.replace('/(tabs)/dashboard');
  };

  return (
    <LinearGradient
      colors={gradient as unknown as [string, string, ...string[]]}
      start={{ x: 0, y: 0 }}
      end={{ x: 1, y: 1 }}
      style={[styles.hero, { paddingTop: insets.top + spacing.md }]}
    >
      {/* decorative glow rings */}
      <View style={[styles.ring, styles.ringLarge]} pointerEvents="none" />
      <View style={[styles.ring, styles.ringSmall]} pointerEvents="none" />

      {(back || right) && (
        <View style={styles.navRow}>
          {back ? (
            <PressableScale
              haptic={false}
              onPress={goBack}
              style={styles.backBtn}
              accessibilityRole="button"
              accessibilityLabel="Go back"
            >
              <Ionicons name="arrow-back" size={22} color={colors.cream.base} />
            </PressableScale>
          ) : (
            <View />
          )}
          {right}
        </View>
      )}

      {children}
    </LinearGradient>
  );
}

const styles = StyleSheet.create({
  hero: {
    borderBottomLeftRadius: radius.xl,
    borderBottomRightRadius: radius.xl,
    paddingHorizontal: spacing.xl,
    paddingBottom: spacing.xxxl + spacing.xl,
    overflow: 'hidden',
  },
  navRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: spacing.lg,
  },
  backBtn: {
    width: touch.iconButton,
    height: touch.iconButton,
    borderRadius: touch.iconButton / 2,
    backgroundColor: 'rgba(252,251,249,0.16)',
    borderWidth: 1,
    borderColor: 'rgba(252,251,249,0.25)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  ring: {
    position: 'absolute',
    borderRadius: 999,
    borderWidth: 1.5,
    borderColor: 'rgba(252,251,249,0.10)',
  },
  ringLarge: {
    width: 280,
    height: 280,
    top: -110,
    right: -90,
  },
  ringSmall: {
    width: 170,
    height: 170,
    top: 40,
    right: -60,
    borderColor: 'rgba(252,251,249,0.07)',
  },
});
