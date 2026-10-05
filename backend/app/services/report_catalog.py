"""The report catalog — ONE implementation of every report rule.

Previously each rule existed twice: as SQL here and as a predicate in the
client's `src/data/reports.ts`. Two copies of "which cows are on the Heat
Report" drift, and when they drift a cow silently disappears from the
technician's work list. The client now renders whatever this module returns and
owns no membership rule of its own.

Layers, per the Technician To-Do List spec:
  1. General To-Do  → which farms to visit today          (services/visits.py)
  2. Farm To-Do     → which reports have cows, and how many
  3. Report         → which cows, the exact action, where to record it

`build_worklist` returns all three in one payload so the counts a technician
sees at layer 2 can never disagree with the rows he finds at layer 3.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Callable, Dict, List, Optional

from app.models.models import Cow, CowStatus, HealthStatus
from app.services.protocols import protocol_label
# Single source with checks.py and the sweep's pregnancy-check reminder.
from app.services.status_engine import (
    HEAT_RECORDABLE_STATUSES, HEAT_WINDOW, PREGNANCY_REPORT_DAY, breeding_exclusion,
    breeding_list, is_milking,
)

# ── thresholds (spec) ────────────────────────────────────────────────
PREGNANCY_WARNING_DAY = 50      # Pregnancy Check Warning
VACCINATION_WINDOW = (30, 50)   # days post calving

# Statuses in which the post-calving 2cc shot is still owed. She has calved and
# has not calved again, so the shot is still this lactation's outstanding work
# — whether she is fresh, back to open, on a protocol, or already re-bred.
# Confirming a pregnancy (or drying her off) closes it: the window is months
# past by then and keeping her on the list only makes the list less trusted.
POST_CALVING_STATUSES = (
    CowStatus.fresh, CowStatus.open, CowStatus.needling, CowStatus.inseminated,
)
DRY_LEAD_DAYS = 7               # surfaced this far before day 223
CALVING_LEAD_DAYS = 3           # due-to-calve heads-up
FRESH_WINDOW_DAYS = 1           # "just calved" — day 0/1


def _days_since(d: Optional[date], today: date) -> Optional[int]:
    return None if d is None else (today - d).days


@dataclass
class ReportRow:
    cow: Cow
    action: str
    detail: str
    # Inline recording form, or None when the report is read-only for this user.
    record_kind: Optional[str] = None
    treatment: Optional[str] = None
    protocol: Optional[str] = None
    protocol_day: Optional[int] = None
    needling_record_id: Optional[str] = None
    needling_completed: bool = False
    overdue: bool = False
    # Shots hidden by the same-day overlap rule (Timed Breeding rows) — data,
    # not just prose, so clients and API consumers can act on it.
    missed_shots: int = 0
    # Additional pending injections beyond the one shown (Needling rows).
    also_pending: int = 0
    # The FARM does this one, not the technician (self-inject / self-vaccinate).
    # The row stays on the list because reminding them is the technician's job.
    farm_administered: bool = False

    def serialize(self, today: date) -> dict:
        cow = self.cow
        return {
            "cow_id": str(cow.id),
            "ear_tag": cow.ear_tag,
            # A farm that names its cows calls her by name; the tag stays,
            # because it is the identity every other system knows her by.
            "name": cow.name,
            "label": cow.label,
            "status": cow.status.value,
            "farm_id": str(cow.farm_id),
            "action": self.action,
            "detail": self.detail,
            "lactation_number": cow.lactation_number,
            "days_in_milk": _days_since(cow.last_calving_date, today),
            "days_post_ai": _days_since(cow.last_insemination_date, today),
            # Carried so a report row can open its recording form without a
            # second round trip for the cow (a pregnancy check needs the
            # insemination it refers to).
            "last_insemination_id": (str(cow.last_insemination_id)
                                     if cow.last_insemination_id else None),
            "last_insemination_date": (cow.last_insemination_date.isoformat()
                                       if cow.last_insemination_date else None),
            "last_calving_date": (cow.last_calving_date.isoformat()
                                  if cow.last_calving_date else None),
            "health_status": cow.health_status.value if cow.health_status else None,
            "record_kind": self.record_kind,
            "treatment": self.treatment,
            "protocol": self.protocol,
            "protocol_day": self.protocol_day,
            "needling_record_id": self.needling_record_id,
            "needling_completed": self.needling_completed,
            "overdue": self.overdue,
            "missed_shots": self.missed_shots,
            "also_pending": self.also_pending,
            "farm_administered": self.farm_administered,
        }


# Who may record an outcome, mirroring each router's require_roles(). Offering
# a form the API answers with 403 is worse than offering none — that mismatch
# is exactly what made a vet fill in an insemination only to be refused.
WORK_ROLES = ("admin", "technician")          # every recording route except…
PREGNANCY_ROLES = ("admin", "technician", "vet")  # …pregnancy checks


@dataclass
class ReportDef:
    type: str
    title: str
    icon: str
    status_key: str
    # Work reports are what a technician performs on a visit and are the only
    # ones counted in the Farm To-Do list; the rest are reference lists.
    is_work_report: bool
    build: Callable
    # Roles allowed to record an outcome inline. Empty = everyone who can see it.
    record_roles: tuple = ()
    subtitle: Optional[Callable[[int], str]] = None


# ── context passed to every builder ──────────────────────────────────

@dataclass
class WorklistContext:
    today: date
    role: str
    cows: List[Cow]
    # cow_id -> the needling record due today (non-final days)
    needling: Dict[str, dict] = field(default_factory=dict)
    # cow_id -> the timed-breeding row (final day, injection folded in)
    breeding: Dict[str, dict] = field(default_factory=dict)
    # cow_id -> a scheduled vaccination whose date has arrived
    vaccinations: Dict[str, dict] = field(default_factory=dict)
    # cow_id -> {"completed_on": date} of her latest completed vaccination
    post_calving: Dict[str, dict] = field(default_factory=dict)
    # cow_id -> a shot the FARMER gives soon, with no note written for him yet
    farmer_injections: Dict[str, dict] = field(default_factory=dict)
    # This farm gives the post-calving vaccine itself (farms.self_vaccinate).
    farm_self_vaccinate: bool = False
    # cow_id -> {"detected_on": date} for a heat seen TODAY. Today's Breed
    # Report is built from these (worklist_builder._heat_events_by_cow).
    heat_events: Dict[str, dict] = field(default_factory=dict)

    def may_record(self, definition: "ReportDef") -> bool:
        return not definition.record_roles or self.role in definition.record_roles


def _fmt(d: Optional[date]) -> str:
    return d.isoformat() if d else "—"


# ── builders ─────────────────────────────────────────────────────────

def _heat(ctx: WorklistContext) -> List[ReportRow]:
    lo, hi = HEAT_WINDOW
    rows = []
    for cow in ctx.cows:
        if cow.status != CowStatus.inseminated:
            continue
        d = _days_since(cow.last_insemination_date, ctx.today)
        if d is None or not (lo <= d <= hi):
            continue
        rows.append(ReportRow(
            cow=cow,
            action="Requires checking for heat",
            detail=f"AI {_fmt(cow.last_insemination_date)} · Day {d} of {lo}–{hi}",
            record_kind="heat",
        ))
    return rows


def _not_to_be_bred(cow: Cow) -> bool:
    """On the Do Not Breed or Do Not Inseminate list (Josh, Oct 2/4).

    Josh named the lists for heats, but a list that says "do not breed" cannot
    then be handed a breeding job by another report: the Open Cow Report's
    "choose a needling protocol" and a protocol's injections both end in a
    timed insemination, and the Timed Breeding Report and the Insemination
    Program ask for one outright. So she gets no breeding work anywhere, and
    the API refuses to enroll or inseminate her. A protocol already running
    when she was listed is left alone rather than cancelled: if she comes off
    the list that week it simply carries on. She stays on her lists, and on
    the Open Cow List, for reference.
    """
    return breeding_list(cow) is not None


def _breeding_today(ctx: WorklistContext, cow: Cow) -> bool:
    """Is she on Today's Breed Report? One answer for every report that asks."""
    heat = ctx.heat_events.get(str(cow.id))
    if not heat or cow.status not in HEAT_RECORDABLE_STATUSES:
        return False
    # Bred since the heat was seen: done, she leaves the report.
    if cow.last_insemination_date and cow.last_insemination_date >= heat["detected_on"]:
        return False
    return breeding_exclusion(cow, ctx.today) is None


