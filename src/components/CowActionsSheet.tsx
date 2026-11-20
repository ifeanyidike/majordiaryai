import { Ionicons } from '@expo/vector-icons';
import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  KeyboardAvoidingView,
  Modal,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  TextInput,
  View,
} from 'react-native';
import { Button, ModalToastHost, SegmentedControl, SectionHeader, Text, useToast } from '@/components';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { FormInput, FormLabel } from './FormField';
import { SharedTagQuestion } from './SharedTagQuestion';
import { YesNoField } from './YesNoField';
import { HEAT_WINDOW, MIN_DAYS_POST_CALVING_TO_BREED } from '@/data/reports';
import { api, ApiError, isApiConfigured, errorMessage } from '@/lib/api';
import { saveOutcome } from '@/lib/outbox';
import {
  daysBetween, daysSince, isValidPastOrTodayDate, isValidStartDate, START_DATE_LOOKAHEAD_DAYS,
  todayISO,
} from '@/lib/dates';
import { isPreferredStartDay, nextStartDay, PROTOCOLS, protocolByValue } from '@/data/protocols';
import { Role as UserRole, useAuthStore, useRole } from '@/store/useAuthStore';
import { colors, radius, shadows, spacing, typography } from '@/theme';
import { Cow, CowStatus } from '@/data/types';
import { herdIdLabel, useAppStore } from '@/store/useAppStore';

// ── helpers ──────────────────────────────────────────────────

