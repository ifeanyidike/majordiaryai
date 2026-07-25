import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import React, { useEffect, useState } from 'react';
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Modal,
  Platform,
  Pressable,
  StyleSheet,
  Switch,
  TextInput,
  View,
} from 'react-native';
import {
  Button,
  EmptyState,
  ErrorBanner,
  Header,
  InputModal,
  Screen,
  Text,
  useToast,
} from '@/components';
import { HeatCheckForm, PregnancyCheckForm } from '@/components/CowActionsSheet';
import { colors, radius, shadows, spacing, status as statusColors, typography } from '@/theme';
import { TaskKind, TechTask } from '@/data/types';
import { api } from '@/lib/api';
import { openDirections as openMapsDirections } from '@/lib/maps';
import { cowById, farmById, useAppStore } from '@/store/useAppStore';

const TASK_ICONS: Record<TaskKind, keyof typeof Ionicons.glyphMap> = {
  heat: 'flame',
  needling: 'fitness',
  preg: 'medkit',
  calving: 'heart',
  insemination: 'flask',
  vaccination: 'shield-checkmark',
  other: 'clipboard',
};

// Single-tap action per task kind — opens the recording form directly.
const TASK_ACTION: Record<TaskKind, string> = {
  heat: 'Record Heat',
  needling: 'Log Needling',
  preg: 'Preg Check',
  calving: 'Record Calving',
  insemination: 'Inseminate',
  vaccination: 'Vaccinate',
  other: 'Mark Done',
};

