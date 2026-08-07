import { Ionicons } from '@expo/vector-icons';
import React, { useMemo, useState } from 'react';
import {
  KeyboardAvoidingView,
  Modal,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Switch,
  TextInput,
  View,
} from 'react-native';
import { Button, SegmentedControl, SectionHeader, Text, useToast } from '@/components';
import { FormInput, FormLabel } from './FormField';
import { api, isApiConfigured } from '@/lib/api';
import { daysSince, isValidPastOrTodayDate, todayISO } from '@/lib/dates';
import { isPreferredStartDay, PROTOCOLS, protocolByValue } from '@/data/protocols';
import { Role as UserRole, useAuthStore } from '@/store/useAuthStore';
import { colors, radius, shadows, spacing, typography } from '@/theme';
import { Cow, CowStatus } from '@/data/types';

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
  | 'enroll'
  | 'inseminate'
  | 'heat_check'
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
  enroll:           { key: 'enroll',           label: 'Enroll Protocol', icon: 'list' },
  inseminate:       { key: 'inseminate',       label: 'Record AI',       icon: 'flask' },
  heat_check:       { key: 'heat_check',       label: 'Heat Check',      icon: 'flame' },
  pregnancy_check:  { key: 'pregnancy_check',  label: 'Preg Check',      icon: 'medkit' },
  calving:          { key: 'calving',          label: 'Record Calving',  icon: 'heart' },
  vaccinate:        { key: 'vaccinate',        label: 'Vaccinate',       icon: 'shield-checkmark' },
  cull:             { key: 'cull',             label: 'Mark Cull',       icon: 'trash', danger: true },
  mark_sold:        { key: 'mark_sold',        label: 'Mark Sold',       icon: 'cash', danger: true },
  mark_dead:        { key: 'mark_dead',        label: 'Mark Dead',       icon: 'close-circle', danger: true },
};

/**
 * Actions only certain roles may perform. Must mirror the backend's
 * `require_roles` — offering an action the API will reject with a 403 is worse
 * than not offering it. Pregnancy checks are recordable by technician or vet
 * (client decision, 2026-08-06), so nothing is restricted here today.
 */
const ROLE_RESTRICTED: Partial<Record<ActionKey, UserRole[]>> = {};

