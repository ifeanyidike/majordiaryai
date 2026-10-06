"""Read a DairyComp 305 herd list into the app's cow records.

DairyComp is the herd software these farms already run, and its LIST export is
how a farm's herd arrives (the first real one came in Oct 2026). The generic
importer in routers/imports.py cannot take it as-is:

  * it gives COUNTS as of the day it was exported -- days in milk, days since
    last heat, days open -- not dates, so every date has to be counted back
    from that day, not from the day it is imported;
  * reproductive status is DairyComp's own vocabulary (PREG, BRED, NO BRED,
    OK/OPEN, FRESH, DRY, HEIFER, BULLCAF, DNB);
  * a bred or pregnant cow needs an insemination RECORD here, not only a
    date: the heat check and pregnancy check are both filed against one, so
    without it the technician and vet could not record her checks at all.

The mapping is a pure function of the rows, tested without a database
(tests/test_dairycomp_import.py); write_plan() adds the result to a farm and
scripts/import_dairycomp.py drives both.

Dates the app derives (due, dry-off) follow Josh's rules -- 283 and 223 days
from the breeding -- not DairyComp's. DairyComp is only trusted for the facts:
when she calved, when she was bred, when she was dried off.
"""

import re
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Dict, Iterable, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Cow, CowStatus, Insemination
from app.services.status_engine import (
    CALF_TO_HEIFER_DAY, DRY_OFF_DAY, FRESH_TO_OPEN_DAY, GESTATION_DAYS,
    HEIFER_BREEDING_DAY, adjust_to_breeding_day,
)

# DairyComp's own pregnancy length and dry-off lead. Its DRY50 column is its
# due date less 50 days; both numbers were read off the first real export (158 of
# 160 pregnant/dry cows agree on one export date only with these values).
DC_GESTATION_DAYS = 280
DC_DRY50_LEAD_DAYS = 50

# A dairy heifer calves at about two years old. One listed as never calved at
# well past that is almost always an animal that left the herd and was never
# removed in DairyComp (the first real export: 176 "heifers" aged 3-8). They
# are held out for the farm to confirm rather than put on the breeding list.
OLDEST_UNCALVED_DAYS = 30 * 30  # ~30 months

# Statuses whose cow is carrying a breeding: she gets an insemination record.
_BRED = ("BRED", "PREG", "DRY")
# Calved, not carrying: fresh until day 70 (on a breeding day), then open.
_CALVED_OPEN = ("FRESH", "NO BRED", "OK/OPEN")


class RowProblem(Exception):
    """A row that cannot be imported, phrased for whoever reads the summary."""


@dataclass
class CowPlan:
    """One animal as the app will hold her."""
    row: int
    ear_tag: str
    status: CowStatus
    dc_status: str
    lactation_number: int = 0
    date_of_birth: Optional[date] = None
    last_calving_date: Optional[date] = None
    current_program: Optional[str] = None
    sire: Optional[str] = None
    maternal_sire: Optional[str] = None
    do_not_breed: bool = False
    # The breeding she is carrying (BRED/PREG/DRY), and which attempt it was.
    insemination_date: Optional[date] = None
    attempt_number: int = 1
    due_date: Optional[date] = None
    dry_date: Optional[date] = None
    dry_off_confirmed_date: Optional[date] = None

    def cow_fields(self) -> dict:
        """Columns for the Cow row (the insemination is written separately)."""
        return {
            "ear_tag": self.ear_tag, "status": self.status,
            "lactation_number": self.lactation_number,
            "date_of_birth": self.date_of_birth,
            "last_calving_date": self.last_calving_date,
            "last_insemination_date": self.insemination_date,
            "current_program": self.current_program,
            "sire": self.sire, "maternal_sire": self.maternal_sire,
            "do_not_breed": self.do_not_breed,
            "due_date": self.due_date, "dry_date": self.dry_date,
            "dry_off_confirmed_date": self.dry_off_confirmed_date,
        }


@dataclass
class Held:
    """An animal deliberately left out, and why."""
    row: int
    ear_tag: str
    reason: str
    age_months: Optional[int] = None


@dataclass
class Plan:
    cows: List[CowPlan] = field(default_factory=list)
    skipped: List[Held] = field(default_factory=list)
    # (row, ear tag or None, what is wrong) -- could not be read
    problems: List[Tuple[int, Optional[str], str]] = field(default_factory=list)


# ── cell readers ─────────────────────────────────────────────────────

def _text(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float):
        return str(int(v)) if v == int(v) else str(v)
    return str(v).strip()


def _int(v) -> Optional[int]:
    t = _text(v)
    if not t:
        return None
    try:
        return int(float(t))
    except ValueError:
        raise RowProblem(f"expected a number, got {t!r}")


