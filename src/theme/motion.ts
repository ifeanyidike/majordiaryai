/**
 * Motion tokens, and the one place that asks whether motion is wanted at all.
 *
 * The app leans on entrance animations — every list row, card and stat strip
 * animates in. That reads as polish to most people and as motion sickness to
 * some, and iOS/Android both expose "Reduce Motion" precisely so an app can
 * tell the difference. Nothing was reading it, so the setting did nothing here.
 *
 * `useMotion()` returns the durations and delays to use. With Reduce Motion on
 * they collapse to zero, which makes every `entering` animation resolve
 * instantly rather than being removed — the layout is identical either way, so
 * there is no second code path to keep correct.
 */

import { useEffect, useState } from 'react';
import { AccessibilityInfo } from 'react-native';
import { FadeIn, FadeInDown, FadeInUp } from 'react-native-reanimated';

/** Durations, in ms. Short enough to feel immediate, long enough to read. */
export const duration = {
  /** Micro-feedback: press, toggle, pill change. */
  fast: 160,
  /** Standard entrance and exit. */
  base: 320,
  /** Hero and full-screen transitions. */
  slow: 480,
} as const;

/**
 * Stagger between siblings in a list.
 *
 * Capped by `staggerFor` below: past a handful of rows a per-row delay stops
 * reading as choreography and starts reading as lag, because the last row
 * arrives visibly late on a full screen of content.
 */
export const stagger = { step: 45, maxSteps: 6 } as const;

export function staggerFor(index: number): number {
  return Math.min(index, stagger.maxSteps) * stagger.step;
}

let cachedReduceMotion = false;

export function useReduceMotion(): boolean {
  const [reduced, setReduced] = useState(cachedReduceMotion);

  useEffect(() => {
    let alive = true;
    AccessibilityInfo.isReduceMotionEnabled().then((on) => {
      cachedReduceMotion = on;
      if (alive) setReduced(on);
    });
    const sub = AccessibilityInfo.addEventListener('reduceMotionChanged', (on) => {
      cachedReduceMotion = on;
      setReduced(on);
    });
    return () => {
      alive = false;
      sub.remove();
    };
  }, []);

  return reduced;
}

/**
 * Entrance animations that honour Reduce Motion.
 *
 * Usage mirrors reanimated's own API:
 *   const motion = useMotion();
 *   <Animated.View entering={motion.up(index)} />
 */
export function useMotion() {
  const reduced = useReduceMotion();

  const d = reduced ? 0 : duration.base;
  const delayFor = (index = 0) => (reduced ? 0 : staggerFor(index));

  /**
   * Explicit timings, preserved as authored.
   *
   * Screens that were choreographed by hand (a hero at 0, its chips at 120,
   * the stat strip at 150…) keep those exact numbers; this only collapses
   * them to zero when Reduce Motion is on, so converting a screen changes
   * nothing about how it looks for everyone else.
   */
  const at = (base: typeof FadeInUp, delayMs: number, durationMs: number) =>
    reduced ? base.delay(0).duration(0) : base.delay(delayMs).duration(durationMs);

  return {
    reduced,
    /** Rises into place — lists, cards, anything below the fold. */
    up: (index = 0) => FadeInUp.delay(delayFor(index)).duration(d),
    /** Drops into place — headers and hero content. */
    down: (index = 0) => FadeInDown.delay(delayFor(index)).duration(d),
    /** No translation — use when a shift would fight the layout. */
    in: (index = 0) => FadeIn.delay(delayFor(index)).duration(d),

    upAt: (delayMs = 0, durationMs: number = duration.base) => at(FadeInUp, delayMs, durationMs),
    downAt: (delayMs = 0, durationMs: number = duration.base) => at(FadeInDown, delayMs, durationMs),
    inAt: (delayMs = 0, durationMs: number = duration.base) => at(FadeIn, delayMs, durationMs),

    /** The springier brand entrance used on login and registration. */
    upSpring: (delayMs = 0, durationMs: number = duration.slow) =>
      reduced ? FadeInUp.duration(0) : FadeInUp.delay(delayMs).duration(durationMs).springify(),
    downSpring: (delayMs = 0, durationMs: number = duration.slow) =>
      reduced ? FadeInDown.duration(0) : FadeInDown.delay(delayMs).duration(durationMs).springify(),

    duration: d,
  };
}