def _breed_today(ctx: WorklistContext) -> List[ReportRow]:
    """Josh, Oct 4: any cow seen in heat -- on the Heat Report or anywhere
    else -- goes straight onto this report, and is bred today.

    Who is left off (breeding_exclusion): under 60 days post calving, Do Not
    Breed, Do Not Inseminate, Cull, under 13 months. She leaves when she is
    inseminated; if she is not, she is simply gone tomorrow, back to whatever
    she was doing, "assume nothing happened" -- which is why the report reads
    today's heat records rather than anything stored on the cow.
    """
    return [
        ReportRow(
            cow=cow,
            action="Seen in heat today — inseminate her today",
            detail="Heat detected today · drops off tomorrow if not bred",
            record_kind="insemination",
        )
        for cow in ctx.cows if _breeding_today(ctx, cow)
    ]


def _timed_breeding(ctx: WorklistContext) -> List[ReportRow]:
    rows = []
    for cow in ctx.cows:
        row = ctx.breeding.get(str(cow.id))
        if not row:
            continue
        # Put on a list after her protocol started: the insemination it was
        # building to must not be asked for.
        if _not_to_be_bred(cow):
            continue
        label = protocol_label(row["protocol"])
        context = f"{label}, Day {row['protocol_day']} — final day"
        if row["needling_completed"]:
            # Shot already given (enrollment completed_pending_ai): only the AI
            # is left. Never tell him to inject the same cow twice.
            action = f"Requires insemination today ({context})"
            treatment = None
        elif row.get("injection"):
            action = f"Give final {row['injection']} + inseminate today ({context})"
            treatment = row["injection"]
        else:
            action = f"Requires insemination today ({context})"
            treatment = None
        missed = row.get("missed_shots", 0)
        if missed:
            # These are hidden from the Needling report by the overlap rule —
            # if the combined row doesn't say so, nobody ever learns they exist.
            action += f" — note: {missed} earlier {'shot was' if missed == 1 else 'shots were'} missed"
        rows.append(ReportRow(
            cow=cow, action=action,
            detail=f"{label} · inseminate today"
                   + (f" · {missed} missed {'shot' if missed == 1 else 'shots'}" if missed else ""),
            missed_shots=missed,
            record_kind="insemination",
            treatment=treatment,
            protocol=row["protocol"],
            protocol_day=row["protocol_day"],
            needling_record_id=row["needling_record_id"],
            needling_completed=row["needling_completed"],
            overdue=row["days_overdue"] > 0,
        ))
    return rows