export default function TasksScreen() {
  const router = useRouter();
  const toast = useToast();
  const state = useAppStore();
  const {
    tasks, tasksLoading, tasksError, demoMode,
    fetchTasks, fetchCows, setTaskStatus, addTaskNote,
  } = state;
  const [noteTask, setNoteTask] = useState<TechTask | null>(null);
  const [heatTask, setHeatTask] = useState<TechTask | null>(null);
  const [pregTask, setPregTask] = useState<TechTask | null>(null);
  const [needlingTask, setNeedlingTask] = useState<TechTask | null>(null);

  useEffect(() => {
    fetchCows();
    fetchTasks();
  }, []);

  const recordTask = (task: TechTask) => {
    switch (task.kind) {
      case 'needling':
        if (demoMode) { setTaskStatus(task.id, 'done'); return; }
        setNeedlingTask(task);
        return;
      case 'heat':
        if (demoMode) { setTaskStatus(task.id, 'done'); return; }
        setHeatTask(task);
        return;
      case 'preg':
        if (demoMode) { setTaskStatus(task.id, 'done'); return; }
        setPregTask(task);
        return;
      case 'calving':
      case 'insemination':
      case 'vaccination':
        // These are recorded on the cow profile with the full form.
        if (task.cowId) {
          router.push({ pathname: '/cow/[id]', params: { id: task.cowId } });
        }
        return;
      default:
        setTaskStatus(task.id, 'done');
    }
  };

  const afterRecord = (task: TechTask) => {
    setTaskStatus(task.id, 'done');
    fetchCows();
    fetchTasks();
  };

  const done = tasks.filter((t) => t.status === 'done').length;
  const pct = tasks.length === 0 ? 0 : Math.round((done / tasks.length) * 100);

  const openDirections = (farmId: string) => {
    const farm = farmById(state, farmId);
    if (!farm) return;
    openMapsDirections(`${farm.address}, ${farm.city}, ${farm.province}`);
  };

  const heatCow = heatTask?.cowId ? cowById(state, heatTask.cowId) : undefined;
  const pregCow = pregTask?.cowId ? cowById(state, pregTask.cowId) : undefined;

  return (
    <Screen refreshing={tasksLoading && tasks.length > 0} onRefresh={fetchTasks}>
      <Header
        title="To Do List"
        subtitle="Today's schedule"
        right={
          <View style={styles.progressBadge}>
            <Text variant="label" color={pct === 100 ? statusColors.pregnant.fg : colors.primary}>
              {pct}%
            </Text>
          </View>
        }
      />

      {/* slim progress rail */}
      <View style={styles.progressTrack}>
        <View style={[styles.progressFill, { width: `${pct}%` }]} />
      </View>

      {tasksError ? <ErrorBanner message={tasksError} onRetry={fetchTasks} /> : null}

      {/* Timeline */}
      {tasksLoading && tasks.length === 0 ? (
        <ActivityIndicator color={colors.primary} style={{ marginTop: spacing.xxl }} />
      ) : !tasksError && tasks.length === 0 ? (
        <EmptyState title="No tasks today" message="All clear — check back tomorrow." />
      ) : null}
      <View style={styles.timeline}>
        {tasks.map((task, i) => {
          const farm = farmById(state, task.farmId);
          const isDone = task.status === 'done';
          const dotColor = isDone ? statusColors.pregnant.fg : colors.textMuted;

          return (
            <View
              key={task.id}
              style={styles.timelineRow}
            >
              {/* time + rail */}
              <View style={styles.rail}>
                <Text variant="label" color={isDone ? colors.textMuted : colors.textSecondary}>
                  {task.time.replace(' ', '\n')}
                </Text>
                <View style={[styles.dot, { borderColor: dotColor }, isDone && { backgroundColor: dotColor }]}>
                  {isDone ? <Ionicons name="checkmark" size={10} color={colors.cream.base} /> : null}
                </View>
                {i < tasks.length - 1 && <View style={styles.railLine} />}
              </View>

              {/* task card */}
              <View style={[styles.taskCard, isDone && styles.taskCardDone]}>
                <View style={styles.taskTop}>
                  <Ionicons
                    name={TASK_ICONS[task.kind] ?? 'clipboard'}
                    size={20}
                    color={isDone ? statusColors.pregnant.fg : colors.primary}
                  />
                  <View style={styles.taskInfo}>
                    <Text variant="subheading" style={isDone ? styles.strikethrough : undefined} numberOfLines={2}>
                      {task.title}
                    </Text>
                    <Text variant="caption" color={colors.textSecondary} numberOfLines={1}>
                      {farm?.name ?? 'Unknown farm'}
                      {task.kind === 'needling' && task.isFinalDay ? ' · Final day — inseminate' : ''}
                    </Text>
                  </View>
                </View>

                {task.note ? (
                  <View style={styles.noteBox}>
                    <Ionicons name="document-text-outline" size={14} color={colors.textSecondary} />
                    <Text variant="caption" color={colors.textSecondary} style={styles.noteText}>
                      {task.note}
                    </Text>
                  </View>
                ) : null}

                <View style={styles.actionsRow}>
                  {isDone ? (
                    <View style={styles.doneChip}>
                      <Ionicons name="checkmark-circle" size={16} color={statusColors.pregnant.fg} />
                      <Text variant="caption" color={statusColors.pregnant.fg}>Recorded</Text>
                    </View>
                  ) : (
                    <Button
                      compact
                      label={TASK_ACTION[task.kind] ?? 'Record'}
                      icon="create"
                      onPress={() => recordTask(task)}
                      style={styles.actionBtn}
                    />
                  )}
                  <Pressable
                    style={styles.iconAction}
                    onPress={() => setNoteTask(task)}
                    accessibilityRole="button"
                    accessibilityLabel={`Add note to ${task.title}`}
                  >
                    <Ionicons name="create-outline" size={17} color={colors.textSecondary} />
                    <Text variant="caption" color={colors.textSecondary}>
                      Note
                    </Text>
                  </Pressable>
                  <Pressable
                    style={styles.iconAction}
                    onPress={() => openDirections(task.farmId)}
                    accessibilityRole="button"
                    accessibilityLabel="Get directions to farm"
                  >
                    <Ionicons name="navigate-outline" size={17} color={colors.textSecondary} />
                    <Text variant="caption" color={colors.textSecondary}>
                      Directions
                    </Text>
                  </Pressable>
                </View>
              </View>
            </View>
          );
        })}
      </View>

      {/* Heat check — full doc-required form */}
      <TaskFormSheet
        visible={!!heatTask}
        title="Record Heat Check"
        subtitle={heatTask?.title}
        onClose={() => setHeatTask(null)}
      >
        {heatTask && heatCow ? (
          <HeatCheckForm
            cow={heatCow}
            onCancel={() => setHeatTask(null)}
            onComplete={() => {
              afterRecord(heatTask);
              setHeatTask(null);
            }}
          />
        ) : (
          <MissingCowNotice onClose={() => setHeatTask(null)} />
        )}
      </TaskFormSheet>

      {/* Pregnancy check — full doc-required form */}
      <TaskFormSheet
        visible={!!pregTask}
        title="Record Pregnancy Check"
        subtitle={pregTask?.title}
        onClose={() => setPregTask(null)}
      >
        {pregTask && pregCow ? (
          <PregnancyCheckForm
            cow={pregCow}
            onCancel={() => setPregTask(null)}
            onComplete={() => {
              afterRecord(pregTask);
              setPregTask(null);
            }}
          />
        ) : (
          <MissingCowNotice onClose={() => setPregTask(null)} />
        )}
      </TaskFormSheet>

      {/* Needling completion with bleeding event */}
      <TaskFormSheet
        visible={!!needlingTask}
        title="Complete Needling"
        subtitle={needlingTask?.title}
        onClose={() => setNeedlingTask(null)}
      >
        {needlingTask ? (
          <NeedlingCompleteForm
            task={needlingTask}
            onCancel={() => setNeedlingTask(null)}
            onComplete={(bled) => {
              afterRecord(needlingTask);
              setNeedlingTask(null);
              if (needlingTask.isFinalDay && !bled && needlingTask.cowId) {
                toast.show('Final protocol day — record the AI now', 'flask', 'success');
                router.push({ pathname: '/cow/[id]', params: { id: needlingTask.cowId } });
              }
            }}
          />
        ) : null}
      </TaskFormSheet>

      {/* Add note modal */}
      <InputModal
        visible={!!noteTask}
        title="Add Note"
        placeholder="Write your note…"
        submitLabel="Save Note"
        initialValue={noteTask?.note ?? ''}
        onClose={() => setNoteTask(null)}
        onSubmit={(text) => {
          if (noteTask) {
            addTaskNote(noteTask.id, text);
            toast.show('Note saved', 'document-text');
          }
          setNoteTask(null);
        }}
      />
    </Screen>
  );
}

