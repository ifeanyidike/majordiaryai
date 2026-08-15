import React from 'react';
import {
  KeyboardAvoidingView,
  Modal,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  View,
} from 'react-native';
import {
  CalvingForm,
  DryOffConfirmForm,
  EnrollForm,
  HeatCheckForm,
  InseminationForm,
  PregnancyCheckForm,
  RecordTarget,
  VaccinationForm,
} from './CowActionsSheet';
import { NeedlingCompleteForm } from './NeedlingCompleteForm';
import { Button, ModalToastHost, Text } from '@/components';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { colors, radius, spacing } from '@/theme';
import { RecordKind, WorklistCow } from '@/data/types';
import { useAppStore } from '@/store/useAppStore';

const TITLES: Record<RecordKind, string> = {
  heat: 'Record Heat Check',
  preg: 'Record Pregnancy Check',
  needling: 'Complete Needling',
  insemination: 'Record Insemination',
  vaccination: 'Record Vaccination',
  calving: 'Record Calving',
  enroll: 'Enroll in Protocol',
  dry_off: 'Confirm Dry Off',
};

interface Props {
  visible: boolean;
  /** The work-list row being actioned — it carries everything the form needs. */
  cow?: WorklistCow;
  /** Which report the row came from — needed to clear it in demo mode. */
  reportType?: string;
  onClose: () => void;
  onRecorded: () => void;
}

/** A work-list row satisfies the forms' `RecordTarget` shape directly. */
function asTarget(cow: WorklistCow): RecordTarget {
  return {
    id: cow.cowId,
    earTag: cow.earTag,
    status: cow.status,
    farmId: cow.farmId,
    lastInseminationId: cow.lastInseminationId,
    lastInseminationDate: cow.lastInseminationDate,
    lastCalvingDate: cow.lastCalvingDate,
    healthStatus: cow.healthStatus,
  };
}

/**
 * Focused recording sheet opened from a report row — exactly the fields that
 * report's action needs, rather than bouncing to the full cow profile.
 *
 * Which form opens is the server's `record_kind`, not a client-side mapping: a
 * row the caller may not record arrives with `record_kind: null` and never
 * reaches this sheet.
 */
export function CowRecordSheet({ visible, cow, reportType, onClose, onRecorded }: Props) {
  const kind = cow?.recordKind ?? null;
  const insets = useSafeAreaInsets();
  const { demoMode, completeWorklistCowDemo } = useAppStore();

  const done = () => {
    onRecorded();
    onClose();
  };

  const renderForm = () => {
    if (!cow || !kind) return null;

    if (demoMode) {
      // No API to record against in the bundled demo — every form would error.
      // Offer an honest local completion instead so the flow stays explorable.
      return (
        <>
          <Text variant="body" color={colors.textSecondary} style={{ marginBottom: spacing.lg }}>
            You're in demo mode — nothing is saved. Mark this task done to see the
            work list update.
          </Text>
          <Button
            compact
            label="Mark Done (demo)"
            icon="checkmark"
            onPress={() => {
              if (reportType) completeWorklistCowDemo(reportType, cow.cowId);
              done();
            }}
          />
        </>
      );
    }

    const target = asTarget(cow);
    const common = { cow: target, onCancel: onClose, onComplete: done };

    switch (kind) {
      case 'heat':
        return <HeatCheckForm {...common} />;
      case 'preg':
        return <PregnancyCheckForm {...common} />;
      case 'vaccination':
        return <VaccinationForm {...common} />;
      case 'calving':
        return <CalvingForm {...common} />;
      case 'enroll':
        return <EnrollForm {...common} />;
      case 'dry_off':
        return <DryOffConfirmForm {...common} />;
      case 'needling':
        return cow.needlingRecordId ? (
          <NeedlingCompleteForm
            {...common}
            cowId={cow.cowId}
            recordId={cow.needlingRecordId}
            treatment={cow.treatment}
            context={cow.detail}
          />
        ) : (
          <Missing onClose={onClose} />
        );
      case 'insemination':
        return (
          <InseminationForm
            {...common}
            // `treatment` is present only while the final injection is still
            // outstanding — the server clears it once the shot is recorded, so
            // the banner never asks for a second dose.
            banner={
              cow.treatment
                ? `Final protocol day — give ${cow.treatment} with this insemination. Both are recorded together.`
                : undefined
            }
          />
        );
    }
  };

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        style={styles.root}
      >
        <Pressable
          style={styles.backdrop}
          onPress={onClose}
          accessibilityRole="button"
          accessibilityLabel="Dismiss"
        />
        <View style={[styles.sheet, { paddingBottom: insets.bottom + spacing.lg }]}>
          {/* Inside the Modal, or toasts render behind it. */}
          {visible && <ModalToastHost />}
          <View style={styles.handle} />
          <Text variant="heading">{kind ? TITLES[kind] : ''}</Text>
          {cow ? (
            <Text variant="caption" color={colors.textSecondary} style={styles.subtitle}>
              {cow.earTag}
            </Text>
          ) : null}
          <ScrollView
            showsVerticalScrollIndicator={false}
            keyboardShouldPersistTaps="handled"
            contentContainerStyle={{ gap: spacing.sm, paddingBottom: spacing.lg }}
          >
            {renderForm()}
          </ScrollView>
        </View>
      </KeyboardAvoidingView>
    </Modal>
  );
}

function Missing({ onClose }: { onClose: () => void }) {
  return (
    <>
      <Text variant="body" color={colors.textSecondary} style={{ marginBottom: spacing.lg }}>
        This record isn't loaded yet — pull to refresh and try again.
      </Text>
      <Button compact variant="secondary" label="Close" onPress={onClose} />
    </>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, justifyContent: 'flex-end' },
  backdrop: {
    position: 'absolute',
    top: 0, left: 0, right: 0, bottom: 0,
    backgroundColor: colors.overlayDark,
  },
  sheet: {
    backgroundColor: colors.background,
    borderTopLeftRadius: radius.xl,
    borderTopRightRadius: radius.xl,
    padding: spacing.xxl,
    maxHeight: '88%',
  },
  handle: {
    width: 36,
    height: 4,
    borderRadius: 2,
    backgroundColor: colors.cream.line,
    alignSelf: 'center',
    marginBottom: spacing.lg,
  },
  subtitle: { marginBottom: spacing.lg },
});