function nowTime(): string {
  const d = new Date();
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

const isValidTime = (t: string) => /^([01]\d|2[0-3]):[0-5]\d$/.test(t);

function daysPostInsemination(cow: { lastInseminationDate?: string }): number | null {
  if (!cow.lastInseminationDate) return null;
  return daysSince(cow.lastInseminationDate);
}

/**
 * Her day in milk when it is under the 60 days she would normally be bred at,
 * else null. The server decides who goes on Today's Breed Report; this is only
 * for the "Are you sure?" when she is enrolled by hand this early.
 */
function earlyBreedingDay(cow: { status: CowStatus; lastCalvingDate?: string }): number | null {
  if (cow.status !== 'fresh' || !cow.lastCalvingDate) return null;
  const dim = daysSince(cow.lastCalvingDate);
  return dim < MIN_DAYS_POST_CALVING_TO_BREED ? dim : null;
}

function useTechnicianName(): string {
  const user = useAuthStore((s) => s.user);
  return user?.name ?? '';
}

/** Demo builds can't record events — surface that honestly instead of failing. */
function guardApi(showError: (m: string) => void): boolean {
  if (!isApiConfigured) {
    showError('Demo mode — connect the API to record events.');
    return false;
  }
  return true;
}

// ── action list based on status ──────────────────────────────

type ActionKey =
  | 'health'
  | 'enroll'
  | 'program'
  | 'inseminate'
  | 'heat_check'
  | 'seen_heat'
  | 'pregnancy_check'
  | 'calving'
  | 'vaccinate'
  | 'cull'
  | 'mark_sold'
  | 'mark_dead';

interface ActionDef {
  key: ActionKey;
  label: string;
  icon: keyof typeof Ionicons.glyphMap;
  danger?: boolean;
}

const ACTION_DEFS: Record<ActionKey, ActionDef> = {
  health:           { key: 'health',           label: 'Health Check',    icon: 'pulse' },
  enroll:           { key: 'enroll',           label: 'Enroll Protocol', icon: 'list' },
  program:          { key: 'program',          label: 'Insemination Program', icon: 'git-branch' },
  inseminate:       { key: 'inseminate',       label: 'Record AI',       icon: 'flask' },
  heat_check:       { key: 'heat_check',       label: 'Heat Check',      icon: 'flame' },
  seen_heat:        { key: 'seen_heat',        label: 'Seen in Heat',    icon: 'flame' },
  pregnancy_check:  { key: 'pregnancy_check',  label: 'Preg Check',      icon: 'medkit' },
  calving:          { key: 'calving',          label: 'Record Calving',  icon: 'heart' },
  vaccinate:        { key: 'vaccinate',        label: 'Vaccinate',       icon: 'shield-checkmark' },
  cull:             { key: 'cull',             label: 'Mark Cull',       icon: 'trash', danger: true },
  mark_sold:        { key: 'mark_sold',        label: 'Mark Sold',       icon: 'cash', danger: true },
  mark_dead:        { key: 'mark_dead',        label: 'Mark Dead',       icon: 'close-circle', danger: true },
};

/**
 * Actions only certain roles may perform. Must mirror the backend's
 * `require_roles` (and report_catalog's WORK_ROLES/PREGNANCY_ROLES) — offering
 * an action the API rejects with a 403 is worse than not offering it: a vet
 * once filled in a whole insemination form only to be refused on submit.
 *
 * Everything is admin+technician except pregnancy checks, which vets share.
 * A `farm` user records nothing, which is why they see no action buttons.
 */
const WORK_ROLES: UserRole[] = ['admin', 'technician'];
const ROLE_RESTRICTED: Record<ActionKey, UserRole[]> = {
  // POST /cows/{id}/health accepts vets too — they assess a cow's condition.
  health: ['admin', 'technician', 'vet'],
  enroll: WORK_ROLES,
  program: WORK_ROLES,
  inseminate: WORK_ROLES,
  heat_check: WORK_ROLES,
  seen_heat: WORK_ROLES,
  pregnancy_check: ['admin', 'technician', 'vet'],
  calving: WORK_ROLES,
  vaccinate: WORK_ROLES,
  cull: WORK_ROLES,
  mark_sold: WORK_ROLES,
  mark_dead: WORK_ROLES,
};

function getActions(cow: RecordTarget, role: UserRole): ActionKey[] {
  const keys: ActionKey[] = [];
  const days = daysPostInsemination(cow);
  const dim = cow.lastCalvingDate ? daysSince(cow.lastCalvingDate) : null;

  switch (cow.status) {
    case 'heifer':
    case 'open':
      keys.push('enroll', 'inseminate', 'seen_heat');
      if (cow.currentProgram !== 'Insemination') keys.push('program');
      break;
    case 'needling':
      // TAI happens on the protocol's final day (Timed Breeding task);
      // recording here covers heat-observed protocols too.
      keys.push('inseminate', 'seen_heat');
      break;
    case 'inseminated':
      // Inside the Heat Report's days there is also the scheduled Yes/No
      // check. Seen in heat is offered on any day (Josh's change requests,
      // Nov 20): she then goes on today's breed report, to be bred that day.
      if (days !== null && days >= HEAT_WINDOW[0] && days <= HEAT_WINDOW[1]) keys.push('heat_check');
      keys.push('seen_heat');
      if (days !== null && days >= 30) keys.push('pregnancy_check');
      break;
    case 'fresh':
      keys.push('seen_heat');
      // The old day-283 rule made a dry cow Fresh on her due date without a
      // recorded calving. Until someone records the real one her lactation is
      // one short and her calf does not exist — so the calving stays on offer,
      // and she stays Fresh for it. Any other Fresh cow can be enrolled by hand,
      // before day 70 (Josh's test results, Nov 5).
      if (cow.calvingAssumed) keys.push('calving');
      else keys.push('enroll', 'program');
      // Vaccination window: 30–50 days post calving
      if (dim !== null && dim >= 30) keys.push('vaccinate');
      break;
    case 'pregnant':
    case 'dry':
      // Josh, Oct 2: a cow in heat is bred "no matter conditions" -- a heat
      // means the pregnancy failed, and the server opens her again.
      keys.push('calving', 'seen_heat');
      break;
    case 'dnb':
      // Not to be bred, but a heat is still worth writing down.
      keys.push('seen_heat');
      break;
    case 'cull':
      keys.push('mark_sold', 'mark_dead');
      break;
  }

  // Health can be recorded on any live animal, by any clinical role.
  if (!['cull', 'sold', 'dead'].includes(cow.status)) keys.push('health', 'cull');
  // A cow marked Do Not Breed is not offered a protocol, the program or an
  // AI — the API refuses all three. A heat can still be recorded: it tells you
  // she isn't pregnant, and the app says she isn't to be bred.
  return keys
    .filter((k) => !(cow.doNotBreed && (k === 'enroll' || k === 'program' || k === 'inseminate')))
    .filter((k) => ROLE_RESTRICTED[k].includes(role));
}

// Form primitives are shared with the full-screen forms (FormField.tsx).

function DateTimeFields({
  date, time, onDate, onTime, dateLabel = 'Date',
}: {
  date: string; time: string;
  onDate: (v: string) => void; onTime: (v: string) => void;
  dateLabel?: string;
}) {
  const dateBad = date.length > 0 && !isValidPastOrTodayDate(date);
  const timeBad = time.length > 0 && !isValidTime(time);
  return (
    <View style={styles.dateTimeRow}>
      <View style={styles.flex2}>
        <FormLabel>{dateLabel}</FormLabel>
        <FormInput
          value={date}
          onChangeText={onDate}
          placeholder="YYYY-MM-DD"
          keyboardType="numbers-and-punctuation"
          error={dateBad}
        />
        {dateBad && (
          <Text variant="caption" color={colors.danger} style={styles.fieldError}>
            Use YYYY-MM-DD, today or earlier
          </Text>
        )}
      </View>
      <View style={styles.flex1}>
        <FormLabel>Time</FormLabel>
        <FormInput
          value={time}
          onChangeText={onTime}
          placeholder="HH:MM"
          keyboardType="numbers-and-punctuation"
          error={timeBad}
        />
      </View>
    </View>
  );
}

function TechnicianRow() {
  const name = useTechnicianName();
  if (!name) return null;
  return (
    <View style={styles.techRow}>
      <Ionicons name="person-circle-outline" size={18} color={colors.textSecondary} />
      <Text variant="caption" color={colors.textSecondary}>
        Recorded by {name}
      </Text>
    </View>
  );
}

function FormActions({
  onCancel, submitLabel, submitIcon, onSubmit, loading, disabled, danger,
}: {
  onCancel: () => void;
  submitLabel: string;
  submitIcon?: keyof typeof Ionicons.glyphMap;
  onSubmit: () => void;
  loading: boolean;
  disabled?: boolean;
  danger?: boolean;
}) {
  return (
    <View style={styles.modalActions}>
      <Button compact variant="secondary" label="Cancel" onPress={onCancel} style={styles.flex1} />
      <Button
        compact
        variant={danger ? 'danger' : 'primary'}
        label={submitLabel}
        icon={submitIcon}
        onPress={onSubmit}
        loading={loading}
        disabled={disabled}
        style={styles.flex1}
      />
    </View>
  );
}

// ── individual modal forms ────────────────────────────────────

/**
 * The subset of a cow a recording form actually needs. `Cow` satisfies it
 * structurally, and so does a work-list row — which lets a report row open its
 * form without a second fetch for the full cow record.
 */
export interface RecordTarget {
  id: string;
  /** Fresh by the old day-283 rule, calving not yet recorded. */
  calvingAssumed?: boolean;
  /** How to name her to a person — her name, her tag, or both. Always set. */
  label: string;
  earTag?: string;
  herdId?: string;
  status: CowStatus;
  currentProgram?: string;
  /**
   * Which farm's bull list to offer.
   *
   * The insemination form used to look this up from the cows already in the
   * store. Opened from a work-list row that farm's cows may never have been
   * fetched, so the lookup missed, the bull picker silently rendered nothing,
   * and the technician had to type a sire from memory with no bull_id
   * recorded. Work-list rows carry their own farmId, so it is passed in.
   */
  farmId?: string;
  lastInseminationId?: string;
  lastInseminationDate?: string;
  lastCalvingDate?: string;
  healthStatus?: Cow['healthStatus'];
  /** On the Do Not Breed list: offered no route to a breeding (Josh, Oct 2/4). */
  doNotBreed?: boolean;
}

interface FormProps {
  cow: RecordTarget;
  onCancel: () => void;
  onComplete: () => void;
}

export function InseminationForm({
  cow, onCancel, onComplete, banner, bannerIcon = 'fitness', withFinalInjection = false,
  seenInHeat = false,
}: FormProps & {
  banner?: string;
  bannerIcon?: keyof typeof Ionicons.glyphMap;
  /** Final protocol day: the last shot is recorded with this AI. */
  withFinalInjection?: boolean;
  /** Just answered "In heat": she is being bred, so bleeding is not asked. */
  seenInHeat?: boolean;
  finalNeedlingRecordId?: string;
}) {
  // Bleeding replaces the insemination for a cow still in a protocol. It is
  // offered whenever she is mid-protocol — NOT only when a completable record
  // happens to exist, because after the final shot there is none left and that
  // is exactly when she is closest to insemination.
  const canBleed = cow.status === 'needling' && !seenInHeat;
  const toast = useToast();
  const { bulls, fetchBulls, saveBull, cows } = useAppStore();
  // The row carries its own farm; fall back to the store only for callers
  // that pass a full Cow (the profile screen) rather than a work-list row.
  const farmId = cow.farmId ?? cows.find((c) => c.id === cow.id)?.farmId;
  const farmBulls = (farmId ? bulls[farmId] : undefined) ?? [];
  useEffect(() => {
    if (farmId) fetchBulls(farmId);
  }, [farmId]);
  // Bleeding can be recorded on ANY protocol day, including the final one.
  // Bleeding means no insemination: the cow goes Open and restarts on Ovsynch.
  // Asked, not defaulted (Josh, Oct 4: no toggles -- every question answered).
  const [bleeding, setBleeding] = useState<boolean | null>(canBleed ? null : false);
  const [date, setDate] = useState(todayISO());
  const [time, setTime] = useState(nowTime());
  const [bull, setBull] = useState('');
  // Josh, Oct 4: the bull is picked from the farm's bull list, and required.
  // Free text is gone, so the same bull is spelled the same way every time;
  // a straw that isn't listed yet is added to the list right here, so it
  // never blocks the visit.
  const [bullId, setBullId] = useState<string | undefined>();
  const [newBull, setNewBull] = useState('');
  const [addingBull, setAddingBull] = useState(false);
  const [doseId, setDoseId] = useState('');
  const [inseminationCode, setInseminationCode] = useState('');
  const [semenType, setSemenType] = useState<'sexed' | 'conventional' | 'beef' | null>(null);
  const [notes, setNotes] = useState('');
  const [loading, setLoading] = useState(false);

  // When bleeding is recorded there is no AI, so the AI fields aren't required.
  const valid = bleeding === null
    ? false
    : bleeding && canBleed
      ? true
      : isValidPastOrTodayDate(date) && isValidTime(time) && !!bullId && semenType !== null;

  const addBull = async () => {
    const name = newBull.trim();
    if (!name || !farmId) return;
    if (!guardApi(toast.error)) return;
    setAddingBull(true);
    try {
      await saveBull(farmId, { name, semenType: semenType ?? undefined });
      const added = (useAppStore.getState().bulls[farmId] ?? [])
        .find((b) => b.name.toLowerCase() === name.toLowerCase());
      if (added) {
        setBullId(added.id);
        setBull(added.name);
      }
      setNewBull('');
    } catch (e: any) {
      toast.error(errorMessage(e, 'Could not add the bull'));
    } finally {
      setAddingBull(false);
    }
  };

  const submit = async () => {
    if (!guardApi(toast.error)) return;
    setLoading(true);
    try {
      // Bleeding: record the event instead of an AI. Goes to the cow-level
      // endpoint, which works whether or not a scheduled record is still open —
      // the backend cancels the enrollment and re-enrolls her on Ovsynch.
      if (bleeding && canBleed) {
        if ((await record(cow, 'Bleeding', `/needling/cow/${cow.id}/bleeding`, {
          notes: notes.trim() || null,
        }, 'POST')).queued) return queuedDone(onComplete);
        toast.show(
          `Bleeding recorded — ${cow.label} moves to Open and restarts on Ovsynch`,
          'water',
          'success',
        );
        onComplete();
        return;
      }

      // Final-day combined task: the API completes the pending final needling
      // record in the same transaction as the AI, so there is no second write
      // to orchestrate (and no partial-failure window) from the client.
      // Backend takes a single datetime; technician comes from the auth token.
      if ((await record(cow, 'Insemination', '/inseminations/', {
        cow_id: cow.id,
        date: `${date}T${time}:00`,
        bull_name: bull.trim(),
        bull_id: bullId ?? null,
        dose_id: doseId.trim() || null,
        insemination_code: inseminationCode.trim() || null,
        semen_type: semenType,
        notes: notes.trim() || null,
      }, 'POST')).queued) return queuedDone(onComplete);
      toast.success(
        withFinalInjection
          ? `Final injection + AI recorded — ${cow.label} is now Inseminated`
          : `AI recorded — ${cow.label} is now Inseminated`,
      );
      onComplete();
    } catch (e: any) {
      toast.error(errorMessage(e, 'Failed to record insemination'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      {banner ? (
        <View style={styles.combinedBanner}>
          <Ionicons name={bannerIcon} size={18} color={colors.primary} />
          <Text variant="caption" color={colors.text} style={styles.flex1}>
            {banner}
          </Text>
        </View>
      ) : null}

      {/* Bleeding is recordable on any protocol day — including the final one,
          where it replaces the insemination. */}
      {canBleed ? (
        <>
          <YesNoField label="Bleeding event?" value={bleeding} onChange={setBleeding} />
          {bleeding && (
            <Text variant="caption" color={colors.textSecondary} style={styles.fieldHint}>
              No insemination will be recorded. She moves to Open and restarts on Ovsynch.
            </Text>
          )}
        </>
      ) : null}

      {bleeding === false && (
        <>
          <DateTimeFields date={date} time={time} onDate={setDate} onTime={setTime} dateLabel="Insemination Date" />
          <FormLabel>Bull Name</FormLabel>
          {farmBulls.length === 0 && (
            <Text variant="caption" color={colors.textSecondary} style={styles.fieldHint}>
              This farm has no bulls listed yet. Add the one you used below.
            </Text>
          )}
          {farmBulls.length > 0 && (
            <View style={styles.bullRow}>
              {farmBulls.map((b) => {
                const on = bullId === b.id;
                return (
                  <Pressable
                    key={b.id}
                    onPress={() => {
                      // Picking fills the name too, so what is stored matches
                      // what the technician saw.
                      setBullId(on ? undefined : b.id);
                      setBull(on ? '' : b.name);
                      if (!on && b.semenType) setSemenType(b.semenType);
                    }}
                    style={[styles.bullChip, on && styles.bullChipOn]}
                    accessibilityRole="button"
                    accessibilityState={{ selected: on }}
                  >
                    <Text variant="caption" color={on ? colors.primary : colors.textSecondary}>
                      {b.name}{b.code ? ` · ${b.code}` : ''}
                    </Text>
                  </Pressable>
                );
              })}
            </View>
          )}
          <View style={styles.addBullRow}>
            <View style={styles.flex1}>
              <FormInput
                value={newBull}
                onChangeText={setNewBull}
                placeholder={farmBulls.length ? 'Not listed? Add a bull' : 'Bull name'}
              />
            </View>
            <Button
              compact
              variant="secondary"
              label="Add"
              icon="add"
              onPress={addBull}
              loading={addingBull}
              disabled={!newBull.trim() || !farmId}
            />
          </View>
          <FormLabel>Semen Type</FormLabel>
          <SegmentedControl
            options={[
              { value: 'sexed', label: 'Sexed' },
              { value: 'conventional', label: 'Conventional' },
              { value: 'beef', label: 'Beef' },
            ]}
            value={semenType}
            onChange={setSemenType}
            style={styles.fieldGap}
          />
          <FormLabel>Dose ID</FormLabel>
          <FormInput value={doseId} onChangeText={setDoseId} placeholder="Optional" />
          <FormLabel>Insemination Code</FormLabel>
          <FormInput
            value={inseminationCode}
            onChangeText={setInseminationCode}
            placeholder="Optional"
          />
        </>
      )}
      <FormLabel>Notes</FormLabel>
      <FormInput value={notes} onChangeText={setNotes} placeholder="Optional" multiline />
      <TechnicianRow />
      <FormActions
        onCancel={onCancel}
        submitLabel={bleeding ? 'Record Bleeding' : 'Record AI'}
        submitIcon={bleeding ? 'water' : 'flask'}
        onSubmit={submit}
        loading={loading}
        disabled={!valid}
      />
    </>
  );
}

interface HeatResult {
  id: string;
  on_breed_report?: boolean | null;
  not_bred_because?: string | null;
  can_overrule?: boolean | null;
}

/** A heat is saved before the sheet's next step, and that step can be closed
 *  without finishing it, so the reports are told now. */
function refreshReports() {
  useAppStore.getState().fetchWorklist();
}

/** What happened to her, in the words the technician needs next. */
function heatOutcome(cow: RecordTarget, result: HeatResult, checkDate: string): string {
  if (result.on_breed_report) return `${cow.label} is on Today's Breed Report — breed her today`;
  if (result.not_bred_because) {
    // A cow on the list goes to DNB, not Open.
    const next = result.not_bred_because.includes('Do Not Breed') ? '' : ' She goes to Open tomorrow.';
    return `Heat recorded — ${cow.label} is not to be bred (${result.not_bred_because}).${next}`;
  }
  if (checkDate !== todayISO()) return 'Heat recorded — too late for Today\'s Breed Report';
  return 'Heat recorded';
}

/**
 * The farmer may overrule the 60-day rule. Josh's test results, Nov 5: "the
 * farmer overrules and wants it bred ... ask are you sure so we can override".
 * Asked after the heat is saved, because the heat is a fact either way and only
 * the server can say this rule is what stopped her.
 */
function OverruleConfirm({ cow, heat, onDone, onOverruled = onDone }: {
  cow: RecordTarget;
  heat: HeatResult;
  onDone: () => void;
  onOverruled?: () => void;
}) {
  const toast = useToast();
  const [loading, setLoading] = useState(false);

  const overrule = async () => {
    setLoading(true);
    try {
      if ((await record(cow, 'Put on Breed Report', `/checks/heat/${heat.id}/overrule`, {}, 'POST')).queued) return queuedDone(onOverruled);
      toast.show(`${cow.label} is on Today's Breed Report — breed her today`, 'flame', 'success');
      onOverruled();
    } catch (e: any) {
      toast.error(errorMessage(e, 'Could not put her on the report'));
      setLoading(false);
    }
  };

  const leave = () => {
    toast.show(heatOutcome(cow, heat, todayISO()), 'flame', 'success');
    onDone();
  };

  return (
    <>
      <View style={styles.combinedBanner}>
        <Ionicons name="alert-circle" size={18} color={colors.primary} />
        <Text variant="caption" color={colors.text} style={styles.flex1}>
          Heat recorded, but {heat.not_bred_because}, so she is not on Today's Breed Report.
        </Text>
      </View>
      <Text variant="subheading" style={styles.fieldHint}>Are you sure you want her bred?</Text>
      <View style={styles.modalActions}>
        <Button compact variant="secondary" label="No" onPress={leave} style={styles.flex1} />
        <Button
          compact
          label="Yes, Breed Her"
          icon="flame"
          onPress={overrule}
          loading={loading}
          style={styles.flex1}
        />
      </View>
    </>
  );
}

/**
 * The Heat Report's check (Josh, Oct 4): "Heat Detected — Yes / No", both
 * answers required. Yes puts her straight onto Today's Breed Report; No
 * leaves her on the Heat Report as before.
 */
export function HeatCheckForm({ cow, onCancel, onComplete }: FormProps) {
  const toast = useToast();
  const [heatDetected, setHeatDetected] = useState<boolean | null>(null);
  const [bloodOnTail, setBloodOnTail] = useState<boolean | null>(null);
  // Backdatable. The date was hardcoded to today, which contradicts the whole
  // reason the backend keeps a relief technician's access open for a week:
  // work gets written up after the visit, not during it. Recording yesterday's
  // check today also mis-stated the day count the timing rule is judged on.
  const [checkDate, setCheckDate] = useState(todayISO());
  const [notes, setNotes] = useState('');
  const [loading, setLoading] = useState(false);
  const [overrule, setOverrule] = useState<HeatResult | null>(null);
  const days = daysPostInsemination(cow) ?? 0;
  const dateValid = isValidPastOrTodayDate(checkDate);
  const answered = heatDetected !== null && bloodOnTail !== null;

  const submit = async () => {
    if (!cow.lastInseminationId) {
      toast.error('No insemination on record for this cow');
      return;
    }
    if (!guardApi(toast.error)) return;
    setLoading(true);
    try {
      // Blood on the tail means she WAS in heat — the spec treats it as a heat event.
      const effectiveHeat = !!heatDetected || !!bloodOnTail;
      const sent = await record<HeatResult>(cow, 'Heat check', '/checks/heat', {
        cow_id: cow.id,
        insemination_id: cow.lastInseminationId,
        check_date: checkDate,
        heat_detected: effectiveHeat,
        bleeding_event: !!bloodOnTail,
        notes: notes.trim() || null,
      }, 'POST');
      if (sent.queued) return queuedDone(onComplete);
      const result = sent.data!;
      if (result.can_overrule) {
        refreshReports();
        setOverrule(result);
        return;
      }
      toast.show(
        effectiveHeat
          ? heatOutcome(cow, result, checkDate)
          : 'No heat — she stays on the Heat Report; preg check at day 30+',
        effectiveHeat ? 'flame' : 'checkmark-circle',
        'success',
      );
      onComplete();
    } catch (e: any) {
      toast.error(errorMessage(e, 'Failed to record heat check'));
    } finally {
      setLoading(false);
    }
  };

  if (overrule) return <OverruleConfirm cow={cow} heat={overrule} onDone={onComplete} />;

  return (
    <>
      <Text variant="caption" color={colors.textSecondary} style={{ marginBottom: spacing.md }}>
        Day {days} post insemination (heat window: days {HEAT_WINDOW[0]}–{HEAT_WINDOW[1]})
      </Text>
      <FormLabel>Check Date</FormLabel>
      <FormInput
        value={checkDate}
        onChangeText={setCheckDate}
        placeholder="YYYY-MM-DD"
        keyboardType="numbers-and-punctuation"
        error={checkDate.length > 0 && !dateValid}
      />
      {checkDate.length > 0 && !dateValid && (
        <Text variant="caption" color={colors.danger} style={styles.fieldError}>
          Use YYYY-MM-DD, today or earlier
        </Text>
      )}
      <YesNoField label="Heat Detected?" value={heatDetected} onChange={setHeatDetected} />
      <YesNoField label="Blood on Tail?" value={bloodOnTail} onChange={setBloodOnTail} />
      {(heatDetected || bloodOnTail) && (
        <Text variant="caption" color={colors.textSecondary} style={styles.fieldHint}>
          {bloodOnTail && !heatDetected ? 'Blood on the tail means she was in heat. ' : ''}
          She goes straight onto Today's Breed Report — breed her today, or she goes to the
          Open Cow Report tomorrow.
        </Text>
      )}
      <FormLabel>Notes</FormLabel>
      <FormInput value={notes} onChangeText={setNotes} placeholder="Standing heat, mucus, etc. (optional)" multiline />
      <TechnicianRow />
      <FormActions
        onCancel={onCancel}
        submitLabel="Record Check"
        submitIcon="flame"
        onSubmit={submit}
        loading={loading}
        disabled={!dateValid || !answered}
      />
    </>
  );
}

/**
 * A heat seen outside a scheduled check — an open cow, one mid-protocol, a
 * fresh cow, a heifer, or an inseminated cow past her Heat Report days.
 * Josh, Oct 4: Today's Breed Report takes "any cow marked Heat Detected:
 * Yes ... any time a cow is seen in heat, not only inside the Heat Report
 * window". There is nothing to answer "No" to here, so it records the heat.
 */
export function SeenInHeatForm({ cow, onCancel, onComplete }: FormProps) {
  const toast = useToast();
  const [seenOn, setSeenOn] = useState(todayISO());
  const [notes, setNotes] = useState('');
  const [loading, setLoading] = useState(false);
  const [overrule, setOverrule] = useState<HeatResult | null>(null);
  const dateValid = isValidPastOrTodayDate(seenOn);

  const submit = async () => {
    if (!guardApi(toast.error)) return;
    setLoading(true);
    try {
      const sent = await record<HeatResult>(cow, 'Seen in heat', '/checks/heat', {
        cow_id: cow.id,
        // Only an inseminated cow's heat is timed from her insemination.
        insemination_id: cow.status === 'inseminated' ? cow.lastInseminationId ?? null : null,
        check_date: seenOn,
        heat_detected: true,
        bleeding_event: false,
        notes: notes.trim() || null,
      }, 'POST');
      if (sent.queued) return queuedDone(onComplete);
      const result = sent.data!;
      if (result.can_overrule) {
        refreshReports();
        setOverrule(result);
        return;
      }
      toast.show(heatOutcome(cow, result, seenOn), 'flame', 'success');
      onComplete();
    } catch (e: any) {
      toast.error(errorMessage(e, 'Failed to record the heat'));
    } finally {
      setLoading(false);
    }
  };

  if (overrule) return <OverruleConfirm cow={cow} heat={overrule} onDone={onComplete} />;

  return (
    <>
      <Text variant="caption" color={colors.textSecondary} style={{ marginBottom: spacing.md }}>
        Seen today, she goes onto Today's Breed Report and is bred today — unless she is under
        60 days post calving, under 13 months, a cull, or on the Do Not Breed list. Not bred
        today, she goes to the Open Cow Report tomorrow.
        {cow.status === 'pregnant' || cow.status === 'dry'
          ? ' A heat means she is not pregnant: her due and dry dates are cleared.'
          : ''}
      </Text>
      <FormLabel>Date Seen in Heat</FormLabel>
      <FormInput
        value={seenOn}
        onChangeText={setSeenOn}
        placeholder="YYYY-MM-DD"
        keyboardType="numbers-and-punctuation"
        error={seenOn.length > 0 && !dateValid}
      />
      {seenOn.length > 0 && !dateValid && (
        <Text variant="caption" color={colors.danger} style={styles.fieldError}>
          Use YYYY-MM-DD, today or earlier
        </Text>
      )}
      <FormLabel>Notes</FormLabel>
      <FormInput value={notes} onChangeText={setNotes} placeholder="Standing heat, mucus, etc. (optional)" multiline />
      <TechnicianRow />
      <FormActions
        onCancel={onCancel}
        submitLabel="Record Heat"
        submitIcon="flame"
        onSubmit={submit}
        loading={loading}
        disabled={!dateValid}
      />
    </>
  );
}

/**
 * The Prostaglandin Report's check, Days 2 to 5. Josh's test results, Nov 5:
 * in heat, she is inseminated from this report; "if it doesn't go in heat then
 * mark as open status", which the last day's No does.
 *
 * Yes records a heat like any other, so if she is not bred after all she is on
 * Today's Breed Report, and Open tomorrow, as every cow in heat is. No asks about
 * bleeding, which "can be recorded on any day" (Master Structure) and stops the
 * protocol: she goes to Open and restarts on Ovsynch.
 */
export function ProstaglandinCheckForm({ cow, recordId, day, onCancel, onComplete }: FormProps & {
  recordId: string;
  day?: number;
}) {
  const toast = useToast();
  const [inHeat, setInHeat] = useState<boolean | null>(null);
  const [bleeding, setBleeding] = useState<boolean | null>(null);
  const [notes, setNotes] = useState('');
  const [loading, setLoading] = useState(false);
  const [overrule, setOverrule] = useState<HeatResult | null>(null);
  const [breeding, setBreeding] = useState(false);
  const lastDay = protocolByValue('prostaglandin_heat')?.steps.find((s) => s.final)?.day;
  const lastCheck = day === lastDay;

  const submit = async () => {
    if (!guardApi(toast.error)) return;
    setLoading(true);
    try {
      if (!inHeat && bleeding) {
        if ((await record(cow, 'Bleeding', `/needling/cow/${cow.id}/bleeding`, { notes: notes.trim() || null }, 'POST')).queued) return queuedDone(onComplete);
        toast.show('Bleeding recorded — cow moves to Open and restarts on Ovsynch', 'water', 'success');
        onComplete();
        return;
      }
      if (!inHeat) {
        if ((await record(cow, 'Protocol injection', `/needling/records/${recordId}/complete`, {
          bleeding_event: false,
          notes: notes.trim() || null,
        }, 'PATCH')).queued) return queuedDone(onComplete);
        toast.show(
          lastCheck ? `No heat by Day ${day} — ${cow.label} goes to Open` : 'No heat — check her again next time',
          'checkmark-circle',
          'success',
        );
        onComplete();
        return;
      }
      const sent = await record<HeatResult>(cow, 'Heat check', '/checks/heat', {
        cow_id: cow.id,
        insemination_id: null,
        check_date: todayISO(),
        heat_detected: true,
        bleeding_event: false,
        notes: notes.trim() || null,
      }, 'POST');
      if (sent.queued) return queuedDone(onComplete);
      const result = sent.data!;
      if (result.on_breed_report) {
        refreshReports();
        setBreeding(true);
      } else if (result.can_overrule) {
        refreshReports();
        setOverrule(result);
      } else {
        toast.show(heatOutcome(cow, result, todayISO()), 'flame', 'success');
        onComplete();
      }
    } catch (e: any) {
      toast.error(errorMessage(e, 'Failed to record the check'));
    } finally {
      setLoading(false);
    }
  };

  if (breeding) {
    return (
      <InseminationForm
        cow={cow}
        // The heat is saved, so leaving here still has to refresh the report.
        onCancel={onComplete}
        onComplete={onComplete}
        seenInHeat
        bannerIcon="flame"
        banner="In heat. If she isn't bred today, she goes to the Open Cow Report tomorrow."
      />
    );
  }
  if (overrule) {
    return (
      <OverruleConfirm
        cow={cow}
        heat={overrule}
        onDone={onComplete}
        onOverruled={() => {
          setOverrule(null);
          setBreeding(true);
        }}
      />
    );
  }

  return (
    <>
      <Text variant="caption" color={colors.textSecondary} style={{ marginBottom: spacing.md }}>
        Prostaglandin Heat, Day {day} of {lastDay}.
        {lastCheck ? ' Last check: with no heat today she goes to Open.' : ''}
      </Text>
      <YesNoField label="In heat?" value={inHeat} onChange={setInHeat} />
      {inHeat === false ? (
        <YesNoField label="Bleeding event?" value={bleeding} onChange={setBleeding} />
      ) : null}
      <FormLabel>Notes</FormLabel>
      <FormInput value={notes} onChangeText={setNotes} placeholder="Optional" multiline />
      <TechnicianRow />
      <FormActions
        onCancel={onCancel}
        submitLabel={inHeat ? 'Breed Her' : 'Save'}
        submitIcon={inHeat ? 'flame' : 'checkmark'}
        onSubmit={submit}
        loading={loading}
        disabled={inHeat === null || (inHeat === false && bleeding === null)}
      />
    </>
  );
}

export function PregnancyCheckForm({ cow, onCancel, onComplete }: FormProps) {
  const toast = useToast();
  // Nothing pre-picked: a result that defaults to "Pregnant" is a pregnancy
  // nobody diagnosed if the vet saves without looking (Josh, Oct 4).
  const [result, setResult] = useState<'pregnant' | 'not_pregnant' | null>(null);
  const [infection, setInfection] = useState<boolean | null>(null);
  const [infectionName, setInfectionName] = useState('');
  const [cysts, setCysts] = useState<boolean | null>(null);
  // Backdatable — a vet writes up a round of checks after the visit, and the
  // date decides the +283 due date and the +223 dry-off.
  const [checkDate, setCheckDate] = useState(todayISO());
  const [notes, setNotes] = useState('');
  const [loading, setLoading] = useState(false);
  const dateValid = isValidPastOrTodayDate(checkDate);

  const submit = async () => {
    if (!cow.lastInseminationId) {
      toast.error('No insemination on record for this cow');
      return;
    }
    if (!guardApi(toast.error)) return;
    setLoading(true);
    try {
      if ((await record(cow, 'Pregnancy check', '/checks/pregnancy', {
        cow_id: cow.id,
        insemination_id: cow.lastInseminationId,
        check_date: checkDate,
        result,
        has_infection: !!infection,
        infection_detail: infection ? infectionName.trim() || null : null,
        has_cysts: !!cysts,
        notes: notes.trim() || null,
      }, 'POST')).queued) return queuedDone(onComplete);
      // Outcome messaging mirrors the program rules, including cyst/infection branches.
      let msg: string;
      if (cysts) {
        msg = 'Cysts found — cow goes back to Open for needling re-enrollment';
      } else if (result === 'pregnant') {
        msg = 'Confirmed pregnant — due and dry dates set';
      } else if (infection) {
        msg = 'Not pregnant + infection — cow moved to Open program';
      } else {
        msg = 'Not pregnant — cow moved to Open, returns to needling';
      }
      toast.show(msg, 'medkit', 'success');
      onComplete();
    } catch (e: any) {
      toast.error(errorMessage(e, 'Failed to record pregnancy check'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      {/* Josh's test results, Nov 5: "Mark in inner page, the day". Counted to
          the check date, which a vet may set back. */}
      {cow.lastInseminationDate && dateValid ? (
        <Text variant="caption" color={colors.textSecondary} style={{ marginBottom: spacing.md }}>
          Day {daysBetween(cow.lastInseminationDate, checkDate)} post insemination
        </Text>
      ) : null}
      <FormLabel>Check Date</FormLabel>
      <FormInput
        value={checkDate}
        onChangeText={setCheckDate}
        placeholder="YYYY-MM-DD"
        keyboardType="numbers-and-punctuation"
        error={checkDate.length > 0 && !dateValid}
      />
      {checkDate.length > 0 && !dateValid && (
        <Text variant="caption" color={colors.danger} style={styles.fieldError}>
          Use YYYY-MM-DD, today or earlier
        </Text>
      )}
      <FormLabel>Result</FormLabel>
      <SegmentedControl
        options={[
          { value: 'pregnant', label: 'Pregnant' },
          { value: 'not_pregnant', label: 'Not Pregnant' },
        ]}
        value={result}
        onChange={setResult}
        style={styles.fieldGap}
      />
      <YesNoField label="Infection?" value={infection} onChange={setInfection} />
      {infection ? (
        <>
          <FormLabel>Which Infection?</FormLabel>
          <FormInput value={infectionName} onChangeText={setInfectionName} placeholder="Optional" />
        </>
      ) : null}
      <YesNoField label="Cysts?" value={cysts} onChange={setCysts} />
      {cysts && (
        <Text variant="caption" color={colors.textSecondary} style={styles.fieldHint}>
          Cysts send the cow back to needling regardless of the pregnancy result.
        </Text>
      )}
      <FormLabel>Notes</FormLabel>
      <FormInput value={notes} onChangeText={setNotes} placeholder="Optional" multiline />
      <TechnicianRow />
      <FormActions
        onCancel={onCancel}
        submitLabel="Record Check"
        submitIcon="medkit"
        onSubmit={submit}
        loading={loading}
        disabled={!dateValid || result === null || infection === null || cysts === null}
      />
    </>
  );
}

export function CalvingForm({ cow, onCancel, onComplete }: FormProps) {
  const toast = useToast();
  const [calvDate, setCalvDate] = useState(todayISO());
  const [calvTime, setCalvTime] = useState(nowTime());
  const [outcome, setOutcome] = useState<'live' | 'still' | null>(null);
  // 'unknown' is an answer (a stillborn calf is not always sexed); null is
  // "not answered yet", which never saves (Josh, Oct 4).
  const [calfSex, setCalfSex] = useState<'female' | 'male' | 'unknown' | null>(null);
  const [calfTag, setCalfTag] = useState('');
  // Set when the server says the tag is already on the farm. An animal may
  // share one, with an "Are you sure?" and an ID (Josh's test results, Nov 5).
  const [tagInUse, setTagInUse] = useState<string | null>(null);
  const [shareTag, setShareTag] = useState<boolean | null>(null);
  const [calfId, setCalfId] = useState('');
  const [saleInfo, setSaleInfo] = useState('');
  const [notes, setNotes] = useState('');
  const [loading, setLoading] = useState(false);

  // A different tag is a new question.
  useEffect(() => {
    setTagInUse(null);
    setShareTag(null);
  }, [calfTag]);

  // A tag only belongs to a live heifer calf — she is the one that gets a
  // herd record. The field kept its value when the technician switched to
  // Male or Still Birth after typing, and it was submitted regardless, so
  // a stillborn calf could be filed under a real ear tag.
  const tagApplies = outcome === 'live' && calfSex === 'female';

  // Female live calves must get an ear tag (spec); the backend can generate
  // one, so an empty tag is allowed but sex is always required for live births.
  const valid =
    isValidPastOrTodayDate(calvDate) &&
    isValidTime(calvTime) &&
    outcome !== null &&
    calfSex !== null &&
    (outcome === 'still' || calfSex !== 'unknown') &&
    (!tagApplies || !tagInUse || (shareTag === true && !!calfId.trim()));

  const submit = async () => {
    if (!guardApi(toast.error)) return;
    setLoading(true);
    try {
      // Backend stores the calving date; keep the spec-required time in the notes.
      const timeNote = `Calved at ${calvTime}`;
      if ((await record(cow, 'Calving', '/calving/', {
        cow_id: cow.id,
        calving_date: calvDate,
        live_birth: outcome === 'live',
        still_birth: outcome === 'still',
        // A stillborn calf still has a sex worth recording; it is simply not
        // required, since it is not always determined.
        calf_sex: calfSex === 'unknown' ? null : calfSex,
        calf_ear_tag: tagApplies ? calfTag.trim() || null : null,
        calf_herd_id: tagApplies && tagInUse ? calfId.trim() || null : null,
        allow_shared_tag: tagApplies && !!tagInUse && !!shareTag,
        calf_sale_info:
          outcome === 'live' && calfSex === 'male' && saleInfo.trim()
            ? saleInfo.trim()
            : null,
        notes: notes.trim() ? `${timeNote} — ${notes.trim()}` : timeNote,
      }, 'POST')).queued) return queuedDone(onComplete);
      toast.success(`Calving recorded — ${cow.label} is now Fresh`);
      onComplete();
    } catch (e: any) {
      // POST /calving/ opens this refusal with "Ear tag" (services/cow_identity.py).
      if (e instanceof ApiError && e.status === 409 && e.message.startsWith('Ear tag')) {
        setTagInUse(calfTag.trim());
      } else {
        toast.error(errorMessage(e, 'Failed to record calving'));
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <DateTimeFields date={calvDate} time={calvTime} onDate={setCalvDate} onTime={setCalvTime} dateLabel="Calving Date" />
      <FormLabel>Outcome</FormLabel>
      <SegmentedControl
        options={[
          { value: 'live', label: 'Live Birth' },
          { value: 'still', label: 'Still Birth' },
        ]}
        value={outcome}
        onChange={setOutcome}
        style={styles.fieldGap}
      />
      {outcome !== null && (
        <>
          <FormLabel>Calf Sex</FormLabel>
          <SegmentedControl
            options={[
              { value: 'female', label: 'Female' },
              { value: 'male', label: 'Male' },
              // A stillbirth is not always sexed. Without this the control forced
              // one of two answers, so an undetermined calf was recorded as
              // whichever option happened to be selected. Live births still
              // require a real answer (`valid` below).
              ...(outcome === 'still'
                ? [{ value: 'unknown' as const, label: 'Not known' }]
                : []),
            ]}
            value={calfSex}
            onChange={(v) => setCalfSex(v)}
            style={styles.fieldGap}
          />
        </>
      )}
      {outcome === 'live' && (
        <>
          {calfSex === 'female' && (
            <>
              <FormLabel>Calf Ear Tag</FormLabel>
              <FormInput
                value={calfTag}
                onChangeText={setCalfTag}
                placeholder="Leave blank to auto-generate"
              />
              {tagInUse ? (
                <SharedTagQuestion tag={tagInUse} value={shareTag} onChange={setShareTag} />
              ) : null}
              {tagInUse && shareTag ? (
                <>
                  <FormLabel>Calf ID</FormLabel>
                  <FormInput
                    value={calfId}
                    onChangeText={setCalfId}
                    placeholder="Tells her apart from the other animal"
                    autoCapitalize="characters"
                  />
                </>
              ) : null}
              {tagInUse && shareTag === false ? (
                <Text variant="caption" color={colors.textSecondary} style={styles.fieldHint}>
                  Change the tag above, or leave it blank to auto-generate.
                </Text>
              ) : null}
            </>
          )}
          {calfSex === 'male' && (
            <>
              <FormLabel>Sale Info</FormLabel>
              <FormInput
                value={saleInfo}
                onChangeText={setSaleInfo}
                placeholder="Buyer, price, outcome… (optional)"
              />
            </>
          )}
        </>
      )}
      <FormLabel>Calving Notes</FormLabel>
      <FormInput value={notes} onChangeText={setNotes} placeholder="Optional" multiline />
      <TechnicianRow />
      <FormActions
        onCancel={onCancel}
        submitLabel="Record Calving"
        submitIcon="heart"
        onSubmit={submit}
        loading={loading}
        disabled={!valid}
      />
    </>
  );
}

/**
 * Record a health assessment on its own.
 *
 * The Open-cow flow asks the same question before choosing a protocol, but that
 * path is technician-only. POST /cows/{id}/health also accepts vets, so this
 * gives them the assessment without the breeding decision attached.
 */
export function HealthForm({ cow, onCancel, onComplete }: FormProps) {
  const toast = useToast();
  // Decided each time, not carried over from her last check (Josh, Oct 4:
  // nothing saves until the question is answered).
  const [value, setValue] = useState<'healthy' | 'sick' | null>(null);
  const [loading, setLoading] = useState(false);

  const submit = async () => {
    if (value === null) return;
    if (!guardApi(toast.error)) return;
    setLoading(true);
    try {
      if ((await record(cow, 'Health check', `/cows/${cow.id}/health`, { health_status: value }, 'POST')).queued) return queuedDone(onComplete);
      toast.show(
        value === 'sick'
          ? 'Marked sick — recheck her in 7 days; she stays on the Open list.'
          : 'Marked healthy',
        'medkit',
        'success',
      );
      onComplete();
    } catch (e: any) {
      toast.error(errorMessage(e, 'Failed to record health status'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <FormLabel>Condition</FormLabel>
      <SegmentedControl
        options={[
          { value: 'healthy', label: 'Healthy' },
          { value: 'sick', label: 'Sick' },
        ]}
        value={value}
        onChange={setValue}
        style={styles.fieldGap}
      />
      {value === 'sick' && (
        <Text variant="caption" color={colors.textSecondary} style={styles.fieldHint}>
          She stays on the Open list and is re-checked in 7 days rather than every day.
        </Text>
      )}
      <TechnicianRow />
      <FormActions
        onCancel={onCancel}
        submitLabel="Save Health"
        submitIcon="pulse"
        onSubmit={submit}
        loading={loading}
        disabled={value === null}
      />
    </>
  );
}

export function VaccinationForm({ cow, onCancel, onComplete }: FormProps) {
  const toast = useToast();
  const [date, setDate] = useState(todayISO());
  const [time, setTime] = useState(nowTime());
  const [vaccine, setVaccine] = useState('');
  const [lot, setLot] = useState('');
  const [notes, setNotes] = useState('');
  const [loading, setLoading] = useState(false);
  const dim = cow.lastCalvingDate ? daysSince(cow.lastCalvingDate) : null;

  const valid = isValidPastOrTodayDate(date) && isValidTime(time) && vaccine.trim().length > 0;

  const submit = async () => {
    if (!guardApi(toast.error)) return;
    setLoading(true);
    try {
      const body = {
        vaccine_name: vaccine.trim(),
        lot_number: lot.trim() || null,
        administered_at: `${date}T${time}:00`,
        notes: notes.trim() || null,
      };
      // Complete the cow's pending scheduled record if she has one — checked
      // via her own record list, not /vaccinations/due, which only covers the
      // 30-50-day post-calving window and missed every other scheduled vaccine.
      const records = await api.get<{ id: string; completed: boolean; scheduled_date: string }[]>(
        `/vaccinations/cow/${cow.id}`,
      );
      const pending = records.find((r) => !r.completed && r.scheduled_date <= todayISO());
      if (pending) {
        if ((await record(cow, 'Vaccination', `/vaccinations/${pending.id}/complete`, body, 'PATCH')).queued) return queuedDone(onComplete);
      } else {
        // Nothing scheduled (e.g. an imported cow's post-calving shot) —
        // record it ad-hoc rather than telling the technician "no".
        if ((await record(cow, 'Vaccination', `/vaccinations/cow/${cow.id}`, body, 'POST')).queued) return queuedDone(onComplete);
      }
      toast.success(`Vaccination recorded for ${cow.label}`);
      onComplete();
    } catch (e: any) {
      toast.error(errorMessage(e, 'Failed to record vaccination'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      {dim !== null && (
        <Text variant="caption" color={colors.textSecondary} style={{ marginBottom: spacing.md }}>
          Day {dim} post calving (window: days 30–50)
        </Text>
      )}
      <DateTimeFields date={date} time={time} onDate={setDate} onTime={setTime} />
      <FormLabel>Vaccine Name</FormLabel>
      <FormInput value={vaccine} onChangeText={setVaccine} placeholder="Required" />
      <FormLabel>Lot Number</FormLabel>
      <FormInput value={lot} onChangeText={setLot} placeholder="Optional" />
      <FormLabel>Notes</FormLabel>
      <FormInput value={notes} onChangeText={setNotes} placeholder="Optional" multiline />
      <TechnicianRow />
      <FormActions
        onCancel={onCancel}
        submitLabel="Record Vaccination"
        submitIcon="shield-checkmark"
        onSubmit={submit}
        loading={loading}
        disabled={!valid}
      />
    </>
  );
}

/**
 * Put a cow on the Insemination Program by hand, to be bred with no protocol.
 * Josh's test results, Nov 5: "allow for manual enrollment in a protocol or
 * programs".
 */
export function ProgramForm({ cow, onCancel, onComplete }: FormProps) {
  const toast = useToast();
  const earlyDay = earlyBreedingDay(cow);
  const [sureEarly, setSureEarly] = useState<boolean | null>(null);
  const [loading, setLoading] = useState(false);

  const submit = async () => {
    if (!guardApi(toast.error)) return;
    setLoading(true);
    try {
      if ((await record(cow, 'Insemination Program', `/cows/${cow.id}/insemination-program`, {}, 'POST')).queued) return queuedDone(onComplete);
      toast.success(`${cow.label} is on the Insemination Program`);
      onComplete();
    } catch (e: any) {
      toast.error(errorMessage(e, 'Failed to put her on the program'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <Text variant="body" color={colors.textSecondary} style={styles.fieldHint}>
        She goes on the Insemination Program report, to be bred directly with no protocol.
      </Text>
      {earlyDay !== null ? (
        <YesNoField
          label={`Day ${earlyDay} post calving, under ${MIN_DAYS_POST_CALVING_TO_BREED} days. Are you sure?`}
          value={sureEarly}
          onChange={setSureEarly}
        />
      ) : null}
      <TechnicianRow />
      <FormActions
        onCancel={onCancel}
        submitLabel="Add to Program"
        submitIcon="git-branch"
        onSubmit={submit}
        loading={loading}
        disabled={earlyDay !== null && sureEarly !== true}
      />
    </>
  );
}

export function EnrollForm({ cow, onCancel, onComplete }: FormProps) {
  const toast = useToast();
  // Asked fresh every time, never carried over from her last answer or
  // pre-picked (Josh, Oct 4: the technician decides every question).
  const [health, setHealth] = useState<'healthy' | 'sick' | null>(null);
  const [healthConfirmed, setHealthConfirmed] = useState(false);
  const [protocol, setProtocol] = useState<string | null>(null);
  // Today when protocols may start today, else the next Mon/Tue/Sat.
  const [startDate, setStartDate] = useState(() => nextStartDay(todayISO()));
  const [loading, setLoading] = useState(false);
  const [savingHealth, setSavingHealth] = useState(false);
  const earlyDay = earlyBreedingDay(cow);
  const [sureEarly, setSureEarly] = useState<boolean | null>(null);

  const steps = useMemo(() => (protocol ? protocolByValue(protocol)?.steps ?? [] : []), [protocol]);
  // Shape alone let 2026-13-45 and a typo'd year through, and a protocol
  // schedules ten days of injections off this date.
  const dateValid = isValidStartDate(startDate);
  const offPreferredDay = dateValid && !isPreferredStartDay(startDate);

  // Record the health assessment. Sick → backend sets a 7-day recheck and the
  // cow stays Open; healthy → proceed to protocol selection.
  const recordHealth = async (value: 'healthy' | 'sick') => {
    if (!guardApi(toast.error)) {
      // In demo mode just advance locally so the flow is explorable.
      if (value === 'healthy') setHealthConfirmed(true);
      return;
    }
    setSavingHealth(true);
    try {
      if ((await record(cow, 'Health check', `/cows/${cow.id}/health`, { health_status: value }, 'POST')).queued) return queuedDone(onComplete);
      if (value === 'sick') {
        toast.show('Marked sick — recheck her in 7 days; she stays on the Open list.', 'medkit', 'success');
        onComplete();
      } else {
        setHealthConfirmed(true);
      }
    } catch (e: any) {
      toast.error(errorMessage(e, 'Failed to record health status'));
    } finally {
      setSavingHealth(false);
    }
  };

  const submit = async () => {
    if (!guardApi(toast.error)) return;
    setLoading(true);
    try {
      if ((await record(cow, 'Protocol enrolment', '/needling/enroll', {
        cow_id: cow.id,
        protocol,
        start_date: startDate,
      }, 'POST')).queued) return queuedDone(onComplete);
      toast.success(`${cow.label} enrolled in ${protocolByValue(protocol!)?.label}`);
      onComplete();
    } catch (e: any) {
      toast.error(errorMessage(e, 'Failed to enroll in protocol'));
    } finally {
      setLoading(false);
    }
  };

  // Open Cow Report rule: check health first; sick cows are re-checked
  // every 7 days instead of starting a protocol.
  if (!healthConfirmed) {
    return (
      <>
        <FormLabel>Health Status</FormLabel>
        <Text variant="caption" color={colors.textSecondary} style={styles.fieldHint}>
          Assess the cow before choosing a protocol.
        </Text>
        <SegmentedControl
          options={[
            { value: 'healthy', label: 'Healthy' },
            { value: 'sick', label: 'Sick' },
          ]}
          value={health}
          onChange={setHealth}
          style={styles.fieldGap}
        />
        {health === 'sick' && (
          <Text variant="body" color={colors.textSecondary} style={styles.fieldHint}>
            Sick cows don't start a protocol. She'll stay on the Open list and reappear for a
            re-check in 7 days.
          </Text>
        )}
        <View style={styles.modalActions}>
          <Button compact variant="secondary" label="Cancel" onPress={onCancel} style={styles.flex1} />
          <Button
            compact
            variant={health === 'sick' ? 'danger' : 'primary'}
            label={health === 'sick' ? 'Mark Sick' : 'Continue'}
            onPress={() => health && recordHealth(health)}
            loading={savingHealth}
            disabled={!health}
            style={styles.flex1}
          />
        </View>
      </>
    );
  }

  return (
    <>
      <FormLabel>Protocol</FormLabel>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: spacing.md }}>
        <View style={{ flexDirection: 'row', gap: spacing.sm }}>
          {PROTOCOLS.map((p) => {
            const selected = protocol === p.value;
            return (
              <Pressable
                key={p.value}
                style={[styles.chip, selected && styles.chipActive]}
                onPress={() => setProtocol(p.value)}
                accessibilityRole="radio"
                accessibilityState={{ selected }}
                accessibilityLabel={p.label}
              >
                <Text variant="label" color={selected ? colors.textOnPrimary : colors.textSecondary}>
                  {p.label}
                </Text>
              </Pressable>
            );
          })}
        </View>
      </ScrollView>

      {/* schedule preview straight from the protocol table */}
      {protocol ? (
        <View style={styles.scheduleBox}>
          {steps.map((s) => (
            <View key={s.day} style={styles.scheduleRow}>
              <Text variant="caption" color={colors.textSecondary} style={styles.scheduleDay}>
                Day {s.day}
              </Text>
              <Text variant="caption" color={s.final ? colors.primary : colors.text}>
                {s.treatment}
              </Text>
            </View>
          ))}
        </View>
      ) : null}

      <FormLabel>Start Date</FormLabel>
      <FormInput
        value={startDate}
        onChangeText={setStartDate}
        placeholder="YYYY-MM-DD"
        keyboardType="numbers-and-punctuation"
      />
      {!dateValid && startDate.length > 0 && (
        <Text variant="caption" color={colors.danger} style={styles.fieldError}>
          Enter a real date (YYYY-MM-DD), from yesterday to {START_DATE_LOOKAHEAD_DAYS} days ahead.
        </Text>
      )}
      {offPreferredDay && (
        <Text variant="caption" color={colors.danger} style={styles.fieldError}>
          A protocol can only start on a Monday, Tuesday or Saturday.
        </Text>
      )}
      {earlyDay !== null ? (
        <YesNoField
          label={`Day ${earlyDay} post calving, under ${MIN_DAYS_POST_CALVING_TO_BREED} days. Are you sure?`}
          value={sureEarly}
          onChange={setSureEarly}
        />
      ) : null}
      <FormActions
        onCancel={onCancel}
        submitLabel="Enroll"
        submitIcon="list"
        onSubmit={submit}
        loading={loading}
        disabled={!dateValid || offPreferredDay || !protocol || (earlyDay !== null && sureEarly !== true)}
      />
    </>
  );
}

export function DryOffConfirmForm({ cow, onCancel, onComplete }: FormProps) {
  const toast = useToast();
  const [loading, setLoading] = useState(false);

  const submit = async () => {
    if (!guardApi(toast.error)) return;
    setLoading(true);
    try {
      if ((await record(cow, 'Moved to dry pen', `/cows/${cow.id}/dry-off-confirm`, {}, 'POST')).queued) return queuedDone(onComplete);
      toast.success(`${cow.label} confirmed in the dry pen`);
      onComplete();
    } catch (e: any) {
      toast.error(errorMessage(e, 'Failed to confirm dry off'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <Text variant="body" color={colors.textSecondary} style={styles.fieldHint}>
        Confirm {cow.label} has been moved to the dry pen. She leaves the Dry Report once
        recorded — without this it repeats every day.
      </Text>
      <TechnicianRow />
      <FormActions
        onCancel={onCancel}
        submitLabel="Confirm Dry Off"
        submitIcon="moon"
        onSubmit={submit}
        loading={loading}
      />
    </>
  );
}

function CullConfirm({ cow, onCancel, onComplete }: FormProps) {
  const toast = useToast();
  const [reason, setReason] = useState('');
  const [date, setDate] = useState(todayISO());
  const [notes, setNotes] = useState('');
  const [loading, setLoading] = useState(false);

  const valid = reason.trim().length > 0 && isValidPastOrTodayDate(date);

  const submit = async () => {
    if (!guardApi(toast.error)) return;
    setLoading(true);
    try {
      if ((await record(cow, 'Cull', `/cows/${cow.id}/cull`, {
        cull_date: date,
        reason: reason.trim(),
        notes: notes.trim() || null,
      }, 'POST')).queued) return queuedDone(onComplete);
      toast.success(`${cow.label} marked as Cull`);
      onComplete();
    } catch (e: any) {
      toast.error(errorMessage(e, 'Failed to cull cow'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <Text variant="body" color={colors.textSecondary} style={{ marginBottom: spacing.lg }}>
        Mark <Text variant="bodyBold">{cow.label}</Text> as cull? She'll be removed from all
        active programs and breeding schedules.
      </Text>
      <FormLabel>Cull Date</FormLabel>
      <FormInput value={date} onChangeText={setDate} placeholder="YYYY-MM-DD" keyboardType="numbers-and-punctuation" />
      <FormLabel>Cull Reason</FormLabel>
      <FormInput value={reason} onChangeText={setReason} placeholder="Age, health, productivity… (required)" />
      <FormLabel>Notes</FormLabel>
      <FormInput value={notes} onChangeText={setNotes} placeholder="Optional" multiline />
      <TechnicianRow />
      <FormActions
        onCancel={onCancel}
        submitLabel="Confirm Cull"
        submitIcon="trash"
        onSubmit={submit}
        loading={loading}
        disabled={!valid}
        danger
      />
    </>
  );
}

function FinalStatusConfirm({ cow, onCancel, onComplete, kind }: FormProps & { kind: 'sold' | 'dead' }) {
  const toast = useToast();
  const [notes, setNotes] = useState('');
  const [loading, setLoading] = useState(false);

  const submit = async () => {
    if (!guardApi(toast.error)) return;
    setLoading(true);
    try {
      if ((await record(cow, `Marked ${kind}`, `/cows/${cow.id}/mark-${kind}`, { reason: notes.trim() || null }, 'POST')).queued) return queuedDone(onComplete);
      toast.success(`${cow.label} marked as ${kind === 'sold' ? 'Sold' : 'Dead'}`);
      onComplete();
    } catch (e: any) {
      toast.error(errorMessage(e, 'Failed to update status'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <Text variant="body" color={colors.textSecondary} style={{ marginBottom: spacing.lg }}>
        Mark <Text variant="bodyBold">{cow.label}</Text> as {kind}? This is final and cannot be
        undone.
      </Text>
      <FormLabel>Notes</FormLabel>
      <FormInput
        value={notes}
        onChangeText={setNotes}
        placeholder={kind === 'sold' ? 'Sale details (buyer, price…)' : 'Cause, if known'}
        multiline
      />
      <FormActions
        onCancel={onCancel}
        submitLabel={kind === 'sold' ? 'Mark Sold' : 'Mark Dead'}
        submitIcon={kind === 'sold' ? 'cash' : 'close-circle'}
        onSubmit={submit}
        loading={loading}
        danger
      />
    </>
  );
}

// ── offline mode ──────────────────────────────────────────────

/** Save an outcome now, or keep it on the phone to send when there is signal
 *  (Josh's Part A platform tests; lib/outbox.ts). */
function record<T = unknown>(
  cow: { id: string; label: string }, what: string, path: string, body: unknown,
  method: 'POST' | 'PATCH' = 'POST',
) {
  return saveOutcome<T>({ method, path, body, cowId: cow.id, label: `${what} — ${cow.label}` });
}

/** A save kept on the phone: say so, and close the form as if it had gone. */
function queuedDone(done: () => void) {
  useToast.getState().show(
    'Saved on this phone — it will be sent when you have signal', 'cloud-offline', 'info');
  done();
}

// ── main export ───────────────────────────────────────────────

interface Props {
  cow: Cow;
  onRefresh: () => void;
  /** Open this form at once, when she offers it: the birth check's Yes
   *  opens Record Calving (Josh's change requests, Nov 20). */
  openAction?: string;
}

export function CowActionsSheet({ cow, onRefresh, openAction }: Props) {
  const [activeAction, setActiveAction] = useState<ActionKey | null>(null);
  const role = useRole();
  const insets = useSafeAreaInsets();
  // Which actions a cow offers is a capability decision. Defaulting an
  // unresolved role to 'technician' offered a vet buttons the API answers
  // with a 403 — the same regression this screen has had before.
  const actions = role ? getActions(cow, role) : [];
  const opened = useRef(false);
  useEffect(() => {
    if (opened.current || !openAction) return;
    if (actions.includes(openAction as ActionKey)) {
      opened.current = true;
      setActiveAction(openAction as ActionKey);
    }
  }, [openAction, actions.join()]);

  if (actions.length === 0) return null;

  const MODAL_TITLES: Record<ActionKey, string> = {
    health:          'Record Health Check',
    enroll:          'Enroll in Protocol',
    program:         'Insemination Program',
    inseminate:      'Record Artificial Insemination',
    heat_check:      'Record Heat Check',
    seen_heat:       'Seen in Heat',
    pregnancy_check: 'Record Pregnancy Check',
    calving:         'Record Calving',
    vaccinate:       'Record Vaccination',
    cull:            'Mark as Cull',
    mark_sold:       'Mark as Sold',
    mark_dead:       'Mark as Dead',
  };

  const dismiss = () => setActiveAction(null);
  const complete = () => {
    setActiveAction(null);
    onRefresh();
    // Every event recorded here can move her between reports -- a heat puts
    // her on Today's Breed Report "immediately" (Josh, Oct 4). Only the cow
    // was refetched, so the To-Do and report screens kept showing the day's
    // first copy of the work list until a pull-to-refresh.
    useAppStore.getState().fetchWorklist();
  };

  const formProps = { cow, onCancel: dismiss, onComplete: complete };

  const renderForm = () => {
    switch (activeAction) {
      case 'inseminate':      return <InseminationForm {...formProps} />;
      case 'heat_check':      return <HeatCheckForm {...formProps} />;
      case 'seen_heat':       return <SeenInHeatForm {...formProps} />;
      case 'pregnancy_check': return <PregnancyCheckForm {...formProps} />;
      case 'calving':         return <CalvingForm {...formProps} />;
      case 'vaccinate':       return <VaccinationForm {...formProps} />;
      case 'health':          return <HealthForm {...formProps} />;
      case 'enroll':          return <EnrollForm {...formProps} />;
      case 'program':         return <ProgramForm {...formProps} />;
      case 'cull':            return <CullConfirm {...formProps} />;
      case 'mark_sold':       return <FinalStatusConfirm {...formProps} kind="sold" />;
      case 'mark_dead':       return <FinalStatusConfirm {...formProps} kind="dead" />;
      default:                return null;
    }
  };

  return (
    <>
      <SectionHeader title="Actions" />

      <View style={styles.actionsGrid}>
        {actions.map((key) => {
          const def = ACTION_DEFS[key];
          return (
            <Pressable
              key={key}
              style={[styles.actionChip, def.danger && styles.actionChipDanger]}
              onPress={() => setActiveAction(key)}
              accessibilityRole="button"
              accessibilityLabel={def.label}
            >
              <Ionicons
                name={def.icon}
                size={18}
                color={def.danger ? colors.red[700] : colors.primary}
              />
              <Text
                variant="label"
                color={def.danger ? colors.red[700] : colors.text}
              >
                {def.label}
              </Text>
            </Pressable>
          );
        })}
      </View>

      <Modal
        visible={!!activeAction}
        transparent
        animationType="slide"
        onRequestClose={dismiss}
      >
        <KeyboardAvoidingView
          behavior={Platform.OS === 'ios' ? 'padding' : undefined}
          style={styles.modalRoot}
        >
          <Pressable
            style={styles.modalBackdrop}
            onPress={dismiss}
            accessibilityRole="button"
            accessibilityLabel="Dismiss"
          />
          <View style={[styles.modalSheet, { paddingBottom: insets.bottom + spacing.lg }]}>
            {/* Toasts must live inside the Modal or they render behind it. */}
            {!!activeAction && <ModalToastHost />}
            <View style={styles.modalHandle} />
            <View style={styles.sheetHeader}>
              <Text variant="heading">
                {activeAction ? MODAL_TITLES[activeAction] : ''}
              </Text>
              <Text variant="caption" color={colors.textSecondary}>
                {[cow.label, herdIdLabel(cow)].filter(Boolean).join(' · ')}
              </Text>
            </View>
            <ScrollView
              showsVerticalScrollIndicator={false}
              keyboardShouldPersistTaps="handled"
              /* Buttons sit at the end of the form; without this the last row
                 is clipped by the sheet edge on gesture-bar devices. */
              contentContainerStyle={{ gap: spacing.sm, paddingBottom: spacing.lg }}
            >
              {renderForm()}
            </ScrollView>
          </View>
        </KeyboardAvoidingView>
      </Modal>
    </>
  );
}

const styles = StyleSheet.create({
  actionsGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.sm,
    marginHorizontal: spacing.xl,
    marginBottom: spacing.lg,
  },
  actionChip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    minHeight: 44,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm + 2,
    borderRadius: radius.pill,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    ...shadows.card,
  },
  actionChipDanger: {
    borderColor: colors.red[200],
    backgroundColor: colors.red[50],
  },
  input: {
    backgroundColor: colors.surfaceSoft,
    borderRadius: radius.sm,
    borderWidth: 1,
    borderColor: colors.border,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm + 2,
    color: colors.text,
    ...typography.input,
    marginBottom: spacing.sm,
  },
  inputMulti: {
    minHeight: 72,
    textAlignVertical: 'top',
  },
  inputError: {
    borderColor: colors.danger,
  },
  fieldError: {
    marginTop: -spacing.xs,
    marginBottom: spacing.sm,
  },
  fieldHint: {
    marginBottom: spacing.md,
  },
  combinedBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    backgroundColor: colors.primarySoft,
    borderWidth: 1,
    borderColor: colors.red[200],
    borderRadius: radius.sm,
    padding: spacing.md,
    marginBottom: spacing.md,
  },
  fieldGap: {
    marginBottom: spacing.md,
  },
  dateTimeRow: {
    flexDirection: 'row',
    gap: spacing.md,
  },
  techRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs + 2,
    marginTop: spacing.xs,
  },
  chip: {
    minHeight: 44,
    justifyContent: 'center',
    paddingHorizontal: spacing.lg,
    borderRadius: radius.pill,
    backgroundColor: colors.surfaceSoft,
    borderWidth: 1,
    borderColor: colors.border,
  },
  chipActive: {
    backgroundColor: colors.primary,
    borderColor: colors.primary,
  },
  scheduleBox: {
    backgroundColor: colors.surfaceSoft,
    borderRadius: radius.sm,
    borderWidth: 1,
    borderColor: colors.border,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    marginBottom: spacing.md,
    gap: spacing.xs,
  },
  scheduleRow: {
    flexDirection: 'row',
    gap: spacing.md,
  },
  scheduleDay: {
    width: 52,
  },
  modalRoot: {
    flex: 1,
    justifyContent: 'flex-end',
  },
  modalBackdrop: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: colors.overlayDark,
  },
  modalSheet: {
    backgroundColor: colors.background,
    borderTopLeftRadius: radius.xl,
    borderTopRightRadius: radius.xl,
    padding: spacing.xxl,
    maxHeight: '88%',
  },
  // Title and ear tag are one unit; the gap below them separates that
  // unit from the form, which is a different kind of break.
  sheetHeader: { gap: spacing.hairline, marginBottom: spacing.xl },
  modalHandle: {
    width: 36,
    height: 4,
    borderRadius: 2,
    backgroundColor: colors.cream.line,
    alignSelf: 'center',
    marginBottom: spacing.lg,
  },
  modalActions: {
    flexDirection: 'row',
    gap: spacing.md,
    marginTop: spacing.md,
  },
  bullRow: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.xs, marginBottom: spacing.sm },
  addBullRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  bullChip: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  bullChipOn: { borderColor: colors.primary, backgroundColor: colors.primarySoft },
  flex1: { flex: 1 },
  flex2: { flex: 2 },
});