def _needling(ctx: WorklistContext) -> List[ReportRow]:
    rows = []
    for cow in ctx.cows:
        row = ctx.needling.get(str(cow.id))
        if not row:
            continue
        if _not_to_be_bred(cow):
            continue  # listed mid-protocol: the shots only lead to an AI she may not have
        label = protocol_label(row.get("protocol"))
        context = f"{label}, Day {row['protocol_day']}"
        treatment = row["treatment"] or ""
        # Not every scheduled step is an injection — Prostaglandin Heat
        # schedules heat examination/observation days.
        is_observation = "heat" in treatment.lower()
        what = treatment if is_observation else f"{treatment} injection"
        extra = row.get("also_pending", 0)
        rows.append(ReportRow(
            cow=cow,
            action=(f"Requires {what} today ({context})" if treatment
                    else f"Requires attention today ({context})")
                   + (f" — plus {extra} more pending {'shot' if extra == 1 else 'shots'}"
                      if extra else ""),
            detail=f"{label} · {'observation' if is_observation else 'injection'} due today"
                   + (f" · +{extra} pending" if extra else ""),
            also_pending=extra,
            record_kind="needling",
            treatment=row["treatment"],
            protocol=row.get("protocol"),
            protocol_day=row["protocol_day"],
            needling_record_id=row["id"],
            overdue=row["days_overdue"] > 0,
        ))
    return rows


