import { ViewStyle } from 'react-native';

export { colors, red, charcoal, cream, status, statusFallback, onDark, alpha } from './colors';
export type { StatusKey } from './colors';
export { typography } from './typography';
export type { TextVariant } from './typography';

/** 4pt spacing grid */
export const spacing = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 20,
  xxl: 24,
  xxxl: 32,
  huge: 48,
} as const;

export const radius = {
  sm: 10,
  md: 14,
  lg: 20,
  xl: 28,
  pill: 999,
} as const;

/** Soft layered shadows for the premium feel */
export const shadows: Record<'card' | 'raised' | 'hero', ViewStyle> = {
  card: {
    shadowColor: '#1D1B1A',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.06,
    shadowRadius: 8,
    elevation: 2,
  },
  raised: {
    shadowColor: '#1D1B1A',
    shadowOffset: { width: 0, height: 6 },
    shadowOpacity: 0.1,
    shadowRadius: 16,
    elevation: 5,
  },
  hero: {
    shadowColor: '#B3353C',
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.28,
    shadowRadius: 20,
    elevation: 8,
  },
};

/** Gradient presets for hero headers — one identity per screen family */
export const gradients = {
  /** Dashboard + Farm profile — brand red */
  primary: ['#C74850', '#B3353C', '#84252B'] as const,
  /** Cow profile + Reports analytics — charcoal */
  charcoal: ['#38342F', '#242220', '#1D1B1A'] as const,
  /** Vet profile — deep brand red, distinct from the primary dashboard red */
  vet: ['#84252B', '#611B1F', '#431215'] as const,
};

/** Consistent hit target for large, confident buttons */
export const touch = {
  buttonHeight: 56,
  rowHeight: 64,
  iconButton: 44,
} as const;