_DMY = re.compile(r"^\s*(\d{1,2})\s*/\s*(\d{1,2})\s*/\s*(\d{2}|\d{4})\s*$")


def parse_date(v, *, not_after: date) -> Optional[date]:
    """DairyComp's D/M/YY ("15/ 7/20" is 15 July 2020). A two-digit year that
    would land after `not_after` is last century."""
    t = _text(v)
    if not t:
        return None
    m = _DMY.match(t)
    if not m:
        raise RowProblem(f"could not read the date {t!r} (expected D/M/YY)")
    day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if year < 100:
        year += 2000
        if year > not_after.year:
            year -= 100
    try:
        return date(year, month, day)
    except ValueError:
        raise RowProblem(f"{t!r} is not a real date")


def normalize_headers(headers: Iterable) -> List[str]:
    return [_text(h).upper() for h in headers]


def is_animal_row(row: Dict) -> bool:
    """False for the blank line and the "Total: 772" footer DairyComp appends."""
    first = _text(row.get("ID"))
    return bool(first) and not first.lower().startswith("total")


# ── the export date ──────────────────────────────────────────────────

def derive_export_date(rows: List[Dict]) -> Optional[date]:
    """The day the list was exported, read back out of the list itself.

    For a pregnant or dry cow DairyComp prints both her DRY50 date (its due
    date less 50) and DSLH (days since the heat she was bred on), so
    DRY50 + 50 - 280 + DSLH is the export day. Most cows agree exactly; a cow
    with a later heat recorded disagrees, so the most common answer wins.
    """
    votes: Counter = Counter()
    for r in rows:
        if not is_animal_row(r) or _text(r.get("RPRO")).upper() not in ("PREG", "DRY"):
            continue
        try:
            dry50 = parse_date(r.get("DRY50"), not_after=date.max)
            dslh = _int(r.get("DSLH"))
        except RowProblem:
            continue
        if dry50 and dslh:
            votes[dry50 + timedelta(days=DC_DRY50_LEAD_DAYS - DC_GESTATION_DAYS + dslh)] += 1
    return votes.most_common(1)[0][0] if votes else None


# ── the mapping ──────────────────────────────────────────────────────

def plan_rows(rows: List[Dict], export_date: date, today: date,
              oldest_uncalved_days: Optional[int] = OLDEST_UNCALVED_DAYS) -> Plan:
    """Every row of the export, mapped to how the app will hold her.

    `export_date` dates the counts; `today` decides the status, because the
    import happens after the export and the app's clock has moved on (a calf
    can have become a heifer in between).
    """
    plan = Plan()
    animals = [(i + 2, r) for i, r in enumerate(rows) if is_animal_row(r)]
    sire_of = {_text(r.get("ID")): _text(r.get("SIRE")) or None for _, r in animals}
    seen: Dict[str, int] = {}

    for row_no, r in animals:
        tag = _text(r.get("ID"))
        dc = _text(r.get("RPRO")).upper()
        try:
            if tag in seen:
                raise RowProblem(f"ID {tag} also appears on row {seen[tag]}")
            seen[tag] = row_no
            if dc == "BULLCAF":
                plan.skipped.append(Held(row_no, tag, "bull calf — the app keeps records "
                                                      "for heifers and cows only"))
                continue
            cow = _plan_cow(row_no, tag, dc, r, sire_of, export_date, today)
            if (oldest_uncalved_days is not None and cow.lactation_number == 0
                    and cow.status in (CowStatus.heifer, CowStatus.open)
                    and cow.date_of_birth
                    and (today - cow.date_of_birth).days > oldest_uncalved_days):
                plan.skipped.append(Held(
                    row_no, tag, "never calved, yet well past calving age — "
                                 "confirm she is still on the farm",
                    age_months=(today - cow.date_of_birth).days // 30,
                ))
                continue
            plan.cows.append(cow)
        except RowProblem as e:
            plan.problems.append((row_no, tag or None, str(e)))
    return plan


