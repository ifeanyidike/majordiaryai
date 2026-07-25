import React from 'react';
import { StyleSheet, View, ViewStyle } from 'react-native';
import { colors, radius } from '@/theme';
import { Text } from './Text';

interface MonogramProps {
  name: string;
  size?: number;
  bg?: string;
  color?: string;
  style?: ViewStyle;
}

/** Initials avatar — gives list rows and profile heroes a personal identity. */
export function Monogram({
  name,
  size = 48,
  bg = colors.primary,
  color = colors.textOnPrimary,
  style,
}: MonogramProps) {
  const initials = name
    .split(' ')
    .filter((w) => /^[A-Za-z]/.test(w))
    .slice(0, 2)
    .map((w) => w[0].toUpperCase())
    .join('');

  return (
    <View
      style={[
        styles.box,
        { width: size, height: size, borderRadius: size * 0.32, backgroundColor: bg },
        style,
      ]}
    >
      <Text
        variant="heading"
        color={color}
        style={{ fontSize: size * 0.38, lineHeight: size * 0.48 }}
      >
        {initials}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  box: {
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: radius.md,
  },
});
