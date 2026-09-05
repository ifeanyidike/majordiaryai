import React, { useState } from 'react';
import { LayoutChangeEvent, Pressable, StyleSheet, View } from 'react-native';
import { charcoal, colors, radius, spacing } from '@/theme';
import { Text } from '../Text';

/**
 * A column chart built from Views — no SVG dependency, so no native rebuild.
 *
 * It follows the mark specs that keep a chart quiet: bars capped at 24px wide
 * with a 4px rounded data-end and a square baseline, a 2px surface gap between
 * neighbours, three solid hairline gridlines one step off the surface, and
 * labels only where they earn their place — the extreme and the latest value —
 * with the rest on tap and in the table view below. Text never wears the data
 * colour; identity comes from the mark beside it.
 *
 * Two series at most: the value in the accent hue, and "pending" in the
 * de-emphasis gray, which is the emphasis form (one hue + gray) rather than a
 * second categorical colour. A legend appears only when both are present.
 */

export interface BarDatum {
  label: string;
  value: number | null;
  /** Drawn in the de-emphasis gray — e.g. a cycle too recent to judge. */
  pending?: boolean;
  /** Extra line shown on tap and in the table. */
  detail?: string;
}

interface Props {
  data: BarDatum[];
  unit?: string;
  /** A target drawn as a labelled hairline — the reader's reference, not a series. */
  benchmark?: { value: number; label: string };
  /** Upper bound of the axis; defaults to a clean ceiling above the data. */
  max?: number;
  height?: number;
  pendingLabel?: string;
  valueLabel?: string;
}

const BAR_MAX = 24;
const GAP = 2;
const TICK_LINE = 12;

/**
 * Axis ceiling and gridline count.
 *
 * Percentages used to get a fixed ceiling of 100, which is honest for a
 * compliance series at 95% and useless for a pregnancy-rate series at 15–30%
 * — the bars sat in the bottom third with the target line, and the
 * difference between a good cycle and a poor one was a few pixels. The
 * ceiling now sits one nice step above the data (with 15% headroom for the
 * value labels), and the gridlines divide it into round numbers.
 */
function axisFor(values: number[], unit?: string): { ceiling: number; steps: number } {
  const top = Math.max(0, ...values);
  if (unit === '%') {
    const nice = [10, 20, 25, 30, 40, 50, 60, 75, 80, 100];
    const ceiling = nice.find((n) => n >= top * 1.15) ?? 100;
    const steps = { 10: 2, 20: 4, 25: 5, 30: 3, 40: 4, 50: 5, 60: 3, 75: 3, 80: 4, 100: 4 }[ceiling] ?? 4;
    return { ceiling, steps };
  }
  if (top === 0) return { ceiling: 1, steps: 1 };
  const pow = 10 ** Math.floor(Math.log10(top));
  const step = top / pow <= 2 ? pow / 2 : top / pow <= 5 ? pow : pow * 2;
  const ceiling = Math.ceil(top / step) * step;
  const steps = ceiling / step <= 5 ? ceiling / step : 4;
  return { ceiling, steps };
}

const fmt = (v: number | null, unit?: string) =>
  v == null ? '—' : `${Number.isInteger(v) ? v : v.toFixed(1)}${unit ?? ''}`;