/** Bottom sheet wrapper for the task forms — backdrop tap dismisses. */
function TaskFormSheet({
  visible, title, subtitle, onClose, children,
}: {
  visible: boolean;
  title: string;
  subtitle?: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        style={styles.sheetRoot}
      >
        <Pressable
          style={styles.sheetBackdrop}
          onPress={onClose}
          accessibilityRole="button"
          accessibilityLabel="Dismiss"
        />
        <View style={styles.sheet}>
          <View style={styles.sheetHandle} />
          <Text variant="heading">{title}</Text>
          {subtitle ? (
            <Text variant="caption" color={colors.textSecondary} style={{ marginBottom: spacing.lg }}>
              {subtitle}
            </Text>
          ) : null}
          {children}
        </View>
      </KeyboardAvoidingView>
    </Modal>
  );
}

function MissingCowNotice({ onClose }: { onClose: () => void }) {
  return (
    <>
      <Text variant="body" color={colors.textSecondary} style={{ marginBottom: spacing.lg }}>
        This cow isn't loaded yet — pull to refresh the herd and try again.
      </Text>
      <Button compact variant="secondary" label="Close" onPress={onClose} />
    </>
  );
}

/** Needling record completion: injection done + bleeding event + notes (per spec). */
function NeedlingCompleteForm({
  task, onCancel, onComplete,
}: {
  task: TechTask;
  onCancel: () => void;
  onComplete: (bleeding: boolean) => void;
}) {
  const toast = useToast();
  const [bleeding, setBleeding] = useState(false);
  const [notes, setNotes] = useState('');
  const [loading, setLoading] = useState(false);

  const submit = async () => {
    const recordId = task.id.slice('needling-'.length);
    setLoading(true);
    try {
      await api.patch(`/needling/records/${recordId}/complete`, {
        bleeding_event: bleeding,
        notes: notes.trim() || null,
      });
      toast.show(
        bleeding
          ? 'Bleeding recorded — cow moves to Open and restarts on Ovsynch'
          : 'Needling step completed',
        bleeding ? 'water' : 'checkmark-circle',
        'success',
      );
      onComplete(bleeding);
    } catch (e: any) {
      toast.error(e?.message ?? 'Failed to complete needling step');
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <View style={styles.toggleRow}>
        <Text variant="body">Bleeding event?</Text>
        <Switch
          value={bleeding}
          onValueChange={setBleeding}
          trackColor={{ false: colors.cream.line, true: colors.primary }}
          thumbColor={colors.cream.base}
          accessibilityLabel="Bleeding event"
        />
      </View>
      {bleeding && (
        <Text variant="caption" color={colors.textSecondary} style={{ marginBottom: spacing.md }}>
          Bleeding before insemination sends the cow to Open and transfers her to the Ovsynch
          program.
        </Text>
      )}
      <TextInput
        style={styles.noteInput}
        value={notes}
        onChangeText={setNotes}
        placeholder="Notes — side effects, behavior… (optional)"
        placeholderTextColor={colors.textMuted}
        multiline
      />
      <View style={styles.modalActions}>
        <Button compact variant="secondary" label="Cancel" onPress={onCancel} style={styles.actionBtn} />
        <Button
          compact
          label="Mark Completed"
          icon="checkmark"
          onPress={submit}
          loading={loading}
          style={styles.actionBtn}
        />
      </View>
    </>
  );
}

const styles = StyleSheet.create({
  progressBadge: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: radius.pill,
    backgroundColor: colors.primarySoft,
  },
  progressTrack: {
    height: 6,
    borderRadius: 3,
    backgroundColor: colors.cream.mist,
    overflow: 'hidden',
    marginBottom: spacing.xxl,
  },
  progressFill: { height: '100%', borderRadius: 3, backgroundColor: colors.primary },
  timeline: { gap: 0 },
  timelineRow: {
    flexDirection: 'row',
    gap: spacing.md,
    paddingBottom: spacing.lg,
  },
  rail: {
    width: 52,
    alignItems: 'center',
    gap: spacing.xs,
  },
  dot: {
    width: 18,
    height: 18,
    borderRadius: 9,
    borderWidth: 2.5,
    backgroundColor: colors.background,
    alignItems: 'center',
    justifyContent: 'center',
  },
  railLine: {
    flex: 1,
    width: 2,
    borderRadius: 1,
    backgroundColor: colors.cream.line,
  },
  taskCard: {
    flex: 1,
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.lg,
    gap: spacing.md,
    ...shadows.card,
  },
  taskCardDone: { opacity: 0.72 },
  strikethrough: { textDecorationLine: 'line-through' },
  taskTop: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  taskInfo: { flex: 1, gap: 1 },
  doneChip: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
  },
  noteBox: {
    flexDirection: 'row',
    gap: spacing.sm,
    backgroundColor: colors.surfaceSoft,
    borderRadius: radius.sm,
    padding: spacing.md,
    alignItems: 'flex-start',
  },
  noteText: { flex: 1 },
  actionsRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  actionBtn: { flex: 1 },
  iconAction: {
    alignItems: 'center',
    justifyContent: 'center',
    gap: 2,
    minWidth: 44,
    minHeight: 44,
    paddingHorizontal: spacing.sm,
  },
  toggleRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: spacing.sm,
    marginBottom: spacing.sm,
  },
  noteInput: {
    ...typography.input,
    color: colors.text,
    backgroundColor: colors.surfaceSoft,
    borderRadius: radius.sm,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.md,
    minHeight: 80,
    textAlignVertical: 'top',
    marginBottom: spacing.md,
  },
  sheetRoot: {
    flex: 1,
    justifyContent: 'flex-end',
  },
  sheetBackdrop: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: colors.overlayDark,
  },
  sheet: {
    backgroundColor: colors.background,
    borderTopLeftRadius: radius.xl,
    borderTopRightRadius: radius.xl,
    padding: spacing.xxl,
    paddingBottom: spacing.huge,
    maxHeight: '88%',
  },
  sheetHandle: {
    width: 36,
    height: 4,
    borderRadius: 2,
    backgroundColor: colors.cream.line,
    alignSelf: 'center',
    marginBottom: spacing.lg,
  },
  modalActions: { flexDirection: 'row', gap: spacing.md },
});