def _insemination_program(ctx: WorklistContext) -> List[ReportRow]:
    """Heifers that reached breeding age (Master Structure: heifers at month
    13 go straight to the Insemination Program).

    They are bred directly rather than enrolled in a protocol, so they do NOT
    belong on the Open report. This report also used to carry every cow a
    heat had returned to breeding -- those are on Today's Breed Report now,
    for one day only (Josh, Oct 4), and migration 0021 moved the ones left
    over from the old rule to the Open Cow Report.
    """
    rows = []
    for cow in ctx.cows:
        if cow.status != CowStatus.open or cow.current_program != "Insemination":
            continue
        if _breeding_today(ctx, cow):
            continue  # on Today's Breed Report, which says it more urgently
        if _not_to_be_bred(cow):
            continue
        rows.append(ReportRow(
            cow=cow,
            action=("Ready for first breeding — breed her" if not cow.last_insemination_date
                    else "In the Insemination Program — breed her"),
            detail=("Reached breeding age · no prior AI" if not cow.last_insemination_date
                    else f"Last AI {_fmt(cow.last_insemination_date)}"),
            record_kind="insemination",
        ))
    return rows


def _farmer_injection(ctx: WorklistContext) -> List[ReportRow]:
    """Leave the farmer a note saying which cow needs which hormone.

    On a farm that gives its own last shot, the injection itself is not the
    technician's work -- but telling the farmer exactly what to give is, and
    it has to happen while he is standing there. The farm gets an automatic
    notification with the same facts; this is the human sentence that goes
    with it, and the row clears as soon as the note is written.
    """
    rows = []
    for cow in ctx.cows:
        row = ctx.farmer_injections.get(str(cow.id))
        if not row:
            continue
        if _not_to_be_bred(cow):
            continue
        due = row["scheduled_date"]
        days = row["days_until"]
        when = ("today" if days == 0 else
                "tomorrow" if days == 1 else
                f"in {days} days" if days > 0 else
                f"{-days} day(s) ago")
        rows.append(ReportRow(
            cow=cow,
            action=f"Leave a note for the farmer: {row['treatment']}, {when}",
            detail=f"Farm gives this one · {row['treatment']} due {_fmt(due)}",
            record_kind="farmer_note",
            needling_record_id=row["id"],
            treatment=row["treatment"],
            farm_administered=True,
            # Past its date with still no note: the farmer was never told.
            overdue=days < 0,
        ))
    return rows


def _pregnancy_check(ctx: WorklistContext) -> List[ReportRow]:
    rows = []
    for cow in ctx.cows:
        if cow.status != CowStatus.inseminated:
            continue
        d = _days_since(cow.last_insemination_date, ctx.today)
        if d is None or d < PREGNANCY_REPORT_DAY:
            continue
        warning = d >= PREGNANCY_WARNING_DAY
        rows.append(ReportRow(
            cow=cow,
            action=(f"Overdue for pregnancy check (Day {d})" if warning
                    else f"Due for pregnancy check (Day {d})"),
            detail=(f"AI {_fmt(cow.last_insemination_date)} · Day {d} · "
                    + ("Overdue — ready for diagnosis" if warning else "Due for check")),
            # Stripped for non-vets by build_reports via `record_roles`.
            record_kind="preg",
            overdue=warning,
        ))
    return rows