def _plan_cow(row_no: int, tag: str, dc: str, r: Dict, sire_of: Dict[str, Optional[str]],
              E: date, today: date) -> CowPlan:
    lact = _int(r.get("LACT")) or 0
    dim = _int(r.get("DIM")) or 0
    dslh = _int(r.get("DSLH")) or 0
    dob = parse_date(r.get("BDAT"), not_after=E)
    dam = _text(r.get("DID"))
    cow = CowPlan(
        row=row_no, ear_tag=tag, status=CowStatus.open, dc_status=dc,
        lactation_number=lact, date_of_birth=dob,
        sire=_text(r.get("SIRE")) or None,
        maternal_sire=sire_of.get(dam) if dam and dam != "0" else None,
        # DairyComp's DNB is the list Josh named (Oct 2/4).
        do_not_breed=(dc == "DNB"),
    )
    # A calving date only exists for an animal that has calved. DIM 0 on a
    # first-lactation animal is a heifer, not a cow that calved today.
    if lact > 0 and dim > 0:
        cow.last_calving_date = E - timedelta(days=dim)

    if dc in _BRED:
        cow.insemination_date = _breeding_date(dc, r, dslh, E)
        cow.attempt_number = max(_int(r.get("TBRD")) or 1, 1)
        cow.due_date = cow.insemination_date + timedelta(days=GESTATION_DAYS)
        if dc == "BRED":
            cow.status = CowStatus.inseminated
            cow.due_date = None  # only a confirmed pregnancy has a due date
        elif dc == "PREG":
            cow.status = CowStatus.pregnant
            cow.dry_date = cow.insemination_date + timedelta(days=DRY_OFF_DAY)
        else:  # DRY: she is already in the dry pen
            cow.status = CowStatus.dry
            dried = parse_date(r.get("DDAT"), not_after=E)
            cow.dry_date = dried or cow.insemination_date + timedelta(days=DRY_OFF_DAY)
            cow.dry_off_confirmed_date = dried
    elif lact > 0 and dc in _CALVED_OPEN + ("DNB",):
        if not cow.last_calving_date:
            raise RowProblem(f"{dc} with no days in milk — cannot date her calving")
        entry = adjust_to_breeding_day(cow.last_calving_date + timedelta(days=FRESH_TO_OPEN_DAY))
        cow.status = CowStatus.open if entry <= today else CowStatus.fresh
    elif dc == "HEIFER" or (lact == 0 and dc in _CALVED_OPEN + ("DNB",)):
        # A heifer is "NO BRED" or "OK/OPEN" to DairyComp when she has never
        # been bred, or was bred and did not take -- an unbred heifer either
        # way, so her age decides what she is here.
        if not dob:
            raise RowProblem("heifer with no birth date — cannot tell calf from heifer")
        age = (today - dob).days
        if age < CALF_TO_HEIFER_DAY:
            cow.status = CowStatus.calf
        elif age < HEIFER_BREEDING_DAY or cow.do_not_breed:
            cow.status = CowStatus.heifer
        else:
            # Master Structure: at 13 months she goes to the Insemination
            # Program -- set here, not left to the sweep, which would raise a
            # "reached breeding age" notification for each of them at once.
            cow.status = CowStatus.open
            cow.current_program = "Insemination"
    else:
        raise RowProblem(f"status {dc or '(blank)'!r} is not a DairyComp status we know")

    for label, d in (("birth", dob), ("calving", cow.last_calving_date),
                     ("breeding", cow.insemination_date)):
        if d and d > E:
            raise RowProblem(f"{label} date {d} is after the export date {E}")
    return cow


def _breeding_date(dc: str, r: Dict, dslh: int, E: date) -> date:
    """When she was bred. For PREG/DRY, DairyComp's own DRY50 pins it best
    (a heat recorded after she was bred resets DSLH but not DRY50)."""
    if dc in ("PREG", "DRY"):
        dry50 = parse_date(r.get("DRY50"), not_after=date.max)
        if dry50:
            return dry50 + timedelta(days=DC_DRY50_LEAD_DAYS - DC_GESTATION_DAYS)
    if dslh > 0:
        return E - timedelta(days=dslh)
    raise RowProblem(f"{dc} with no days since breeding — cannot date her breeding")


# ── writing ──────────────────────────────────────────────────────────

async def write_plan(db: AsyncSession, farm_id, plan: Plan,
                     export_date: date) -> Tuple[List[CowPlan], List[str]]:
    """Add the planned animals to a farm. Flushes; the caller commits.

    Only ever adds: an ID already on the farm is left exactly as it is, so the
    app's own records (checks, breedings recorded since) always win over an
    older export, and re-running a later export adds just the new animals.
    Returns (added, ear tags left alone).
    """
    existing = set((await db.execute(
        select(Cow.ear_tag).where(Cow.farm_id == farm_id)
    )).scalars())
    added: List[CowPlan] = []
    already: List[str] = []
    for p in plan.cows:
        if p.ear_tag in existing:
            already.append(p.ear_tag)
            continue
        cow = Cow(id=uuid.uuid4(), farm_id=farm_id, **p.cow_fields())
        db.add(cow)
        if p.insemination_date:
            # The record her heat check and pregnancy check are filed against.
            ins = Insemination(
                id=uuid.uuid4(), cow_id=cow.id, date=p.insemination_date,
                attempt_number=p.attempt_number,
                notes=f"Imported from DairyComp (export of {export_date}); "
                      "bull not in the export",
            )
            db.add(ins)
            await db.flush()
            cow.last_insemination_id = ins.id
        added.append(p)
    await db.flush()
    return added, already
