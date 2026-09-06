import React, { useState } from 'react';
import { LayoutChangeEvent, Pressable, StyleSheet, View } from 'react-native';
import { charcoal, colors, radius, spacing } from '@/theme';
import { Text } from '../Text';

/**
 * A column chart built from Views — no SVG, so no native rebuild.
 *
 * Deliberately spare. The first version wore a 40px axis-label column, four
 * gridlines, a floating benchmark caption and a permanent "show values" link,
 * which is more chrome than data on a phone. What is left: two hairlines with
 * their values set small and muted INSIDE the plot, a benchmark rule, and the
 * bars. Labels appear on the latest bar and the best one, never on all of
 * them; every other value comes from tapping a bar, and each bar carries its
 * own accessibility label so nothing is gated behind touch precision.
 *
 * One hue for the series and the de-emphasis gray for pending bars — emphasis,
 * not a second category (validated: ΔE 30.8 under deuteranopia, 35 normal).
 */

export interface BarDatum {
  label: string;
  value: number | null;
  /** Drawn gray — e.g. a cycle too recent to have pregnancy results. */
  pending?: boolean;
  /** Shown when the bar is tapped. */
  detail?: string;
}

interface Props {
  data: BarDatum[];
  unit?: string;
  benchmark?: { value: number; label: string };
  height?: number;
  pendingLabel?: string;
}

const BAR_MAX = 22;
const MIN_BAR = 3;

/**
 * Axis ceiling: one nice step above the data, with headroom for the label
 * that sits over the tallest bar. A fixed 0–100 would squash a 15–30%
 * pregnancy-rate series into the bottom third of the plot.
 */
function ceilingFor(values: number[], unit?: string): number {
  const top = Math.max(0, ...values);
  if (top === 0) return unit === '%' ? 10 : 1;
  const withHeadroom = top * 1.18;
  if (unit === '%') {
    return [10, 20, 25, 30, 40, 50, 60, 75, 80, 100].find((n) => n >= withHeadroom) ?? 100;
  }
  const pow = 10 ** Math.floor(Math.log10(withHeadroom));
  const step = withHeadroom / pow <= 2 ? pow / 2 : withHeadroom / pow <= 5 ? pow : pow * 2;
  return Math.ceil(withHeadroom / step) * step;
}

const fmt = (v: number | null, unit?: string) =>
  v == null ? '—' : `${Number.isInteger(v) ? v : v.toFixed(1)}${unit === '%' ? '%' : ''}`;