def _vaccination(ctx: WorklistContext) -> List[ReportRow]:
    """Spec: "schedule report most times" — a cow is *ready* after day 30 but
    waits for the vaccine's scheduled date. Driven by the scheduled record, so
    this is a different set from the Post Calving window below, not a duplicate
    of it.
    """
    rows = []
    for cow in ctx.cows:
        record = ctx.vaccinations.get(str(cow.id))
        if not record:
            continue
        rows.append(ReportRow(
            cow=cow,
            action=f"Administer {record.get('vaccine_name') or 'the scheduled vaccine'}"
                   f" (scheduled {record['scheduled_date']})",
            detail=f"Scheduled {record['scheduled_date']}"
                   + (f" · Day {d} post calving"
                      if (d := _days_since(cow.last_calving_date, ctx.today)) is not None else ""),
            record_kind="vaccination",
            overdue=record["days_overdue"] > 0,
        ))
    return rows


def _post_calving(ctx: WorklistContext) -> List[ReportRow]:
    """Spec: cows 30 days post calving, to be completed before day 50 — the 2cc
    shot. Recording ANY vaccination this lactation takes her off the report
    (auto-scheduled or ad-hoc); a shot from a previous calving does not count.
    """
    lo, hi = VACCINATION_WINDOW
    rows = []
    for cow in ctx.cows:
        # Every status in this lactation, not just fresh.
        #
        # Removing the day-50 cap was not enough on its own: the sweep flips
        # fresh -> open at day 70, and enrolling or breeding her moves her on
        # again. Each hop dropped a cow whose mandatory shot was never given
        # off every work list — later than before, but just as silently.
        #
        # The shot belongs to the lactation, so she stays visible for the whole
        # of it: until it is recorded, or she calves again (which moves
        # last_calving_date and re-arms the check below). Terminal statuses and
        # animals that have not calved are excluded, and `dry`/`pregnant` are
        # too — by then the window is long past and chasing it is noise on a
        # list that has to stay actionable.
        if cow.status not in POST_CALVING_STATUSES:
            continue
        d = _days_since(cow.last_calving_date, ctx.today)
        # No upper bound. Windowing this at day 50 meant a cow whose mandatory
        # 2cc shot was never given silently dropped off every work list on day
        # 51 — the miss disappeared instead of escalating.
        if d is None or d < lo:
            continue
        done = ctx.post_calving.get(str(cow.id))
        if done and cow.last_calving_date and \
                done["completed_on"] >= cow.last_calving_date:
            continue
        late = d > hi
        # On a farm that vaccinates its own cows the shot is still owed and
        # still tracked here -- what changes is whose hands give it. The
        # technician's job becomes making sure the farmer knows, and recording
        # it once they have.
        mine = not ctx.farm_self_vaccinate
        rows.append(ReportRow(
            cow=cow,
            action=(
                (f"OVERDUE: 2cc vaccine shot still not given (Day {d} — was due by day {hi})"
                 if late
                 else f"Give 2cc vaccine shot (Day {d} post calving — complete by day {hi})")
                if mine else
                (f"OVERDUE: remind the farm to give her 2cc vaccine (Day {d} — was due by day {hi})"
                 if late
                 else f"Farm gives this 2cc vaccine — remind them (Day {d}, complete by day {hi})")
            ),
            farm_administered=not mine,
            detail=(f"Day {d} post calving · {d - hi} days past the day-{hi} deadline"
                    if late else f"Day {d} post calving · complete by day {hi}"),
            record_kind="vaccination",
            overdue=d >= hi - 5,
        ))
    return rows


