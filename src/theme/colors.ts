/**
 * Major Dairy AI — Brand color system.
 * Every color in the app derives from the three brand colors.
 * Never use raw hex values in screens/components — import from here.
 */

/** Deep Red ramp — primary brand color #B3353C at 500 */
export const red = {
  50: '#FBEEEF',
  100: '#F5D6D8',
  200: '#EAADB1',
  300: '#DE8389',
  400: '#C95C64',
  500: '#B3353C', // brand
  600: '#9A2D33',
  700: '#7E2429',
  800: '#611B1F',
  900: '#431215',
} as const;

/** Charcoal ramp — brand black #1D1B1A at 900 */
export const charcoal = {
  50: '#F4F3F2',
  100: '#E5E3E1',
  200: '#CBC7C4',
  300: '#A8A29E',
  400: '#847D78',
  500: '#635D58',
  600: '#4A4541',
  700: '#38342F',
  800: '#282523',
  900: '#1D1B1A', // brand
} as const;

/** Off White ramp — brand white #FCFBF9 */
export const cream = {
  base: '#FCFBF9', // brand
  soft: '#F7F5F1',
  mist: '#F1EEE8',
  line: '#E7E3DC',
} as const;

/** Semantic status colors, tuned to sit well on the warm palette */
export const status = {
  pregnant:    { fg: '#2E7D4F', bg: '#E5F2EA' },
  open:        { fg: '#B07C10', bg: '#F9F0DC' },
  inseminated: { fg: '#7B5EA7', bg: '#F0EBF8' },
  dry:         { fg: '#3B6B9E', bg: '#E7EFF7' },
  fresh:       { fg: '#1F8A8A', bg: '#E2F2F2' },
  cull:        { fg: red[600],  bg: red[50]   },
  heat:        { fg: '#C2542B', bg: '#FBEAE2' },
  needling:    { fg: '#6B5B95', bg: '#EDE8F5' },
  calf:        { fg: '#7A6250', bg: '#F2EDE8' },
  heifer:      { fg: '#8B6914', bg: '#F5EDD4' },
  calving:     { fg: '#1F8A8A', bg: '#E2F2F2' },
  sold:        { fg: charcoal[500], bg: charcoal[50] },
  dead:        { fg: charcoal[700], bg: charcoal[100] },
} as const;

export type StatusKey = keyof typeof status;

/** Fallback pill colors for statuses the app doesn't know yet */
export const statusFallback = { fg: charcoal[500], bg: charcoal[50] } as const;

/** Append an alpha channel to a #RRGGBB hex — never string-concat alpha in screens */
export const alpha = (hex: string, opacity: number) =>
  hex + Math.round(Math.min(Math.max(opacity, 0), 1) * 255).toString(16).padStart(2, '0');

/**
 * Text and surface tokens for content sitting on dark hero gradients.
 * Screens must use these instead of hand-rolled rgba() literals.
 */
export const onDark = {
  text: cream.base,
  textSecondary: 'rgba(252, 251, 249, 0.75)',
  textMuted: 'rgba(252, 251, 249, 0.6)',
  /** Translucent light panel (stat ribbons on charcoal heroes) */
  panel: 'rgba(252, 251, 249, 0.12)',
  panelBorder: 'rgba(252, 251, 249, 0.18)',
  /** Translucent dark scrim (chips on red heroes, over video) */
  scrim: 'rgba(29, 27, 26, 0.22)',
  scrimStrong: 'rgba(29, 27, 26, 0.45)',
  divider: 'rgba(252, 251, 249, 0.15)',
} as const;

export const colors = {
  primary: red[500],
  primaryDark: red[700],
  primarySoft: red[50],

  background: cream.base,
  surface: '#FFFFFF',
  surfaceSoft: cream.soft,
  border: cream.line,

  text: charcoal[900],
  textSecondary: charcoal[500],
  textMuted: charcoal[300],
  textOnPrimary: cream.base,

  success: status.pregnant.fg,
  warning: status.open.fg,
  danger: red[600],

  overlayDark: 'rgba(29, 27, 26, 0.55)',

  tabInactive: charcoal[300],

  red,
  charcoal,
  cream,
  status,
  onDark,
} as const;