export function BarChart({
  data, unit, benchmark, height = 132, pendingLabel = 'Awaiting results',
}: Props) {
  const [width, setWidth] = useState(0);
  const [selected, setSelected] = useState<number | null>(null);

  const values = data.map((d) => d.value ?? 0);
  const ceiling = ceilingFor([...values, benchmark?.value ?? 0], unit);
  const y = (v: number) => (v / ceiling) * height;

  // Two labels at most: the latest bar, and the best one when it is elsewhere.
  const last = data.length - 1;
  const best = values.reduce((m, v, i) => (v > values[m] ? i : m), 0);
  const labelled = new Set([last, ...(values[best] > 0 ? [best] : [])]);

  // With eight bars a date label per slot collides. Show alternate ones,
  // anchored so the newest — the one being read — always has its label.
  const showX = (i: number) => i % 2 === last % 2;

  const slot = width > 0 ? width / data.length : 0;
  const barW = Math.max(MIN_BAR, Math.min(BAR_MAX, slot * 0.52));

  return (
    <View>
      <View
        style={[styles.plot, { height }]}
        onLayout={(e: LayoutChangeEvent) => setWidth(e.nativeEvent.layout.width)}
      >
        {/* Two hairlines, values inline and muted — no axis gutter */}
        {[1, 0.5].map((f) => (
          <View key={f} pointerEvents="none" style={[styles.gridWrap, { bottom: height * f }]}>
            <View style={styles.grid} />
            <Text variant="caption" color={colors.textMuted} style={styles.gridLabel}>
              {fmt(ceiling * f, unit)}
            </Text>
          </View>
        ))}

        {benchmark ? (
          <View pointerEvents="none" style={[styles.gridWrap, { bottom: y(benchmark.value) }]}>
            <View style={styles.benchmark} />
            <Text variant="caption" color={colors.textSecondary} style={styles.gridLabel}>
              {benchmark.label}
            </Text>
          </View>
        ) : null}

        {width > 0 && (
          <View style={styles.bars}>
            {data.map((d, i) => {
              // A pending bar at zero still shows a stub: "awaiting results"
              // must not look identical to "no data".
              const h = d.value == null ? 0
                : Math.max(d.value > 0 || d.pending ? 2 : 0, y(d.value));
              const sel = selected === i;
              return (
                <Pressable
                  key={`${d.label}-${i}`}
                  onPress={() => setSelected(sel ? null : i)}
                  style={[styles.slot, { width: slot }]}
                  accessibilityRole="button"
                  accessibilityLabel={`${d.label}: ${fmt(d.value, unit)}${d.pending ? `, ${pendingLabel}` : ''}`}
                >
                  {(labelled.has(i) || sel) && d.value != null ? (
                    <Text
                      variant="caption"
                      color={sel ? colors.text : colors.textSecondary}
                      style={[styles.barLabel, { bottom: h + 3 }]}
                    >
                      {fmt(d.value, unit)}
                    </Text>
                  ) : null}
                  <View
                    style={[
                      styles.bar,
                      {
                        width: barW,
                        height: h,
                        backgroundColor: d.pending ? charcoal[200] : colors.primary,
                        opacity: selected != null && !sel ? 0.35 : 1,
                      },
                    ]}
                  />
                </Pressable>
              );
            })}
          </View>
        )}
      </View>

      <View style={styles.xRow}>
        {data.map((d, i) => (
          <View key={`${d.label}-x-${i}`} style={{ width: slot, alignItems: 'center' }}>
            {showX(i) ? (
              <Text variant="caption" color={colors.textMuted} numberOfLines={1}>
                {d.label}
              </Text>
            ) : null}
          </View>
        ))}
      </View>

      {selected != null && data[selected] ? (
        <View style={styles.readout}>
          <Text variant="bodyBold">
            {data[selected].label} · {fmt(data[selected].value, unit)}
          </Text>
          {data[selected].detail ? (
            <Text variant="caption" color={colors.textSecondary}>
              {data[selected].detail}
              {data[selected].pending ? ` · ${pendingLabel}` : ''}
            </Text>
          ) : null}
        </View>
      ) : (
        <Text variant="caption" color={colors.textMuted} style={styles.hint}>
          Tap a bar for detail
        </Text>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  plot: { position: 'relative' },
  gridWrap: { position: 'absolute', left: 0, right: 0 },
  grid: { height: StyleSheet.hairlineWidth, backgroundColor: colors.border },
  benchmark: { height: 1, backgroundColor: charcoal[300] },
  gridLabel: { position: 'absolute', left: 0, bottom: 2, fontVariant: ['tabular-nums'] },
  bars: {
    position: 'absolute', top: 0, left: 0, right: 0, bottom: 0,
    flexDirection: 'row', alignItems: 'flex-end',
  },
  slot: { alignItems: 'center', justifyContent: 'flex-end', height: '100%' },
  bar: { borderTopLeftRadius: 4, borderTopRightRadius: 4 },
  barLabel: { position: 'absolute', fontVariant: ['tabular-nums'] },
  xRow: { flexDirection: 'row', marginTop: spacing.sm },
  readout: {
    marginTop: spacing.md,
    padding: spacing.md,
    backgroundColor: colors.surfaceSoft,
    borderRadius: radius.sm,
    gap: 1,
  },
  hint: { marginTop: spacing.md, textAlign: 'center' },
});
