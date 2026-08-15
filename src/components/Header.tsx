import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import React from 'react';
import { StyleSheet, View } from 'react-native';
import { colors, spacing, touch } from '@/theme';
import { PressableScale } from './PressableScale';
import { Text } from './Text';

interface HeaderProps {
  title: string;
  subtitle?: string;
  back?: boolean;
  right?: React.ReactNode;
}

/** Screen title bar with optional back button. */
export function Header({ title, subtitle, back, right }: HeaderProps) {
  const router = useRouter();

  const goBack = () => {
    if (router.canGoBack()) router.back();
    else router.replace('/(tabs)/dashboard');
  };
  return (
    <View style={styles.wrap}>
      <View style={styles.topRow}>
        {back ? (
          <PressableScale
            haptic={false}
            onPress={goBack}
            style={styles.backBtn}
            accessibilityRole="button"
            accessibilityLabel="Go back"
          >
            <Ionicons name="arrow-back" size={22} color={colors.text} />
          </PressableScale>
        ) : null}
        <View style={styles.titleCol}>
          <Text variant="title">{title}</Text>
          {subtitle ? (
            <Text variant="caption" color={colors.textSecondary}>
              {subtitle}
            </Text>
          ) : null}
        </View>
        {right}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { marginBottom: spacing.lg },
  topRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
  },
  backBtn: {
    width: touch.iconButton,
    height: touch.iconButton,
    borderRadius: touch.iconButton / 2,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    alignItems: 'center',
    justifyContent: 'center',
  },
  titleCol: { flex: 1, gap: spacing.hairline },
});