def _dry(ctx: WorklistContext) -> List[ReportRow]:
    """Day 223 is when the work exists — but the lifecycle sweep flips
    pregnant → dry on exactly that day, so a `pregnant`-only filter would drop
    her the moment she becomes actionable. Cover both sides of the transition.
    """
    rows = []
    for cow in ctx.cows:
        if cow.dry_date is None or cow.dry_off_confirmed_date is not None:
            continue  # already confirmed moved to the dry pen — work is done
        delta = (cow.dry_date - ctx.today).days
        if cow.status == CowStatus.pregnant and 0 <= delta <= DRY_LEAD_DAYS:
            rows.append(ReportRow(
                cow=cow,
                action=f"Dry off {_fmt(cow.dry_date)} — notify farmer to change pen",
                detail=f"Dry {_fmt(cow.dry_date)} · Due {_fmt(cow.due_date)}",
                record_kind="dry_off",
            ))
        elif cow.status == CowStatus.dry and delta <= 0:
            rows.append(ReportRow(
                cow=cow,
                action=f"Dried off {_fmt(cow.dry_date)} — confirm the pen change",
                detail=f"Dry {_fmt(cow.dry_date)} · Due {_fmt(cow.due_date)}",
                record_kind="dry_off",
                overdue=delta < 0,
            ))
    return rows


def _calving_due(ctx: WorklistContext) -> List[ReportRow]:
    """Cows about to calve. This is the report that produces work — the calving
    itself is recorded here when it happens.
    """
    rows = []
    for cow in ctx.cows:
        if cow.status not in (CowStatus.pregnant, CowStatus.dry) or cow.due_date is None:
            continue
        delta = (cow.due_date - ctx.today).days
        if delta > CALVING_LEAD_DAYS:
            continue
        rows.append(ReportRow(
            cow=cow,
            action=("Overdue to calve — record the calving when she does"
                    if delta < 0 else f"Due to calve {_fmt(cow.due_date)}"),
            detail=f"Due {_fmt(cow.due_date)} · Dry {_fmt(cow.dry_date)}",
            record_kind="calving",
            overdue=delta < 0,
        ))
    return rows


def _fresh(ctx: WorklistContext) -> List[ReportRow]:
    """Cows that have just calved -- and cows the day-283 sweep ASSUMES have.

    For a recorded calving the action is the post-calving check. For an
    assumed one it is recording the calving itself: until then her lactation
    is one short, her calving date is a guess, and her calf does not exist.
    """
    rows = []
    for cow in ctx.cows:
        if cow.status != CowStatus.fresh:
            continue
        if cow.calving_assumed:
            # No window: this stays on the list until somebody records it,
            # because the error it represents does not age out.
            rows.append(ReportRow(
                cow=cow,
                action="Due date has passed — record the calving",
                detail=f"Due {_fmt(cow.last_calving_date)} · calving not recorded yet",
                record_kind="calving",
            ))
            continue
        d = _days_since(cow.last_calving_date, ctx.today)
        if d is None or d > FRESH_WINDOW_DAYS:
            continue
        rows.append(ReportRow(
            cow=cow,
            # The calving is already recorded (that's how she became Fresh) —
            # this row is the post-calving check, not a data-entry task.
            action=f"Just calved {_fmt(cow.last_calving_date)} — check cow and calf",
            detail=f"Calved {_fmt(cow.last_calving_date)} · Day {d}",
        ))
    return rows


def _open(ctx: WorklistContext) -> List[ReportRow]:
    rows = []
    for cow in ctx.cows:
        if cow.status != CowStatus.open:
            continue
        # Breeding-age heifers have their own report.
        if cow.current_program == "Insemination":
            continue
        # Seen in heat today: she is bred, not assessed for a protocol. If she
        # isn't bred today she is back here tomorrow, as if nothing happened.
        if _breeding_today(ctx, cow):
            continue
        if _not_to_be_bred(cow):
            continue
        sick = cow.health_status == HealthStatus.sick
        if sick and cow.recheck_due_date and cow.recheck_due_date > ctx.today:
            continue  # recheck every 7 days, not every day
        days_open = _days_since(cow.last_calving_date, ctx.today)
        rows.append(ReportRow(
            cow=cow,
            action=(f"Recheck health today (marked sick, recheck due {_fmt(cow.recheck_due_date)})"
                    if sick else "Assess health and choose a needling protocol"),
            detail=(f"{days_open} days open · " if days_open is not None else "")
                   + ("Sick — recheck due" if sick else "Healthy — ready to breed"),
            record_kind="enroll",
        ))
    return rows


