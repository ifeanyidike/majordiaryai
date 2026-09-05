"""Herd reproduction KPIs — the standard set, computed from this system's records.

Pure functions over plain records, no database. A farm has hundreds of cows,
not millions, so the whole herd's history fits in memory and every figure here
can be tested against a synthetic herd with a hand-computed answer. That is the
only way to be sure a rate is right: not by reading SQL, by asserting that ten
eligible cows, six served and three conceived produce 60 / 50 / 30.

Definitions follow the industry ones (DairyComp / DRMS conventions), stated in
KPI_DEFINITIONS on the client and in the docstrings below. Where this system's
own thresholds decide a definition — the 70-day voluntary waiting period, the
395-day heifer breeding age, the 50-day pregnancy-check warning — they are
imported from the modules that own them, never re-typed here.

Judgement (good / fair / poor) is made HERE, once, against published benchmark
bands, and returned with each figure. The app never re-derives a threshold. A
figure built on fewer than MIN_N records is returned but not judged: three cows
cannot tell you a conception rate.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from statistics import mean, median
from typing import Dict, List, Optional, Sequence

from app.services.report_catalog import PREGNANCY_WARNING_DAY
from app.services.status_engine import (
    ABANDONED_PROTOCOL_DAYS, FRESH_TO_OPEN_DAY, GESTATION_DAYS, HEAT_WINDOW,
    HEIFER_BREEDING_DAY,
)

CYCLE_DAYS = 21
CYCLES = 8                     # 24 weeks of 21-day cycles on the chart
TRAILING_DAYS = 365            # every rate is "last 12 months" unless stated
CALVING_INTERVAL_DAYS = 730    # needs two calvings, so a wider window
MIN_N = 5                      # below this a figure is shown, not judged
SEXED_MATCH_TOLERANCE = 21     # days either side of (calving - gestation)
TERMINAL = ("cull", "sold", "dead")
PREGNANT_STATES = ("pregnant", "dry")


# ── Plain records ────────────────────────────────────────────────────
# The router converts ORM rows to these; tests build them directly.

@dataclass
class CowRec:
    id: uuid.UUID
    status: str
    date_of_birth: Optional[date] = None
    last_insemination_id: Optional[uuid.UUID] = None
    last_insemination_date: Optional[date] = None
    # Imported herds carry this on the cow with no calving record behind it.
    last_calving_date: Optional[date] = None


@dataclass
class AiRec:
    id: uuid.UUID
    cow_id: uuid.UUID
    date: date
    attempt_number: int = 1
    semen_type: Optional[str] = None


@dataclass
class CheckRec:
    insemination_id: uuid.UUID
    cow_id: uuid.UUID
    check_date: date
    result: Optional[str]          # "pregnant" | "not_pregnant" | None


@dataclass
class CalvingRec:
    cow_id: uuid.UUID
    calving_date: date
    live_birth: bool = True
    still_birth: bool = False
    calf_sex: Optional[str] = None  # "female" | "male" | None
    # Made from cow.last_calving_date, not a recorded calving. A date we can
    # count days from, but not an outcome: it says nothing about the calf.
    synthetic: bool = False


@dataclass
class CullRec:
    cow_id: uuid.UUID
    cull_date: date


@dataclass
class NeedlingRec:
    cow_id: uuid.UUID
    scheduled_date: date
    completed: bool
    completed_date: Optional[date] = None
    enrollment_id: Optional[uuid.UUID] = None


@dataclass
class EnrollmentRec:
    cow_id: uuid.UUID
    start_date: date
    status: str                    # active | completed | completed_pending_ai | cancelled
    id: Optional[uuid.UUID] = None


@dataclass
class HeatCheckRec:
    insemination_id: uuid.UUID
    check_date: date


@dataclass
class HerdRecords:
    cows: List[CowRec] = field(default_factory=list)
    inseminations: List[AiRec] = field(default_factory=list)
    checks: List[CheckRec] = field(default_factory=list)
    calvings: List[CalvingRec] = field(default_factory=list)
    culls: List[CullRec] = field(default_factory=list)
    needling: List[NeedlingRec] = field(default_factory=list)
    enrollments: List[EnrollmentRec] = field(default_factory=list)
    heat_checks: List[HeatCheckRec] = field(default_factory=list)


# ── Judgement ────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Band:
    """Benchmark bands. `higher_is_better` decides which way the ladder runs."""
    good: float
    fair: float
    higher_is_better: bool
    target: str                   # the human sentence shown on the tile


# Published dairy-reproduction benchmarks. Kept together so a change is one
# edit and so the client can display the target next to the figure.
BANDS = {
    "pregnancy_rate_21d":    Band(20, 15, True,  "≥ 20% — 25%+ is excellent"),
    "service_rate_21d":      Band(65, 50, True,  "≥ 65% of eligible cows bred each cycle"),
    "conception_rate":       Band(40, 30, True,  "≥ 40% of checked breedings pregnant"),
    "first_service_rate":    Band(40, 30, True,  "≥ 40% on the first breeding"),
    "services_per_conception": Band(2.0, 2.5, False, "≤ 2.0 breedings per pregnancy"),
    "days_open":             Band(120, 150, False, "median ≤ 120 days"),
    "days_to_first_service": Band(85, 100, False, f"{FRESH_TO_OPEN_DAY}–85 days (VWP is {FRESH_TO_OPEN_DAY})"),
    "calving_interval_months": Band(13.5, 14.5, False, "≤ 13.5 months"),
    "stillbirth_rate":       Band(6, 10, False,  "≤ 6% of calvings"),
    "cull_rate":             Band(30, 38, False, "≤ 30% of the herd per year"),
    "protocol_on_time_rate": Band(95, 85, True,  "≥ 95% of shots on the scheduled day"),
    "protocol_completion_rate": Band(90, 75, True, "≥ 90% of protocols run to completion"),
    "heat_check_coverage":   Band(95, 80, True,  "every breeding checked on days 20–25"),
}


def _kpi(key: Optional[str], value: Optional[float], n: int, unit: str,
         decimals: int = 1) -> dict:
    """One figure with its judgement. `key=None` means informational only."""
    band = BANDS.get(key) if key else None
    if value is None:
        status = "na"
    elif n < MIN_N:
        status = "na"
    elif band is None:
        status = "info"
    else:
        if band.higher_is_better:
            status = "good" if value >= band.good else "fair" if value >= band.fair else "poor"
        else:
            status = "good" if value <= band.good else "fair" if value <= band.fair else "poor"
    return {
        "value": None if value is None else round(value, decimals),
        "n": n,
        "unit": unit,
        "status": status,
        "target": band.target if band else None,
    }


def _pct(num: int, den: int) -> Optional[float]:
    return None if den == 0 else 100.0 * num / den


# ── The engine ───────────────────────────────────────────────────────

class _Herd:
    """Indexes over the records, so each KPI reads as its definition."""

    def __init__(self, r: HerdRecords, today: date):
        self.today = today
        self.cows = r.cows
        self.ais = sorted(r.inseminations, key=lambda a: a.date)
        self.ais_by_cow: Dict[uuid.UUID, List[AiRec]] = defaultdict(list)
        for a in self.ais:
            self.ais_by_cow[a.cow_id].append(a)

        # Latest check per insemination decides its result.
        latest: Dict[uuid.UUID, CheckRec] = {}
        for c in r.checks:
            if c.result is None:
                continue
            prev = latest.get(c.insemination_id)
            if prev is None or c.check_date >= prev.check_date:
                latest[c.insemination_id] = c
        self.result_by_ai: Dict[uuid.UUID, str] = {k: v.result for k, v in latest.items()}
        self.pregnant_ais = {k for k, v in self.result_by_ai.items() if v == "pregnant"}

        # Imported herds set last_calving_date on the cow and write no calving
        # rows. Without treating that date as a calving, an imported farm has no
        # entry into the breeding pool, no days open and no days to first
        # service — an empty KPI screen for exactly the herds loaded first.
        # The synthesized row carries the date and nothing else.
        calvings = list(r.calvings)
        recorded = {(c.cow_id, c.calving_date) for c in calvings}
        for cow in r.cows:
            if cow.last_calving_date and (cow.id, cow.last_calving_date) not in recorded:
                calvings.append(CalvingRec(
                    cow_id=cow.id, calving_date=cow.last_calving_date, synthetic=True,
                ))
        self.calvings_by_cow: Dict[uuid.UUID, List[CalvingRec]] = defaultdict(list)
        for c in sorted(calvings, key=lambda c: c.calving_date):
            self.calvings_by_cow[c.cow_id].append(c)
        self.calvings = sorted(calvings, key=lambda c: c.calving_date)

        self.cull_date: Dict[uuid.UUID, date] = {}
        for c in r.culls:
            d = self.cull_date.get(c.cow_id)
            self.cull_date[c.cow_id] = c.cull_date if d is None else min(d, c.cull_date)
        # Left the herd with no dated record — any terminal status without a
        # cull row, which is every culled animal in an imported herd. We cannot
        # say when she left, so she is never in a historical denominator.
        # Conservative on purpose. (This covered only sold/dead at first, so a
        # status-cull cow with no row sat in every cycle's eligible pool.)
        self.left_undated = {
            c.id for c in self.cows if c.status in TERMINAL and c.id not in self.cull_date
        }
        self.cow_by_id = {c.id: c for c in self.cows}
        self.culls = r.culls
        self.needling = r.needling
        self.enrollments = r.enrollments
        self.heat_by_ai: Dict[uuid.UUID, int] = defaultdict(int)
        for h in r.heat_checks:
            self.heat_by_ai[h.insemination_id] += 1

    # ── state reconstruction ──

    def last_calving_before(self, cow_id: uuid.UUID, d: date) -> Optional[date]:
        prior = [c.calving_date for c in self.calvings_by_cow.get(cow_id, []) if c.calving_date < d]
        return prior[-1] if prior else None

    def pregnant_at(self, cow_id: uuid.UUID, d: date) -> bool:
        """Was she carrying a calf on day `d`?

        The most recent breeding before `d` decides: if it was confirmed
        pregnant and she has not calved since, she is pregnant. A later
        breeding after a confirmed one means the pregnancy was lost — the later
        breeding is the one that speaks.

        Imported herds arrive with a status but no check records, so a cow whose
        latest breeding has no result but who is currently pregnant/dry is taken
        as pregnant from that breeding onward. Without this every imported
        pregnant cow would sit in the eligible pool and drag the rate down.
        """
        prior = [a for a in self.ais_by_cow.get(cow_id, []) if a.date < d]
        if not prior:
            return False
        ai = prior[-1]
        calved_since = any(
            ai.date < c.calving_date < d for c in self.calvings_by_cow.get(cow_id, [])
        )
        if calved_since:
            return False
        if ai.id in self.pregnant_ais:
            return True
        cow = self.cow_by_id.get(cow_id)
        return bool(
            cow and ai.id not in self.result_by_ai
            and cow.status in PREGNANT_STATES and cow.last_insemination_id == ai.id
        )

    def eligible_at(self, cow: CowRec, start: date) -> bool:
        """In the breeding pool on `start`: present, past the VWP, not pregnant.

        Entry is FRESH_TO_OPEN_DAY after her last calving, or HEIFER_BREEDING_DAY
        after birth for an animal that has never calved. A cow with neither a
        calving nor a birth date has no entry point we can defend, so she is out.
        """
        if cow.id in self.left_undated:
            return False
        cull = self.cull_date.get(cow.id)
        if cull is not None and cull <= start:
            return False
        last_calv = self.last_calving_before(cow.id, start)
        if last_calv is not None:
            entry = last_calv + timedelta(days=FRESH_TO_OPEN_DAY)
        elif cow.date_of_birth is not None:
            entry = cow.date_of_birth + timedelta(days=HEIFER_BREEDING_DAY)
        else:
            return False
        if entry > start:
            return False
        return not self.pregnant_at(cow.id, start)

    # ── period helpers ──

    def window(self, days: int):
        return self.today - timedelta(days=days), self.today

    def ais_in(self, start: date, end: date) -> List[AiRec]:
        return [a for a in self.ais if start <= a.date <= end]


def compute_kpis(records: HerdRecords, today: date) -> dict:
    h = _Herd(records, today)
    out: dict = {
        "as_of": today.isoformat(),
        "period_days": TRAILING_DAYS,
        "cycle_days": CYCLE_DAYS,
        "assumptions": {
            "voluntary_waiting_period_days": FRESH_TO_OPEN_DAY,
            "heifer_breeding_age_days": HEIFER_BREEDING_DAY,
            "pregnancy_check_lag_days": PREGNANCY_WARNING_DAY,
            "gestation_days": GESTATION_DAYS,
            "min_records_to_judge": MIN_N,
        },
    }

    # ── 21-day cycles: pregnancy rate = service rate × conception rate ──
    cycles = []
    conf_elig = conf_served = conf_conc = 0
    for k in range(CYCLES):
        end = today - timedelta(days=CYCLE_DAYS * k)       # exclusive
        start = end - timedelta(days=CYCLE_DAYS)
        eligible = {c.id for c in h.cows if h.eligible_at(c, start)}
        in_cycle = [a for a in h.ais if start <= a.date < end and a.cow_id in eligible]
        served = {a.cow_id for a in in_cycle}
        conceived = {a.cow_id for a in in_cycle if a.id in h.pregnant_ais}
        # A breeding with no result counts as not pregnant — the conservative
        # convention — but the reader must be able to see that a low cycle is
        # "checks not entered" rather than "cows not conceiving".
        unchecked = {a.cow_id for a in in_cycle if a.id not in h.result_by_ai}
        # Checks land 30–50 days after breeding; a cycle newer than that is
        # not a bad cycle, it is an unknown one.
        pending = (today - end).days < PREGNANCY_WARNING_DAY
        n_e, n_s, n_c = len(eligible), len(served), len(conceived)
        cycles.append({
            "start": start.isoformat(), "end": (end - timedelta(days=1)).isoformat(),
            "eligible": n_e, "served": n_s, "conceived": n_c, "unchecked": len(unchecked),
            "service_rate": _pct(n_s, n_e), "conception_rate": _pct(n_c, n_s),
            "pregnancy_rate": _pct(n_c, n_e), "pending": pending,
        })
        if not pending:
            conf_elig += n_e; conf_served += n_s; conf_conc += n_c
    cycles.reverse()   # oldest first, for the chart
    for c in cycles:
        for key in ("service_rate", "conception_rate", "pregnancy_rate"):
            if c[key] is not None:
                c[key] = round(c[key], 1)
    out["cycles"] = cycles
    # Weighted over confirmed cycles: steadier than any single cycle and the
    # figure a herd is actually judged on.
    out["pregnancy_rate_21d"] = _kpi("pregnancy_rate_21d", _pct(conf_conc, conf_elig), conf_elig, "%")
    out["service_rate_21d"] = _kpi("service_rate_21d", _pct(conf_served, conf_elig), conf_elig, "%")

    # ── Conception, trailing 12 months, by month of breeding ──
    p_start, p_end = h.window(TRAILING_DAYS)
    period_ais = h.ais_in(p_start, p_end)
    checked = [a for a in period_ais if a.id in h.result_by_ai]
    pregnant = [a for a in checked if a.id in h.pregnant_ais]
    first = [a for a in checked if a.attempt_number == 1]
    first_preg = [a for a in first if a.id in h.pregnant_ais]

    months: Dict[str, dict] = {}
    cursor = date(today.year, today.month, 1)
    for _ in range(12):
        months[cursor.strftime("%Y-%m")] = {
            "month": cursor.strftime("%Y-%m"), "checked": 0, "pregnant": 0, "unchecked": 0,
        }
        cursor = (cursor.replace(day=1) - timedelta(days=1)).replace(day=1)
    for a in period_ais:
        key = a.date.strftime("%Y-%m")
        if key not in months:
            continue
        if a.id in h.result_by_ai:
            months[key]["checked"] += 1
            if a.id in h.pregnant_ais:
                months[key]["pregnant"] += 1
        else:
            months[key]["unchecked"] += 1
    by_month = sorted(months.values(), key=lambda m: m["month"])
    for m in by_month:
        r = _pct(m["pregnant"], m["checked"])
        m["rate"] = None if r is None else round(r, 1)

    out["conception"] = {
        "rate": _kpi("conception_rate", _pct(len(pregnant), len(checked)), len(checked), "%"),
        "first_service_rate": _kpi("first_service_rate", _pct(len(first_preg), len(first)), len(first), "%"),
        "services_per_conception": _kpi(
            "services_per_conception",
            None if not pregnant else len(period_ais) / len(pregnant),
            len(pregnant), "ratio", decimals=2,
        ),
        "unchecked_breedings": len(period_ais) - len(checked),
        "by_month": by_month,
    }

    # ── Timing ──
    days_open: List[int] = []
    for a in pregnant:
        calv = h.last_calving_before(a.cow_id, a.date)
        if calv is not None:                     # heifers have no days open
            days_open.append((a.date - calv).days)
    buckets = {"under_100": 0, "100_130": 0, "131_160": 0, "over_160": 0}
    for d in days_open:
        k = "under_100" if d < 100 else "100_130" if d <= 130 else "131_160" if d <= 160 else "over_160"
        buckets[k] += 1

    dfs: List[int] = []
    for c in h.calvings:
        if not (p_start <= c.calving_date <= p_end):
            continue
        later = [a for a in h.ais_by_cow.get(c.cow_id, []) if a.date > c.calving_date]
        if later:
            dfs.append((later[0].date - c.calving_date).days)

    intervals: List[int] = []
    ci_start = today - timedelta(days=CALVING_INTERVAL_DAYS)
    for cow_id, cs in h.calvings_by_cow.items():
        for prev, nxt in zip(cs, cs[1:]):
            if nxt.calving_date >= ci_start:
                intervals.append((nxt.calving_date - prev.calving_date).days)

    out["timing"] = {
        "days_open": {
            **_kpi("days_open", median(days_open) if days_open else None, len(days_open), "days", 0),
            "mean": round(mean(days_open), 1) if days_open else None,
            "buckets": buckets,
        },
        "days_to_first_service": _kpi(
            "days_to_first_service", median(dfs) if dfs else None, len(dfs), "days", 0),
        "calving_interval_months": _kpi(
            "calving_interval_months",
            (median(intervals) / 30.44) if intervals else None, len(intervals), "months"),
    }

    # ── Outcomes ──
    period_calvings = [
        c for c in h.calvings if not c.synthetic and p_start <= c.calving_date <= p_end
    ]
    still = [c for c in period_calvings if c.still_birth]

    # Sexed semen: does the product deliver? Find the breeding that produced
    # each calf — the cow's AI nearest to (calving − gestation), within a window
    # wide enough for normal variation and no wider — and split calf sex by
    # the semen type on that straw.
    by_semen: Dict[str, Dict[str, int]] = defaultdict(lambda: {"female": 0, "total": 0})
    for c in period_calvings:
        if not c.live_birth or c.calf_sex not in ("female", "male"):
            continue
        target = c.calving_date - timedelta(days=GESTATION_DAYS)
        near = [
            a for a in h.ais_by_cow.get(c.cow_id, [])
            if abs((a.date - target).days) <= SEXED_MATCH_TOLERANCE
        ]
        if not near:
            continue
        ai = min(near, key=lambda a: abs((a.date - target).days))
        semen = ai.semen_type or "unknown"
        by_semen[semen]["total"] += 1
        if c.calf_sex == "female":
            by_semen[semen]["female"] += 1
    sexed = by_semen.get("sexed", {"female": 0, "total": 0})
    conv = by_semen.get("conventional", {"female": 0, "total": 0})

    active_now = sum(1 for c in h.cows if c.status not in TERMINAL)
    period_culls = [c for c in h.culls if p_start <= c.cull_date <= p_end]

    overdue = 0
    for c in h.cows:
        if c.status != "inseminated" or not c.last_insemination_date:
            continue
        if (today - c.last_insemination_date).days >= PREGNANCY_WARNING_DAY \
                and c.last_insemination_id not in h.result_by_ai:
            overdue += 1

    out["outcomes"] = {
        "stillbirth_rate": _kpi(
            "stillbirth_rate", _pct(len(still), len(period_calvings)), len(period_calvings), "%"),
        "calvings": len(period_calvings),
        # Informational: sexed semen should run ~90% heifers, conventional ~48%.
        "sexed_semen_heifer_rate": _kpi(None, _pct(sexed["female"], sexed["total"]), sexed["total"], "%"),
        "conventional_heifer_rate": _kpi(None, _pct(conv["female"], conv["total"]), conv["total"], "%"),
        "cull_rate": _kpi(
            "cull_rate", _pct(len(period_culls), active_now + len(period_culls)),
            active_now + len(period_culls), "%"),
        "culls": len(period_culls),
        "overdue_pregnancy_checks": {"value": overdue, "n": overdue, "unit": "count",
                                     "status": "poor" if overdue else "good",
                                     "target": f"0 cows past day {PREGNANCY_WARNING_DAY} without a result"},
    }

    # ── Compliance: what this system uniquely knows ──
    # A cancelled protocol's ungiven shots are not misses: the cow bled, or was
    # inseminated on heat, and the schedule was correctly abandoned. Only the
    # shots of protocols still meant to run can be missed.
    cancelled = {e.id for e in h.enrollments if e.status == "cancelled" and e.id is not None}
    on_time = late = missed = 0
    for r in h.needling:
        if not (p_start <= r.scheduled_date <= p_end) or r.scheduled_date >= today:
            continue
        if not r.completed and r.enrollment_id in cancelled:
            continue
        if r.completed:
            if r.completed_date is None or r.completed_date <= r.scheduled_date:
                on_time += 1
            else:
                late += 1
        elif (today - r.scheduled_date).days > ABANDONED_PROTOCOL_DAYS:
            missed += 1
        # else: due in the last day or two — still open, not yet a miss
    judged = on_time + late + missed

    started = [e for e in h.enrollments if p_start <= e.start_date <= p_end]
    done = [e for e in started if e.status in ("completed", "completed_pending_ai")]
    cancelled = [e for e in started if e.status == "cancelled"]

    window_closed = [a for a in period_ais if (today - a.date).days > HEAT_WINDOW[1]]
    covered = [a for a in window_closed if h.heat_by_ai.get(a.id, 0) > 0]

    out["compliance"] = {
        "protocol_on_time_rate": {
            **_kpi("protocol_on_time_rate", _pct(on_time, judged), judged, "%"),
            "on_time": on_time, "late": late, "missed": missed,
        },
        "protocol_completion_rate": {
            **_kpi("protocol_completion_rate", _pct(len(done), len(done) + len(cancelled)),
                   len(done) + len(cancelled), "%"),
            "completed": len(done), "cancelled": len(cancelled),
            "active": len(started) - len(done) - len(cancelled),
        },
        "heat_check_coverage": _kpi(
            "heat_check_coverage", _pct(len(covered), len(window_closed)), len(window_closed), "%"),
    }
    return out
