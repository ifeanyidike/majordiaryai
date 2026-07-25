import React from 'react';
import { RefreshControl, ScrollView, StyleSheet, View, ViewStyle } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { colors, spacing } from '@/theme';

/** Content column cap so screens stay readable on tablets / large devices */
const MAX_CONTENT_WIDTH = 720;

interface ScreenProps {
  children: React.ReactNode;
  /** Scrollable content (default true) */
  scroll?: boolean;
  /** Apply horizontal padding (default true) */
  padded?: boolean;
  /** Disable top safe-area padding — for screens with a HeroHeader (default true) */
  topInset?: boolean;
  /** Pull-to-refresh — provide both to enable */
  refreshing?: boolean;
  onRefresh?: () => void;
  /** Extra bottom padding for screens under the tab bar */
  style?: ViewStyle;
  contentStyle?: ViewStyle;
}

/** Safe-area aware screen wrapper with the app background. */
export function Screen({
  children,
  scroll = true,
  padded = true,
  topInset = true,
  refreshing,
  onRefresh,
  style,
  contentStyle,
}: ScreenProps) {
  const insets = useSafeAreaInsets();
  const padding: ViewStyle = {
    paddingTop: topInset ? insets.top + spacing.sm : 0,
    paddingHorizontal: padded ? spacing.xl : 0,
  };

  if (!scroll) {
    return (
      <View style={[styles.root, padding, style, contentStyle]}>
        <View style={styles.column}>{children}</View>
      </View>
    );
  }

  return (
    <ScrollView
      style={[styles.root, style]}
      contentContainerStyle={[padding, { paddingBottom: spacing.huge * 2 }, contentStyle]}
      showsVerticalScrollIndicator={false}
      keyboardShouldPersistTaps="handled"
      refreshControl={
        onRefresh ? (
          <RefreshControl
            refreshing={Boolean(refreshing)}
            onRefresh={onRefresh}
            tintColor={colors.primary}
            colors={[colors.primary]}
          />
        ) : undefined
      }
    >
      <View style={styles.column}>{children}</View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.background },
  column: {
    width: '100%',
    maxWidth: MAX_CONTENT_WIDTH,
    alignSelf: 'center',
    flexGrow: 1,
  },
});