def _pregnant_list(ctx: WorklistContext) -> List[ReportRow]:
    return [
        ReportRow(
            cow=cow, action="",
            detail=f"Due {_fmt(cow.due_date)} · Dry {_fmt(cow.dry_date)} · "
                   f"{_days_since(cow.last_insemination_date, ctx.today) or 0} days pregnant",
        )
        for cow in ctx.cows
        if cow.status in (CowStatus.pregnant, CowStatus.dry)
    ]


def _open_list(ctx: WorklistContext) -> List[ReportRow]:
    return [
        ReportRow(
            cow=cow, action="",
            detail=f"Calved {_fmt(cow.last_calving_date)}"
                   + (f" · {protocol_label(cow.current_program)}"
                      if cow.status == CowStatus.needling and cow.current_program else ""),
        )
        for cow in ctx.cows
        if cow.status in (CowStatus.open, CowStatus.needling)
    ]


def _breeding_list(flag: str):
    """The Do Not Breed / Do Not Inseminate lists themselves -- Josh speaks of
    cows being "on the Do Not Breed list", so the list has to be somewhere a
    person can read it, not only a flag on each cow."""
    def build(ctx: WorklistContext) -> List[ReportRow]:
        return [
            ReportRow(
                cow=cow, action="",
                detail=f"{cow.status.value.capitalize()}"
                       + (f" · {_days_since(cow.last_calving_date, ctx.today)} days in milk"
                          if is_milking(cow) and cow.last_calving_date else ""),
            )
            for cow in ctx.cows
            if getattr(cow, flag) and cow.status not in (CowStatus.sold, CowStatus.dead)
        ]
    return build


def _cull_list(ctx: WorklistContext) -> List[ReportRow]:
    return [
        ReportRow(cow=cow, action="", detail=f"Exited {_fmt(cow.exit_date)}"
                                             + (f" · {cow.exit_reason}" if cow.exit_reason else ""))
        for cow in ctx.cows
        if cow.status == CowStatus.cull
    ]


# ── the catalog ──────────────────────────────────────────────────────

