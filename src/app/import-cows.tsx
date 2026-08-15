import { Ionicons } from '@expo/vector-icons';
import * as DocumentPicker from 'expo-document-picker';
import { useRouter } from 'expo-router';
import React, { useEffect, useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import { Button, Card, Header, Screen, SectionHeader, Text, useToast } from '@/components';
import { api, isApiConfigured } from '@/lib/api';
import { colors, radius, spacing, status } from '@/theme';
import { useAppStore } from '@/store/useAppStore';
import { useAuthStore } from '@/store/useAuthStore';

interface ImportError {
  row: number;
  ear_tag?: string | null;
  message: string;
}

interface ImportResult {
  filename: string;
  total_rows: number;
  created: number;
  updated: number;
  skipped: number;
  ignored_columns: string[];
  errors: ImportError[];
}

interface PickedFile {
  uri: string;
  name: string;
  type: string;
}

/** Canonical columns the importer understands (also documented server-side). */
const EXPECTED_COLUMNS = [
  'ear_tag (required)', 'breed', 'date_of_birth', 'lactation_number',
  'status', 'current_program', 'last_calving_date',
  'last_insemination_date', 'due_date', 'dry_date', 'notes',
];

export default function ImportCowsScreen() {
  const router = useRouter();
  const toast = useToast();
  const { user } = useAuthStore();
  const { farms, fetchFarms, fetchCows } = useAppStore();
  const [farmId, setFarmId] = useState<string | null>(null);
  const [file, setFile] = useState<PickedFile | null>(null);
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState<ImportResult | null>(null);

  useEffect(() => {
    if (farms.length === 0) fetchFarms();
  }, []);
  useEffect(() => {
    if (!farmId && farms.length > 0) setFarmId(farms[0].id);
  }, [farms]);

  const pickFile = async () => {
    const res = await DocumentPicker.getDocumentAsync({
      type: [
        'text/csv',
        'text/comma-separated-values',
        'application/vnd.ms-excel',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      ],
      copyToCacheDirectory: true,
    });
    if (res.canceled || !res.assets?.[0]) return;
    const asset = res.assets[0];
    const name = asset.name ?? 'herd.csv';
    const ext = name.toLowerCase().split('.').pop();
    if (ext !== 'csv' && ext !== 'xlsx') {
      toast.error('Please choose a .csv or .xlsx file');
      return;
    }
    setResult(null);
    setFile({
      uri: asset.uri,
      name,
      type: asset.mimeType ?? (ext === 'xlsx'
        ? 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        : 'text/csv'),
    });
  };

  const runImport = async () => {
    if (!file || !farmId) return;
    if (!isApiConfigured) {
      toast.error('Demo mode — connect the API to import cows.');
      return;
    }
    setUploading(true);
    setResult(null);
    try {
      const res = await api.upload<ImportResult>(`/imports/cows?farm_id=${farmId}`, file);
      setResult(res);
      toast.success(`Imported ${res.created + res.updated} cows`);
      fetchCows();
    } catch (e: any) {
      toast.error(e?.message ?? 'Import failed');
    } finally {
      setUploading(false);
    }
  };

  if (user && user.role !== 'admin' && user.role !== 'technician') {
    return (
      <Screen>
        <Header back title="Import Cows" />
        <Card style={styles.card}>
          <Text variant="body" color={colors.textSecondary}>
            Only administrators and technicians can import herd data.
          </Text>
        </Card>
      </Screen>
    );
  }

  return (
    <Screen>
      <Header back title="Import Cows" subtitle="Upload a herd spreadsheet" />

      <SectionHeader title="1 · Choose Farm" />
      <Card style={styles.card}>
        {farms.length === 0 ? (
          <Text variant="body" color={colors.textMuted}>No farms available.</Text>
        ) : (
          farms.map((f, i) => {
            const selected = f.id === farmId;
            return (
              <Pressable
                key={f.id}
                onPress={() => setFarmId(f.id)}
                style={[styles.farmRow, i > 0 && styles.divided]}
                accessibilityRole="radio"
                accessibilityState={{ selected }}
                accessibilityLabel={f.name}
              >
                <Ionicons
                  name={selected ? 'radio-button-on' : 'radio-button-off'}
                  size={20}
                  color={selected ? colors.primary : colors.textMuted}
                />
                <Text variant="subheading" style={styles.flex1} numberOfLines={1}>{f.name}</Text>
                <Text variant="caption" color={colors.textSecondary}>{f.city}</Text>
              </Pressable>
            );
          })
        )}
      </Card>

      <SectionHeader title="2 · Choose File" />
      <Card style={styles.card}>
        <Pressable style={styles.filePick} onPress={pickFile} accessibilityRole="button" accessibilityLabel="Choose file">
          <Ionicons name={file ? 'document-text' : 'cloud-upload-outline'} size={24} color={colors.primary} />
          <View style={styles.flex1}>
            <Text variant="subheading" numberOfLines={1}>
              {file ? file.name : 'Choose a .csv or .xlsx file'}
            </Text>
            <Text variant="caption" color={colors.textSecondary}>
              {file ? 'Tap to choose a different file' : 'Herd master data export'}
            </Text>
          </View>
          <Ionicons name="chevron-forward" size={18} color={colors.textMuted} />
        </Pressable>
      </Card>

      <Button
        label={uploading ? 'Importing…' : 'Import Herd'}
        icon="cloud-upload"
        onPress={runImport}
        loading={uploading}
        disabled={!file || !farmId}
        style={styles.importBtn}
      />

      {result ? (
        <>
          <SectionHeader title="Result" />
          <Card style={styles.card}>
            <View style={styles.statsRow}>
              <Stat value={result.created} label="Created" color={status.pregnant.fg} />
              <Stat value={result.updated} label="Updated" color={status.dry.fg} />
              <Stat value={result.skipped} label="Skipped" color={result.skipped ? status.heat.fg : colors.textMuted} />
            </View>
            <Text variant="caption" color={colors.textSecondary} style={styles.resultMeta}>
              {result.filename} · {result.total_rows} rows read
            </Text>
            {result.ignored_columns.length > 0 && (
              <Text variant="caption" color={colors.textSecondary} style={styles.resultMeta}>
                Ignored columns: {result.ignored_columns.join(', ')}
              </Text>
            )}
            {result.errors.length > 0 && (
              <View style={styles.errors}>
                <Text variant="label" color={colors.danger}>{result.errors.length} row errors</Text>
                {result.errors.slice(0, 10).map((e, i) => (
                  <Text key={i} variant="caption" color={colors.textSecondary}>
                    Row {e.row}{e.ear_tag ? ` (${e.ear_tag})` : ''}: {e.message}
                  </Text>
                ))}
                {result.errors.length > 10 && (
                  <Text variant="caption" color={colors.textMuted}>
                    …and {result.errors.length - 10} more
                  </Text>
                )}
              </View>
            )}
          </Card>
          <Button
            variant="secondary"
            label="View Herd"
            icon="list"
            onPress={() => farmId && router.push({ pathname: '/farm/herd', params: { id: farmId } })}
            style={styles.importBtn}
          />
        </>
      ) : null}

      <SectionHeader title="Expected Columns" />
      <Card style={styles.card}>
        <Text variant="caption" color={colors.textSecondary} style={{ marginBottom: spacing.sm }}>
          The importer matches these column names (spelling is flexible — extra columns are ignored).
          It updates existing cows by ear tag and creates new ones.
        </Text>
        <View style={styles.chips}>
          {EXPECTED_COLUMNS.map((c) => (
            <View key={c} style={styles.chip}>
              <Text variant="caption" color={colors.textSecondary}>{c}</Text>
            </View>
          ))}
        </View>
      </Card>
    </Screen>
  );
}

function Stat({ value, label, color }: { value: number; label: string; color: string }) {
  return (
    <View style={styles.stat}>
      <Text variant="stat" color={color}>{value}</Text>
      <Text variant="caption" color={colors.textSecondary}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  card: { paddingVertical: spacing.md },
  flex1: { flex: 1 },
  divided: { borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border },
  farmRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    paddingVertical: spacing.md,
    minHeight: 48,
  },
  filePick: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    paddingVertical: spacing.sm,
  },
  importBtn: { marginTop: spacing.lg },
  statsRow: { flexDirection: 'row' },
  stat: { flex: 1, alignItems: 'center', gap: spacing.hairline },
  resultMeta: { marginTop: spacing.md },
  errors: { marginTop: spacing.md, gap: spacing.hairline },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
  chip: {
    backgroundColor: colors.surfaceSoft,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.sm,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs + 2,
  },
});
