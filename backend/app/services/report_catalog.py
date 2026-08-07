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
from app.services.status_engine import HEAT_WINDOW  # single source with checks.py

# ── thresholds (spec) ────────────────────────────────────────────────
PREGNANCY_REPORT_DAY = 30       # appears on the Pregnancy Report
PREGNANCY_WARNING_DAY = 50      # Pregnancy Check Warning
VACCINATION_WINDOW = (30, 50)   # days post calving
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

    def serialize(self, today: date) -> dict:
        cow = self.cow
        return {
            "cow_id": str(cow.id),
            "ear_tag": cow.ear_tag,
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
        }


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


def _timed_breeding(ctx: WorklistContext) -> List[ReportRow]:
    rows = []
    for cow in ctx.cows:
        row = ctx.breeding.get(str(cow.id))
        if not row:
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
    """Cows in the Insemination Program — a detected heat, or a heifer that
    reached breeding age (Master Structure: heifers at month 13 go straight to
    the Insemination Program).

    They are bred directly rather than re-enrolled in a protocol, so they do NOT
    belong on the Open report. Without this report they were on no work list at
    all: real work, invisible.
    """
    rows = []
    for cow in ctx.cows:
        if cow.status != CowStatus.open or cow.current_program != "Insemination":
            continue
        if cow.last_insemination_date:
            action = "Returned to the Insemination Program — breed her"
            detail = f"Heat detected · last AI {_fmt(cow.last_insemination_date)}"
        else:
            action = "Ready for first breeding — breed her"
            detail = "Reached breeding age · no prior AI"
        rows.append(ReportRow(
            cow=cow,
            action=action,
            detail=detail,
            record_kind="insemination",
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
        if cow.status != CowStatus.fresh:
            continue
        d = _days_since(cow.last_calving_date, ctx.today)
        if d is None or not (lo <= d <= hi):
            continue
        done = ctx.post_calving.get(str(cow.id))
        if done and cow.last_calving_date and \
                done["completed_on"] >= cow.last_calving_date:
            continue
        rows.append(ReportRow(
            cow=cow,
            action=f"Give 2cc vaccine shot (Day {d} post calving — complete by day {hi})",
            detail=f"Day {d} post calving · complete by day {hi}",
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
    """Cows that have just calved. The calving is already on record by the time
    she is Fresh, so the action is the post-calving check, not "record it".
    """
    rows = []
    for cow in ctx.cows:
        if cow.status != CowStatus.fresh:
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
        # Heat-detected cows are bred directly — they have their own report.
        if cow.current_program == "Insemination":
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
              subtitle=lambda n: f"{n} {'cow' if n == 1 else 'cows'} to check for heat"),
    ReportDef("timed-breeding", "Timed Breeding", "flask", "inseminated", True, _timed_breeding,
              subtitle=lambda n: f"{n} {'cow requires' if n == 1 else 'cows require'} insemination"),
    ReportDef("needling", "Needling Report", "fitness", "needling", True, _needling,
              subtitle=lambda n: f"{n} {'cow requires' if n == 1 else 'cows require'} injection"),
    ReportDef("insemination", "Insemination Program", "git-branch", "inseminated", True,
              _insemination_program,
              subtitle=lambda n: f"{n} {'cow' if n == 1 else 'cows'} returned for breeding"),
    # Recordable by technician or vet (client decision, 2026-08-06) — hence no
    # record_roles restriction. POST /checks/pregnancy enforces the same.
    ReportDef("pregnancy-check", "Pregnancy Report", "medkit", "inseminated", True,
              _pregnancy_check,
              subtitle=lambda n: f"{n} {'cow' if n == 1 else 'cows'} due for check"),
    ReportDef("vaccination", "Vaccination Report", "shield-checkmark", "fresh", True, _vaccination,
              subtitle=lambda n: f"{n} scheduled {'vaccination' if n == 1 else 'vaccinations'} due"),
    ReportDef("dry-report", "Dry Report", "moon", "dry", True, _dry,
              subtitle=lambda n: f"{n} {'cow' if n == 1 else 'cows'} to dry off"),
    ReportDef("post-calving", "Post Calving Report", "bandage", "fresh", True, _post_calving,
              subtitle=lambda n: f"{n} {'cow' if n == 1 else 'cows'} due the 2cc shot"),
    ReportDef("fresh", "Fresh / Calving Report", "heart", "fresh", True, _fresh,
              subtitle=lambda n: f"{n} freshly calved {'cow' if n == 1 else 'cows'}"),
    ReportDef("open-report", "Open Cow Report", "ellipse-outline", "open", True, _open,
              subtitle=lambda n: f"{n} {'cow' if n == 1 else 'cows'} to assess"),
    # ── reference lists (never counted as work) ──
    # Upcoming calvings are a heads-up, not a task: the spec's calving work is
    # the Fresh / Calving Report, triggered by the birth itself.
    ReportDef("calving-due", "Upcoming Calvings", "alarm", "pregnant", False, _calving_due),
    ReportDef("pregnant", "Pregnant Cow List", "heart-circle", "pregnant", False, _pregnant_list),
    ReportDef("open", "Open Cow List", "list-circle", "open", False, _open_list),
    ReportDef("cull", "Cull Cow List", "alert-circle", "cull", False, _cull_list),
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
