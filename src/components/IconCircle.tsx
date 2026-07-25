import { Ionicons } from '@expo/vector-icons';
import React from 'react';
import { StyleSheet, View, ViewStyle } from 'react-native';
import { colors, radius } from '@/theme';

interface IconCircleProps {
  name: keyof typeof Ionicons.glyphMap;
  size?: number;
  color?: string;
  bg?: string;
  style?: ViewStyle;
}

export function IconCircle({
  name,
  size = 44,
  color = colors.primary,
  bg = colors.primarySoft,
  style,
}: IconCircleProps) {
  return (
    <View
      style={[
        styles.circle,
        { width: size, height: size, backgroundColor: bg },
        style,
      ]}
    >
      <Ionicons name={name} size={size * 0.5} color={color} />
    </View>
  );
}

const styles = StyleSheet.create({
  circle: {
    borderRadius: radius.pill,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