REPORTS: List[ReportDef] = [
    ReportDef("heat", "Heat Report", "flame", "heat", True, _heat,
              record_roles=WORK_ROLES,
              subtitle=lambda n: f"{n} {'cow' if n == 1 else 'cows'} to check for heat"),
    # Straight after the Heat Report, whose "Yes" fills it (Josh, Oct 4).
    ReportDef("breed-today", "Today's Breed Report", "flash", "heat", True, _breed_today,
              record_roles=WORK_ROLES,
              subtitle=lambda n: f"{n} {'cow' if n == 1 else 'cows'} in heat to breed today"),
    # "Timed Breeding Report" in full: Josh looked for that name and did not
    # recognise the shortened "Timed Breeding" as it (Oct 2).
    ReportDef("timed-breeding", "Timed Breeding Report", "flask", "inseminated", True, _timed_breeding,
              record_roles=WORK_ROLES,
              subtitle=lambda n: f"{n} {'cow requires' if n == 1 else 'cows require'} insemination"),
    ReportDef("needling", "Injection Report", "fitness", "needling", True, _needling,
              record_roles=WORK_ROLES,
              subtitle=lambda n: f"{n} {'cow requires' if n == 1 else 'cows require'} injection"),
    ReportDef("farmer-injection", "Farmer Injection", "create", "needling", True,
              _farmer_injection, record_roles=WORK_ROLES,
              subtitle=lambda n: f"{n} {'note' if n == 1 else 'notes'} to leave for the farmer"),
    ReportDef("insemination", "Insemination Program", "git-branch", "inseminated", True,
              _insemination_program, record_roles=WORK_ROLES,
              subtitle=lambda n: f"{n} ready for first breeding"),
    # Recordable by technician or vet (client decision, 2026-08-06) — hence no
    # record_roles restriction. POST /checks/pregnancy enforces the same.
    ReportDef("pregnancy-check", "Pregnancy Report", "medkit", "inseminated", True,
              _pregnancy_check, record_roles=PREGNANCY_ROLES,
              subtitle=lambda n: f"{n} {'cow' if n == 1 else 'cows'} due for check"),
    ReportDef("vaccination", "Scheduled Vaccinations", "shield-checkmark", "fresh", True, _vaccination,
              record_roles=WORK_ROLES,
              subtitle=lambda n: f"{n} scheduled {'vaccination' if n == 1 else 'vaccinations'} due"),
    ReportDef("dry-report", "Dry Report", "moon", "dry", True, _dry,
              record_roles=WORK_ROLES,
              subtitle=lambda n: f"{n} {'cow' if n == 1 else 'cows'} to dry off"),
    ReportDef("post-calving", "Vaccine Report", "bandage", "fresh", True, _post_calving,
              record_roles=WORK_ROLES,
              subtitle=lambda n: f"{n} {'cow' if n == 1 else 'cows'} due the 2cc shot"),
    # record_roles because assumed calvings now carry a calving form, and only
    # admins and technicians may record one (routers/calving.py) — offering
    # it to a farm manager would end in a 403.
    ReportDef("fresh", "Fresh / Calving Report", "heart", "fresh", True, _fresh,
              record_roles=WORK_ROLES,
              subtitle=lambda n: f"{n} freshly calved {'cow' if n == 1 else 'cows'}"),
    ReportDef("open-report", "Open Cow Report", "ellipse-outline", "open", True, _open,
              record_roles=WORK_ROLES,
              subtitle=lambda n: f"{n} {'cow' if n == 1 else 'cows'} to assess"),
    # ── reference lists (never counted as work) ──
    # Upcoming calvings are a heads-up, not a task: the spec's calving work is
    # the Fresh / Calving Report, triggered by the birth itself.
    ReportDef("calving-due", "Upcoming Calvings", "alarm", "pregnant", False, _calving_due,
              # record_kind is "calving" here, and POST /calving is
              # admin+technician — without this a vet filled in the form and
              # was 403'd, the same mismatch reported from testing.
              record_roles=WORK_ROLES),
    ReportDef("pregnant", "Pregnant Cow List", "heart-circle", "pregnant", False, _pregnant_list),
    ReportDef("open", "Open Cow List", "list-circle", "open", False, _open_list),
    ReportDef("cull", "Cull Cow List", "alert-circle", "cull", False, _cull_list),
    ReportDef("do-not-breed", "Do Not Breed List", "ban", "cull", False,
              _breeding_list("do_not_breed")),
    ReportDef("do-not-inseminate", "Do Not Inseminate List", "remove-circle", "cull", False,
              _breeding_list("do_not_inseminate")),
]

REPORTS_BY_TYPE = {r.type: r for r in REPORTS}


def build_reports(ctx: WorklistContext, work_only: bool = False) -> List[dict]:
    """Every report that currently has cows, in catalog order."""
    out = []
    for definition in REPORTS:
        if work_only and not definition.is_work_report:
            continue
        rows = definition.build(ctx)
        if not rows:
            continue
        may_record = ctx.may_record(definition)
        out.append({
            "type": definition.type,
            "title": definition.title,
            "icon": definition.icon,
            "status_key": definition.status_key,
            "is_work_report": definition.is_work_report,
            "count": len(rows),
            "subtitle": definition.subtitle(len(rows)) if definition.subtitle
                        else f"{len(rows)} {'cow' if len(rows) == 1 else 'cows'}",
            "can_record": may_record,
            "cows": [
                {**row.serialize(ctx.today),
                 # A form the caller may not submit is worse than no form: the
                 # API would 403 after they filled it in.
                 "record_kind": row.record_kind if may_record else None}
                for row in rows
            ],
        })
    return out