function getActions(cow: RecordTarget, role: UserRole): ActionKey[] {
  const keys: ActionKey[] = [];
  const days = daysPostInsemination(cow);
  const dim = cow.lastCalvingDate ? daysSince(cow.lastCalvingDate) : null;

  switch (cow.status) {
    case 'heifer':
    case 'open':
      keys.push('enroll', 'inseminate');
      break;
    case 'needling':
      // TAI happens on the protocol's final day (Timed Breeding task);
      // recording here covers heat-observed protocols too.
      keys.push('inseminate');
      break;
    case 'inseminated':
      if (days !== null && days >= 20 && days <= 25) keys.push('heat_check');
      if (days !== null && days >= 30) keys.push('pregnancy_check');
      break;
    case 'fresh':
      // Vaccination window: 30–50 days post calving
      if (dim !== null && dim >= 30) keys.push('vaccinate');
      break;
    case 'pregnant':
    case 'dry':
      keys.push('calving');
      break;
    case 'cull':
      keys.push('mark_sold', 'mark_dead');
      break;
  }

  if (!['cull', 'sold', 'dead'].includes(cow.status)) keys.push('cull');
  return keys.filter((k) => (ROLE_RESTRICTED[k] ?? []).length === 0 || ROLE_RESTRICTED[k]!.includes(role));
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

function FormToggle({ label, value, onChange }: { label: string; value: boolean; onChange: (v: boolean) => void }) {
  return (
    <View style={styles.toggleRow}>
      <Text variant="body">{label}</Text>
      <Switch
        value={value}
        onValueChange={onChange}
        trackColor={{ false: colors.cream.line, true: colors.primary }}
        thumbColor={colors.cream.base}
        accessibilityLabel={label}
      />
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
  earTag: string;
  status: CowStatus;
  lastInseminationId?: string;
  lastInseminationDate?: string;
  lastCalvingDate?: string;
  healthStatus?: Cow['healthStatus'];
}

interface FormProps {
  cow: RecordTarget;
  onCancel: () => void;
  onComplete: () => void;
}

export function InseminationForm({
  cow, onCancel, onComplete, banner,
}: FormProps & { banner?: string; finalNeedlingRecordId?: string }) {
  // Bleeding replaces the insemination for a cow still in a protocol. It is
  // offered whenever she is mid-protocol — NOT only when a completable record
  // happens to exist, because after the final shot there is none left and that
  // is exactly when she is closest to insemination.
  const canBleed = cow.status === 'needling';
  const toast = useToast();
  // Bleeding can be recorded on ANY protocol day, including the final one.
  // Bleeding means no insemination: the cow goes Open and restarts on Ovsynch.
  const [bleeding, setBleeding] = useState(false);
  const [date, setDate] = useState(todayISO());
  const [time, setTime] = useState(nowTime());
  const [bull, setBull] = useState('');
  const [doseId, setDoseId] = useState('');
  const [semenType, setSemenType] = useState<'sexed' | 'conventional' | 'beef' | null>(null);
  const [notes, setNotes] = useState('');
  const [loading, setLoading] = useState(false);

  // When bleeding is recorded there is no AI, so the AI fields aren't required.
  const valid = bleeding && canBleed
    ? true
    : isValidPastOrTodayDate(date) && isValidTime(time) && bull.trim().length > 0 && semenType !== null;

  const submit = async () => {
    if (!guardApi(toast.error)) return;
    setLoading(true);
    try {
      // Bleeding: record the event instead of an AI. Goes to the cow-level
      // endpoint, which works whether or not a scheduled record is still open —
      // the backend cancels the enrollment and re-enrolls her on Ovsynch.
      if (bleeding && canBleed) {
        await api.post(`/needling/cow/${cow.id}/bleeding`, {
          notes: notes.trim() || null,
        });
        toast.show(
          `Bleeding recorded — ${cow.earTag} moves to Open and restarts on Ovsynch`,
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
      await api.post('/inseminations/', {
        cow_id: cow.id,
        date: `${date}T${time}:00`,
        bull_name: bull.trim(),
        dose_id: doseId.trim() || null,
        semen_type: semenType,
        notes: notes.trim() || null,
      });
      toast.success(
        banner
          ? `Final injection + AI recorded — ${cow.earTag} is now Inseminated`
          : `AI recorded — ${cow.earTag} is now Inseminated`,
      );
      onComplete();
    } catch (e: any) {
      toast.error(e?.message ?? 'Failed to record insemination');
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      {banner ? (
        <View style={styles.combinedBanner}>
          <Ionicons name="fitness" size={18} color={colors.primary} />
          <Text variant="caption" color={colors.text} style={styles.flex1}>
            {banner}
          </Text>
        </View>
      ) : null}

      {/* Bleeding is recordable on any protocol day — including the final one,
          where it replaces the insemination. */}
      {canBleed ? (
        <>
          <FormToggle label="Bleeding event?" value={bleeding} onChange={setBleeding} />
          {bleeding && (
            <Text variant="caption" color={colors.textSecondary} style={styles.fieldHint}>
              No insemination will be recorded. She moves to Open and restarts on Ovsynch.
            </Text>
          )}
        </>
      ) : null}

      {!bleeding && (
        <>
          <DateTimeFields date={date} time={time} onDate={setDate} onTime={setTime} dateLabel="Insemination Date" />
          <FormLabel>Bull Name</FormLabel>
          <FormInput value={bull} onChangeText={setBull} placeholder="Required" />
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

export function HeatCheckForm({ cow, onCancel, onComplete }: FormProps) {
  const toast = useToast();
  const [heatDetected, setHeatDetected] = useState(false);
  const [bloodOnTail, setBloodOnTail] = useState(false);
  const [notes, setNotes] = useState('');
  const [loading, setLoading] = useState(false);
  const days = daysPostInsemination(cow) ?? 0;

  const submit = async () => {
    if (!cow.lastInseminationId) {
      toast.error('No insemination on record for this cow');
      return;
    }
    if (!guardApi(toast.error)) return;
    setLoading(true);
    try {
      // Blood on the tail means she WAS in heat — the spec treats it as a heat event.
      const effectiveHeat = heatDetected || bloodOnTail;
      await api.post('/checks/heat', {
        cow_id: cow.id,
        insemination_id: cow.lastInseminationId,
        check_date: todayISO(),
        heat_detected: effectiveHeat,
        bleeding_event: bloodOnTail,
        notes: notes.trim() || null,
      });
      toast.show(
        effectiveHeat
          ? 'Heat detected — cow returned to the Insemination Program'
          : 'No heat — she stays Inseminated; preg check at day 30+',
        effectiveHeat ? 'flame' : 'checkmark-circle',
        'success',
      );
      onComplete();
    } catch (e: any) {
      toast.error(e?.message ?? 'Failed to record heat check');
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <Text variant="caption" color={colors.textSecondary} style={{ marginBottom: spacing.md }}>
        Day {days} post insemination (heat window: days 20–25)
      </Text>
      <FormToggle label="Heat Detected?" value={heatDetected} onChange={setHeatDetected} />
      <FormToggle label="Blood on Tail?" value={bloodOnTail} onChange={setBloodOnTail} />
      {bloodOnTail && (
        <Text variant="caption" color={colors.textSecondary} style={styles.fieldHint}>
          Blood on the tail means she was in heat — she'll return to the Insemination Program.
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
      />
    </>
  );
}

export function PregnancyCheckForm({ cow, onCancel, onComplete }: FormProps) {
  const toast = useToast();
  const [result, setResult] = useState<'pregnant' | 'not_pregnant'>('pregnant');
  const [infection, setInfection] = useState(false);
  const [cysts, setCysts] = useState(false);
  const [notes, setNotes] = useState('');
  const [loading, setLoading] = useState(false);

  const submit = async () => {
    if (!cow.lastInseminationId) {
      toast.error('No insemination on record for this cow');
      return;
    }
    if (!guardApi(toast.error)) return;
    setLoading(true);
    try {
      await api.post('/checks/pregnancy', {
        cow_id: cow.id,
        insemination_id: cow.lastInseminationId,
        check_date: todayISO(),
        result,
        has_infection: infection,
        has_cysts: cysts,
        notes: notes.trim() || null,
      });
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
      toast.error(e?.message ?? 'Failed to record pregnancy check');
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
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
      <FormToggle label="Infection?" value={infection} onChange={setInfection} />
      <FormToggle label="Cysts?" value={cysts} onChange={setCysts} />
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
      />
    </>
  );
}

export function CalvingForm({ cow, onCancel, onComplete }: FormProps) {
  const toast = useToast();
  const [calvDate, setCalvDate] = useState(todayISO());
  const [calvTime, setCalvTime] = useState(nowTime());
  const [outcome, setOutcome] = useState<'live' | 'still'>('live');
  const [calfSex, setCalfSex] = useState<'female' | 'male' | null>(null);
  const [calfTag, setCalfTag] = useState('');
  const [saleInfo, setSaleInfo] = useState('');
  const [notes, setNotes] = useState('');
  const [loading, setLoading] = useState(false);

  // Female live calves must get an ear tag (spec); the backend can generate
  // one, so an empty tag is allowed but sex is always required for live births.
  const valid =
    isValidPastOrTodayDate(calvDate) &&
    isValidTime(calvTime) &&
    (outcome === 'still' || calfSex !== null);

  const submit = async () => {
    if (!guardApi(toast.error)) return;
    setLoading(true);
    try {
      // Backend stores the calving date; keep the spec-required time in the notes.
      const timeNote = `Calved at ${calvTime}`;
      await api.post('/calving/', {
        cow_id: cow.id,
        calving_date: calvDate,
        live_birth: outcome === 'live',
        still_birth: outcome === 'still',
        calf_sex: outcome === 'live' ? calfSex : null,
        calf_ear_tag: calfTag.trim() || null,
        calf_sale_info: calfSex === 'male' && saleInfo.trim() ? saleInfo.trim() : null,
        notes: notes.trim() ? `${timeNote} — ${notes.trim()}` : timeNote,
      });
      toast.success(`Calving recorded — ${cow.earTag} is now Fresh`);
      onComplete();
    } catch (e: any) {
      toast.error(e?.message ?? 'Failed to record calving');
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
      {outcome === 'live' && (
        <>
          <FormLabel>Calf Sex</FormLabel>
          <SegmentedControl
            options={[
              { value: 'female', label: 'Female' },
              { value: 'male', label: 'Male' },
            ]}
            value={calfSex}
            onChange={setCalfSex}
            style={styles.fieldGap}
          />
          {calfSex === 'female' && (
            <>
              <FormLabel>Calf Ear Tag</FormLabel>
              <FormInput
                value={calfTag}
                onChangeText={setCalfTag}
                placeholder="Leave blank to auto-generate"
              />
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
        await api.patch(`/vaccinations/${pending.id}/complete`, body);
      } else {
        // Nothing scheduled (e.g. an imported cow's post-calving shot) —
        // record it ad-hoc rather than telling the technician "no".
        await api.post(`/vaccinations/cow/${cow.id}`, body);
      }
      toast.success(`Vaccination recorded for ${cow.earTag}`);
      onComplete();
    } catch (e: any) {
      toast.error(e?.message ?? 'Failed to record vaccination');
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

export function EnrollForm({ cow, onCancel, onComplete }: FormProps) {
  const toast = useToast();
  const [health, setHealth] = useState<'healthy' | 'sick' | null>(
    cow.healthStatus ?? null,
  );
  const [healthConfirmed, setHealthConfirmed] = useState(false);
  const [protocol, setProtocol] = useState('ovsynch');
  const [startDate, setStartDate] = useState(todayISO());
  const [loading, setLoading] = useState(false);
  const [savingHealth, setSavingHealth] = useState(false);

  const steps = useMemo(() => protocolByValue(protocol)?.steps ?? [], [protocol]);
  const dateValid = /^\d{4}-\d{2}-\d{2}$/.test(startDate);
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
      await api.post(`/cows/${cow.id}/health`, { health_status: value });
      if (value === 'sick') {
        toast.show('Marked sick — recheck her in 7 days; she stays on the Open list.', 'medkit', 'success');
        onComplete();
      } else {
        setHealthConfirmed(true);
      }
    } catch (e: any) {
      toast.error(e?.message ?? 'Failed to record health status');
    } finally {
      setSavingHealth(false);
    }
  };

  const submit = async () => {
    if (!guardApi(toast.error)) return;
    setLoading(true);
    try {
      await api.post('/needling/enroll', {
        cow_id: cow.id,
        protocol,
        start_date: startDate,
      });
      toast.success(`${cow.earTag} enrolled in ${protocolByValue(protocol)?.label}`);
      onComplete();
    } catch (e: any) {
      toast.error(e?.message ?? 'Failed to enroll in protocol');
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

      <FormLabel>Start Date</FormLabel>
      <FormInput
        value={startDate}
        onChangeText={setStartDate}
        placeholder="YYYY-MM-DD"
        keyboardType="numbers-and-punctuation"
      />
      {offPreferredDay && (
        <Text variant="caption" color={colors.warning} style={styles.fieldError}>
          Program starts are scheduled Monday, Tuesday or Saturday.
        </Text>
      )}
      <FormActions
        onCancel={onCancel}
        submitLabel="Enroll"
        submitIcon="list"
        onSubmit={submit}
        loading={loading}
        disabled={!dateValid}
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
      await api.post(`/cows/${cow.id}/dry-off-confirm`, {});
      toast.success(`${cow.earTag} confirmed in the dry pen`);
      onComplete();
    } catch (e: any) {
      toast.error(e?.message ?? 'Failed to confirm dry off');
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <Text variant="body" color={colors.textSecondary} style={styles.fieldHint}>
        Confirm {cow.earTag} has been moved to the dry pen. She leaves the Dry Report once
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
      await api.post(`/cows/${cow.id}/cull`, {
        cull_date: date,
        reason: reason.trim(),
        notes: notes.trim() || null,
      });
      toast.success(`${cow.earTag} marked as Cull`);
      onComplete();
    } catch (e: any) {
      toast.error(e?.message ?? 'Failed to cull cow');
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <Text variant="body" color={colors.textSecondary} style={{ marginBottom: spacing.lg }}>
        Mark <Text variant="bodyBold">{cow.earTag}</Text> as cull? She'll be removed from all
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
      await api.post(`/cows/${cow.id}/mark-${kind}`, { reason: notes.trim() || null });
      toast.success(`${cow.earTag} marked as ${kind === 'sold' ? 'Sold' : 'Dead'}`);
      onComplete();
    } catch (e: any) {
      toast.error(e?.message ?? 'Failed to update status');
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <Text variant="body" color={colors.textSecondary} style={{ marginBottom: spacing.lg }}>
        Mark <Text variant="bodyBold">{cow.earTag}</Text> as {kind}? This is final and cannot be
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

// ── main export ───────────────────────────────────────────────

interface Props {
  cow: Cow;
  onRefresh: () => void;
}

export function CowActionsSheet({ cow, onRefresh }: Props) {
  const [activeAction, setActiveAction] = useState<ActionKey | null>(null);
  const role = useAuthStore((s) => s.user?.role) ?? 'technician';
  const actions = getActions(cow, role);

  if (actions.length === 0) return null;

  const MODAL_TITLES: Record<ActionKey, string> = {
    enroll:          'Enroll in Protocol',
    inseminate:      'Record Artificial Insemination',
    heat_check:      'Record Heat Check',
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
  };

  const formProps = { cow, onCancel: dismiss, onComplete: complete };

  const renderForm = () => {
    switch (activeAction) {
      case 'inseminate':      return <InseminationForm {...formProps} />;
      case 'heat_check':      return <HeatCheckForm {...formProps} />;
      case 'pregnancy_check': return <PregnancyCheckForm {...formProps} />;
      case 'calving':         return <CalvingForm {...formProps} />;
      case 'vaccinate':       return <VaccinationForm {...formProps} />;
      case 'enroll':          return <EnrollForm {...formProps} />;
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
          <View style={styles.modalSheet}>
            <View style={styles.modalHandle} />
            <Text variant="heading" style={{ marginBottom: spacing.sm }}>
              {activeAction ? MODAL_TITLES[activeAction] : ''}
            </Text>
            <Text variant="caption" color={colors.textSecondary} style={{ marginBottom: spacing.xl }}>
              {cow.earTag}
            </Text>
            <ScrollView
              showsVerticalScrollIndicator={false}
              keyboardShouldPersistTaps="handled"
              contentContainerStyle={{ gap: spacing.sm }}
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
  toggleRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: spacing.sm,
    marginBottom: spacing.sm,
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
    paddingBottom: spacing.huge,
    maxHeight: '88%',
  },
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
  flex1: { flex: 1 },
  flex2: { flex: 2 },
});
