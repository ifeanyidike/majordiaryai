import { Ionicons } from '@expo/vector-icons';
import React, { useEffect, useRef } from 'react';
import { StyleSheet, View } from 'react-native';
import { colors, radius, spacing } from '@/theme';
import { onReconnect } from '@/lib/net';
import { Button } from './Button';
import { Text } from './Text';

interface ErrorBannerProps {
  message: string;
  onRetry?: () => void;
}

/** Inline load-failure banner with retry — so an API outage never looks like an empty herd. */
export function ErrorBanner({ message, onRetry }: ErrorBannerProps) {
  // When the signal comes back, retry by itself, so a "No signal" message does
  // not stay on the screen after the connection has returned. Every Retry
  // given to this banner reloads data; none sends a save.
  const retry = useRef(onRetry);
  useEffect(() => { retry.current = onRetry; }, [onRetry]);
  useEffect(() => onReconnect(() => retry.current?.()), []);

  return (
    <View style={styles.banner}>
      <Ionicons name="cloud-offline-outline" size={20} color={colors.danger} />
      <Text variant="body" color={colors.text} style={styles.msg} numberOfLines={3}>
        {message}
      </Text>
      {onRetry ? <Button compact variant="secondary" label="Retry" onPress={onRetry} /> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  banner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    backgroundColor: colors.red[50],
    borderWidth: 1,
    borderColor: colors.red[200],
    borderRadius: radius.md,
    padding: spacing.lg,
    marginBottom: spacing.lg,
  },
  msg: { flex: 1 },
});
