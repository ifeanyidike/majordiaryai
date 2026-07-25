import { Platform, TextStyle } from 'react-native';

const sans = Platform.select({ ios: 'System', default: 'sans-serif' })!;

export type TextVariant =
  | 'display'
  | 'title'
  | 'heading'
  | 'subheading'
  | 'body'
  | 'bodyBold'
  | 'caption'
  | 'label'
  | 'stat'
  | 'statSmall'
  | 'tabLabel'
  | 'input';

export const typography: Record<TextVariant, TextStyle> = {
  /** Hero numbers / login wordmark */
  display: {
    fontFamily: sans,
    fontSize: 34,
    fontWeight: '800',
    letterSpacing: -0.8,
    lineHeight: 40,
  },
  /** Screen titles */
  title: {
    fontFamily: sans,
    fontSize: 26,
    fontWeight: '700',
    letterSpacing: -0.5,
    lineHeight: 32,
  },
  /** Card titles */
  heading: {
    fontFamily: sans,
    fontSize: 18,
    fontWeight: '700',
    letterSpacing: -0.3,
    lineHeight: 24,
  },
  /** Row titles, emphasized body */
  subheading: {
    fontFamily: sans,
    fontSize: 16,
    fontWeight: '600',
    letterSpacing: -0.2,
    lineHeight: 22,
  },
  body: {
    fontFamily: sans,
    fontSize: 15,
    fontWeight: '400',
    lineHeight: 21,
  },
  bodyBold: {
    fontFamily: sans,
    fontSize: 15,
    fontWeight: '600',
    lineHeight: 21,
  },
  caption: {
    fontFamily: sans,
    fontSize: 13,
    fontWeight: '400',
    lineHeight: 18,
  },
  /** Section labels, pills — uppercase */
  label: {
    fontFamily: sans,
    fontSize: 12,
    fontWeight: '700',
    letterSpacing: 0.8,
    textTransform: 'uppercase',
    lineHeight: 16,
  },
  /** Big stat numbers */
  stat: {
    fontFamily: sans,
    fontSize: 24,
    fontWeight: '800',
    letterSpacing: -0.5,
    lineHeight: 30,
  },
  /** Compact stat numbers (summary strips, ribbons) */
  statSmall: {
    fontFamily: sans,
    fontSize: 20,
    fontWeight: '800',
    letterSpacing: -0.4,
    lineHeight: 26,
  },
  /** Tab bar labels */
  tabLabel: {
    fontFamily: sans,
    fontSize: 11,
    fontWeight: '600',
    lineHeight: 14,
  },
  /** Text inputs — one size on every form in the app */
  input: {
    fontFamily: sans,
    fontSize: 16,
    fontWeight: '400',
    lineHeight: 22,
  },
};