export function BarChart({
  data, unit, benchmark, max, height = 150,
  pendingLabel = 'Awaiting results', valueLabel = 'Confirmed',
}: Props) {
  const [width, setWidth] = useState(0);
  const [selected, setSelected] = useState<number | null>(null);
  const [table, setTable] = useState(false);

  const values = data.map((d) => d.value ?? 0);
  const axis = axisFor([...values, benchmark?.value ?? 0], unit);
  const ceiling = max ?? axis.ceiling;
  const GRID_STEPS = max ? 4 : axis.steps;
  const hasPending = data.some((d) => d.pending);

  // Label the extreme and the latest — never every point.
  const maxIdx = values.reduce((m, v, i) => (v > values[m] ? i : m), 0);
  const lastIdx = data.length - 1;

  const slot = width > 0 ? width / data.length : 0;
  const barW = Math.max(4, Math.min(BAR_MAX, slot - GAP * 2));

  const onLayout = (e: LayoutChangeEvent) => setWidth(e.nativeEvent.layout.width);
  const y = (v: number) => (ceiling ? (v / ceiling) * height : 0);

  return (
    <View>
      {/* Plot */}
      <View style={styles.plotRow}>
        {/* Axis ticks, each centred on its gridline */}
        <View style={[styles.axis, { height }]}>
          {Array.from({ length: GRID_STEPS + 1 }, (_, i) => {
            const v = (ceiling / GRID_STEPS) * i;
            return (
              <Text
                key={i}
                variant="caption"
                color={colors.textMuted}
                style={[styles.tick, { bottom: (height / GRID_STEPS) * i - TICK_LINE / 2 }]}
              >
                {fmt(v, unit)}
              </Text>
            );
          })}
        </View>

        <View style={[styles.plot, { height }]} onLayout={onLayout}>
          {/* Gridlines: solid hairlines, one step off the surface */}
          {Array.from({ length: GRID_STEPS + 1 }, (_, i) => (
            <View
              key={i}
              pointerEvents="none"
              style={[styles.grid, { bottom: (height / GRID_STEPS) * i }]}
            />
          ))}

          {/* Benchmark reference — a hairline the reader can compare against */}
          {benchmark ? (
            <View pointerEvents="none" style={[styles.benchmark, { bottom: y(benchmark.value) }]}>
              <Text variant="caption" color={colors.textSecondary} style={styles.benchmarkLabel}>
                {benchmark.label}
              </Text>
            </View>
          ) : null}

          {/* Bars */}
          {width > 0 && (
            <View style={styles.bars}>
              {data.map((d, i) => {
                // A pending cycle at zero still draws a 2px stub: "awaiting
                // checks" must look different from "no data here".
                const h = d.value == null ? 0
                  : Math.max(d.value > 0 || d.pending ? 2 : 0, y(d.value));
                const showLabel = d.value != null && (i === maxIdx || i === lastIdx) && selected == null;
                const isSel = selected === i;
                return (
                  <Pressable
                    key={`${d.label}-${i}`}
                    onPress={() => setSelected(isSel ? null : i)}
                    style={[styles.slot, { width: slot }]}
                    accessibilityRole="button"
                    accessibilityLabel={`${d.label}: ${fmt(d.value, unit)}${d.pending ? `, ${pendingLabel}` : ''}`}
                  >
                    {(showLabel || isSel) && (
                      <Text
                        variant="caption"
                        color={colors.text}
                        style={[styles.valueLabel, { bottom: h + 4 }]}
                        numberOfLines={1}
                      >
                        {fmt(d.value, unit)}
                      </Text>
                    )}
                    <View
                      style={[
                        styles.bar,
                        {
                          width: barW,
                          height: h,
                          backgroundColor: d.pending ? charcoal[200] : colors.primary,
                          opacity: selected != null && !isSel ? 0.45 : 1,
                        },
                      ]}
                    />
                  </Pressable>
                );
              })}
            </View>
          )}
        </View>
      </View>

      {/* X labels */}
      <View style={[styles.xRow, { paddingLeft: styles.axis.width }]}>
        {data.map((d, i) => (
          <View key={`${d.label}-${i}`} style={{ width: slot, alignItems: 'center' }}>
            <Text variant="caption" color={colors.textMuted} numberOfLines={1}>
              {d.label}
            </Text>
          </View>
        ))}
      </View>

      {/* Tap readout — the tooltip's equivalent on touch */}
      {selected != null && data[selected] ? (
        <View style={styles.readout}>
          <View style={[styles.swatch, { backgroundColor: data[selected].pending ? charcoal[200] : colors.primary }]} />
          <Text variant="bodyBold">{data[selected].label}</Text>
          <Text variant="body" color={colors.textSecondary}>
            {fmt(data[selected].value, unit)}
            {data[selected].detail ? ` · ${data[selected].detail}` : ''}
            {data[selected].pending ? ` · ${pendingLabel}` : ''}
          </Text>
        </View>
      ) : null}

      {/* Legend only when two series are actually on screen */}
      {hasPending ? (
        <View style={styles.legend}>
          <View style={styles.legendItem}>
            <View style={[styles.swatch, { backgroundColor: colors.primary }]} />
            <Text variant="caption" color={colors.textSecondary}>{valueLabel}</Text>
          </View>
          <View style={styles.legendItem}>
            <View style={[styles.swatch, { backgroundColor: charcoal[200] }]} />
            <Text variant="caption" color={colors.textSecondary}>{pendingLabel}</Text>
          </View>
        </View>
      ) : null}

      {/* Table view — every value reachable without colour or touch precision */}
      <Pressable onPress={() => setTable((t) => !t)} hitSlop={8} accessibilityRole="button">
        <Text variant="caption" color={colors.primary} style={styles.tableToggle}>
          {table ? 'Hide values' : 'Show values'}
        </Text>
      </Pressable>
      {table ? (
        <View style={styles.table}>
          {data.map((d, i) => (
            <View key={`${d.label}-row-${i}`} style={styles.tableRow}>
              <Text variant="caption" color={colors.textSecondary} style={styles.tableLabel}>{d.label}</Text>
              <Text variant="caption" color={colors.text} style={styles.tableValue}>{fmt(d.value, unit)}</Text>
              <Text variant="caption" color={colors.textMuted} style={styles.tableDetail} numberOfLines={1}>
                {[d.detail, d.pending ? pendingLabel : null].filter(Boolean).join(' · ')}
              </Text>
            </View>
          ))}
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  plotRow: { flexDirection: 'row' },
  axis: { width: 40, position: 'relative', paddingRight: spacing.xs },
  tick: {
    position: 'absolute', right: spacing.xs, textAlign: 'right',
    fontVariant: ['tabular-nums'], lineHeight: TICK_LINE,
  },
  plot: { flex: 1, position: 'relative' },
  grid: {
    position: 'absolute', left: 0, right: 0, height: StyleSheet.hairlineWidth,
    backgroundColor: colors.border,
  },
  benchmark: {
    position: 'absolute', left: 0, right: 0, height: 1, backgroundColor: charcoal[400],
  },
  benchmarkLabel: {
    position: 'absolute', right: 0, bottom: 2, paddingHorizontal: spacing.xs,
    backgroundColor: colors.surface,
  },
  bars: { position: 'absolute', left: 0, right: 0, bottom: 0, top: 0, flexDirection: 'row', alignItems: 'flex-end' },
  slot: { alignItems: 'center', justifyContent: 'flex-end', height: '100%' },
  bar: {
    borderTopLeftRadius: 4, borderTopRightRadius: 4,   // rounded data-end, square baseline
  },
  valueLabel: { position: 'absolute', fontVariant: ['tabular-nums'] },
  xRow: { flexDirection: 'row', marginTop: spacing.xs },
  readout: {
    flexDirection: 'row', alignItems: 'center', gap: spacing.sm,
    marginTop: spacing.md, padding: spacing.md,
    backgroundColor: colors.surfaceSoft, borderRadius: radius.sm,
  },
  swatch: { width: 10, height: 10, borderRadius: 3 },
  legend: { flexDirection: 'row', gap: spacing.lg, marginTop: spacing.md },
  legendItem: { flexDirection: 'row', alignItems: 'center', gap: spacing.xs + 2 },
  tableToggle: { marginTop: spacing.md },
  table: { marginTop: spacing.sm, gap: spacing.xs },
  tableRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  tableLabel: { width: 64 },
  tableValue: { width: 56, textAlign: 'right', fontVariant: ['tabular-nums'] },
  tableDetail: { flex: 1 },
});
