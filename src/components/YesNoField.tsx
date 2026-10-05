import React from 'react';
import { StyleSheet, View } from 'react-native';
import { spacing } from '@/theme';
import { FormLabel } from './FormField';
import { SegmentedControl } from './SegmentedControl';

type Answer = 'yes' | 'no';

const OPTIONS = [
  { value: 'yes' as const, label: 'Yes' },
  { value: 'no' as const, label: 'No' },
];

/**
 * A report question the technician must answer — Yes or No, nothing picked
 * until they pick it.
 *
 * Replaces the on/off switches (Josh, Oct 4: "remove toggle switches from
 * every report ... a cow cannot be saved or cleared from a report until the
 * question is answered"). A switch starts at "no", so an untouched switch
 * and a deliberate "no" were the same record; `null` here is "not answered",
 * and forms keep Save disabled until every question is non-null.
 */
export function YesNoField({
  label, value, onChange,
}: {
  label: string;
  value: boolean | null;
  onChange: (value: boolean) => void;
}) {
  return (
    <View style={styles.field}>
      <FormLabel>{label}</FormLabel>
      <SegmentedControl<Answer>
        options={OPTIONS}
        value={value === null ? null : value ? 'yes' : 'no'}
        onChange={(v) => onChange(v === 'yes')}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  field: { marginBottom: spacing.md },
});
