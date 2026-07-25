import React from 'react';
import { Text as RNText, TextProps as RNTextProps } from 'react-native';
import { colors, typography, TextVariant } from '@/theme';

interface TextProps extends RNTextProps {
  variant?: TextVariant;
  color?: string;
}

export function Text({ variant = 'body', color = colors.text, style, ...rest }: TextProps) {
  return <RNText style={[typography[variant], { color }, style]} {...rest} />;
}
