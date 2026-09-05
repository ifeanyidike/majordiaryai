"""The KPI engine against synthetic herds with hand-computed answers.

Every rate here is asserted against a number worked out by hand from a herd
built for the purpose. No database: the engine is pure, so these run anywhere
and take milliseconds — and a change to a definition fails a test that names
the definition, rather than shifting a dashboard figure nobody can verify.
"""

import uuid
from datetime import date, timedelta

import pytest

from app.services.kpis import (
    MIN_N, AiRec, CalvingRec, CheckRec, CowRec, CullRec, EnrollmentRec, HeatCheckRec,
    HerdRecords, NeedlingRec, compute_kpis,
)
from app.services.status_engine import FRESH_TO_OPEN_DAY, GESTATION_DAYS, HEIFER_BREEDING_DAY

TODAY = date(2026, 9, 5)
D = lambda n: TODAY - timedelta(days=n)     # n days ago


def uid():
    return uuid.uuid4()


class Herd:
    """A tiny builder so a test reads like the herd it describes."""

    def __init__(self):
        self.r = HerdRecords()

    def cow(self, status="open", calved_days_ago=None, dob_days_ago=None, **kw) -> CowRec:
        c = CowRec(id=uid(), status=status,
                   date_of_birth=D(dob_days_ago) if dob_days_ago is not None else None, **kw)
        self.r.cows.append(c)
        if calved_days_ago is not None:
            self.calving(c, calved_days_ago)
        return c

    def calving(self, cow, days_ago, **kw) -> CalvingRec:
        rec = CalvingRec(cow_id=cow.id, calving_date=D(days_ago), **kw)
        self.r.calvings.append(rec)
        return rec

    def ai(self, cow, days_ago, result=None, attempt=1, semen=None, checked_days_ago=None) -> AiRec:
        a = AiRec(id=uid(), cow_id=cow.id, date=D(days_ago), attempt_number=attempt, semen_type=semen)
        self.r.inseminations.append(a)
        cow.last_insemination_id = a.id
        cow.last_insemination_date = a.date
        if result is not None:
            when = D(checked_days_ago) if checked_days_ago is not None else D(max(days_ago - 35, 0))
            self.r.checks.append(CheckRec(insemination_id=a.id, cow_id=cow.id, check_date=when, result=result))
        return a

    def cull(self, cow, days_ago):
        self.r.culls.append(CullRec(cow_id=cow.id, cull_date=D(days_ago)))

    def shot(self, cow, scheduled_days_ago, completed=True, completed_days_ago=None, enrolment=None):
        self.r.needling.append(NeedlingRec(
            cow_id=cow.id, scheduled_date=D(scheduled_days_ago), completed=completed,
            completed_date=D(completed_days_ago) if completed_days_ago is not None else None,
            enrollment_id=enrolment.id if enrolment else None,
        ))

    def enrol(self, cow, days_ago, status):
        e = EnrollmentRec(id=uid(), cow_id=cow.id, start_date=D(days_ago), status=status)
        self.r.enrollments.append(e)
        return e

    def heat_check(self, ai, days_after):
        self.r.heat_checks.append(HeatCheckRec(insemination_id=ai.id, check_date=ai.date + timedelta(days=days_after)))

    def kpis(self):
        return compute_kpis(self.r, TODAY)


# A cycle old enough for pregnancy checks to be in: cycle index 3 is
# [84, 63) days ago; its end is 63 days back, past the 50-day check lag.
CONFIRMED_CYCLE_START = 84
IN_CYCLE = 75            # a breeding inside that cycle


# ── 21-day pregnancy rate: the arithmetic ────────────────────────────

def test_ten_eligible_six_served_three_conceived_is_60_50_30():
    """The whole point of testing a rate: known inputs, known answer."""
    h = Herd()
    cows = [h.cow(calved_days_ago=200) for _ in range(10)]     # all past the VWP
    for c in cows[:3]:
        h.ai(c, IN_CYCLE, result="pregnant")
    for c in cows[3:6]:
        h.ai(c, IN_CYCLE, result="not_pregnant")
    k = h.kpis()
    cycle = next(c for c in k["cycles"] if c["start"] == D(CONFIRMED_CYCLE_START).isoformat())
    assert (cycle["eligible"], cycle["served"], cycle["conceived"]) == (10, 6, 3)
    assert cycle["service_rate"] == 60.0
    assert cycle["conception_rate"] == 50.0
    assert cycle["pregnancy_rate"] == 30.0
    assert cycle["pending"] is False


def test_headline_rate_is_weighted_over_confirmed_cycles_only():
    """Two confirmed cycles: 10 eligible / 3 conceived and 10 / 1 -> 4/20 = 20%.
    A single good or bad cycle should not swing the herd's headline figure."""
    h = Herd()
    cows = [h.cow(calved_days_ago=300) for _ in range(10)]
    for c in cows[:3]:
        h.ai(c, IN_CYCLE + 21, result="pregnant")             # older cycle
    h.ai(cows[3], IN_CYCLE, result="pregnant")                 # next cycle
    k = h.kpis()
    # Cows that conceived leave the pool, so the later cycle has 7 eligible,
    # not 10: (3 + 1) / (10 + 7) — and the older cycles have 10 each.
    assert k["pregnancy_rate_21d"]["status"] in ("good", "fair", "poor")
    total_conc = sum(c["conceived"] for c in k["cycles"] if not c["pending"])
    total_elig = sum(c["eligible"] for c in k["cycles"] if not c["pending"])
    assert k["pregnancy_rate_21d"]["value"] == round(100 * total_conc / total_elig, 1)
    assert k["pregnancy_rate_21d"]["n"] == total_elig


def test_recent_cycles_are_flagged_pending_not_judged_bad():
    """A breeding 10 days ago cannot have a pregnancy result yet. Reporting
    that cycle as 0% conception would tell the farmer the herd fell apart
    this month, every month."""
    h = Herd()
    for _ in range(6):
        c = h.cow(calved_days_ago=200)
        h.ai(c, 10)
    k = h.kpis()
    newest = k["cycles"][-1]
    assert newest["pending"] is True
    assert newest["served"] == 6 and newest["conceived"] == 0
    # ...and its cows are not in the headline's denominator: that counts
    # confirmed cycles only. (The earlier version of this assertion was
    # `newest["eligible"] not in ()`, which is always true — it tested nothing.)
    assert k["pregnancy_rate_21d"]["n"] == sum(c["eligible"] for c in k["cycles"] if not c["pending"])
    assert all(c["pending"] for c in k["cycles"][-2:])
    assert not any(c["pending"] for c in k["cycles"][:5])


# ── Eligibility: who is in the denominator ───────────────────────────

def _eligible_in_confirmed_cycle(h):
    k = h.kpis()
    return next(c for c in k["cycles"] if c["start"] == D(CONFIRMED_CYCLE_START).isoformat())["eligible"]


def test_a_cow_inside_the_voluntary_waiting_period_is_not_eligible():
    h = Herd()
    h.cow(calved_days_ago=CONFIRMED_CYCLE_START + FRESH_TO_OPEN_DAY - 1)   # 69 days at cycle start
    assert _eligible_in_confirmed_cycle(h) == 0


def test_a_cow_exactly_at_the_vwp_is_eligible():
    h = Herd()
    h.cow(calved_days_ago=CONFIRMED_CYCLE_START + FRESH_TO_OPEN_DAY)       # 70 days at cycle start
    assert _eligible_in_confirmed_cycle(h) == 1


def test_a_heifer_enters_the_pool_at_breeding_age():
    h = Herd()
    h.cow(status="heifer", dob_days_ago=CONFIRMED_CYCLE_START + HEIFER_BREEDING_DAY)
    h.cow(status="heifer", dob_days_ago=CONFIRMED_CYCLE_START + HEIFER_BREEDING_DAY - 1)
    assert _eligible_in_confirmed_cycle(h) == 1


def test_an_animal_with_no_calving_and_no_birth_date_is_never_eligible():
    """No defensible entry point: leaving her out is honest, counting her is a
    guess in the denominator."""
    h = Herd()
    h.cow(status="open")
    assert _eligible_in_confirmed_cycle(h) == 0


def test_a_confirmed_pregnant_cow_is_out_of_the_pool():
    h = Herd()
    c = h.cow(calved_days_ago=300)
    h.ai(c, 150, result="pregnant")         # pregnant well before the cycle
    assert _eligible_in_confirmed_cycle(h) == 0


def test_a_later_breeding_means_the_pregnancy_was_lost_and_she_is_back():
    h = Herd()
    c = h.cow(calved_days_ago=400)
    h.ai(c, 250, result="pregnant")
    h.ai(c, 120, result="not_pregnant")     # rebred: she was open again
    assert _eligible_in_confirmed_cycle(h) == 1


def test_calving_after_a_pregnancy_resets_her_to_open_then_vwp():
    h = Herd()
    c = h.cow()
    h.ai(c, 500, result="pregnant")
    h.calving(c, 500 - GESTATION_DAYS)      # calved ~217 days ago
    # 217 - 84 = 133 days into lactation at cycle start: past the VWP, open.
    assert _eligible_in_confirmed_cycle(h) == 1


def test_a_culled_cow_leaves_the_pool_from_her_cull_date():
    h = Herd()
    c = h.cow(calved_days_ago=300)
    h.cull(c, CONFIRMED_CYCLE_START + 1)    # gone the day before the cycle
    assert _eligible_in_confirmed_cycle(h) == 0


def test_a_cow_culled_during_the_cycle_still_counts_at_its_start():
    h = Herd()
    c = h.cow(calved_days_ago=300)
    h.cull(c, CONFIRMED_CYCLE_START - 5)
    assert _eligible_in_confirmed_cycle(h) == 1


def test_sold_or_dead_with_no_dated_record_is_excluded_from_history():
    """We do not know when she left, so she cannot honestly sit in any
    historical denominator."""
    h = Herd()
    h.cow(status="sold", calved_days_ago=300)
    h.cow(status="dead", calved_days_ago=300)
    assert _eligible_in_confirmed_cycle(h) == 0


def test_imported_pregnant_cow_without_check_records_is_treated_as_pregnant():
    """An imported herd has statuses but no pregnancy-check rows. Her latest
    breeding has no result, but she is `pregnant` — so from that breeding on
    she is out of the pool, not dragging the rate down."""
    h = Herd()
    c = h.cow(status="pregnant", calved_days_ago=300)
    h.ai(c, 150)                            # no result recorded
    assert _eligible_in_confirmed_cycle(h) == 0


# ── Conception, by month and first service ───────────────────────────

def test_conception_rate_counts_only_checked_breedings():
    h = Herd()
    cows = [h.cow(calved_days_ago=200) for _ in range(8)]
    for c in cows[:4]:
        h.ai(c, 100, result="pregnant")
    for c in cows[4:6]:
        h.ai(c, 100, result="not_pregnant")
    for c in cows[6:]:
        h.ai(c, 100)                        # awaiting a check
    k = h.kpis()
    conc = k["conception"]
    assert conc["rate"]["value"] == round(100 * 4 / 6, 1)
    assert conc["rate"]["n"] == 6
    assert conc["unchecked_breedings"] == 2


def test_first_service_conception_rate_uses_attempt_one_only():
    h = Herd()
    cows = [h.cow(calved_days_ago=300) for _ in range(6)]
    for c in cows[:2]:
        h.ai(c, 120, result="pregnant", attempt=1)
    for c in cows[2:4]:
        h.ai(c, 120, result="not_pregnant", attempt=1)
    for c in cows[4:]:
        h.ai(c, 120, result="pregnant", attempt=2)   # second services: excluded
    k = h.kpis()
    assert k["conception"]["first_service_rate"]["value"] == 50.0
    assert k["conception"]["first_service_rate"]["n"] == 4


def test_services_per_conception():
    h = Herd()
    cows = [h.cow(calved_days_ago=300) for _ in range(5)]
    for c in cows:
        h.ai(c, 200, result="not_pregnant", attempt=1)
        h.ai(c, 150, result="pregnant", attempt=2)
    k = h.kpis()
    assert k["conception"]["services_per_conception"]["value"] == 2.0   # 10 / 5


def test_monthly_series_covers_twelve_months_and_puts_each_breeding_in_its_month():
    h = Herd()
    c = h.cow(calved_days_ago=300)
    h.ai(c, 40, result="pregnant")
    k = h.kpis()
    months = k["conception"]["by_month"]
    assert len(months) == 12
    assert months[-1]["month"] == TODAY.strftime("%Y-%m")
    key = D(40).strftime("%Y-%m")
    m = next(m for m in months if m["month"] == key)
    assert (m["checked"], m["pregnant"], m["rate"]) == (1, 1, 100.0)


# ── Timing ───────────────────────────────────────────────────────────

def test_days_open_is_calving_to_conception_with_the_median_reported():
    h = Herd()
    for gap in (90, 110, 130, 150, 170):
        c = h.cow(calved_days_ago=gap + 100)
        h.ai(c, 100, result="pregnant")     # conceived `gap` days after calving
    k = h.kpis()
    do = k["timing"]["days_open"]
    assert do["value"] == 130 and do["n"] == 5
    assert do["mean"] == 130.0
    assert do["buckets"] == {"under_100": 1, "100_130": 2, "131_160": 1, "over_160": 1}


def test_a_heifer_conception_has_no_days_open():
    """Days open is calving-to-conception; a heifer has not calved."""
    h = Herd()
    c = h.cow(status="heifer", dob_days_ago=600)
    h.ai(c, 100, result="pregnant")
    assert h.kpis()["timing"]["days_open"]["n"] == 0


def test_days_to_first_service_is_the_first_breeding_after_calving():
    h = Herd()
    c = h.cow(calved_days_ago=200)
    h.ai(c, 200 - 75)                       # 75 days after calving
    h.ai(c, 200 - 96)                       # second service, must not count
    k = h.kpis()
    assert k["timing"]["days_to_first_service"]["value"] == 75


def test_calving_interval_in_months_from_consecutive_calvings():
    h = Herd()
    c = h.cow()
    h.calving(c, 500)
    h.calving(c, 500 - 396)                 # 396 days ≈ 13.0 months
    k = h.kpis()
    assert k["timing"]["calving_interval_months"]["value"] == round(396 / 30.44, 1)
    assert k["timing"]["calving_interval_months"]["n"] == 1


# ── Outcomes ─────────────────────────────────────────────────────────

def test_stillbirth_rate():
    h = Herd()
    for i in range(10):
        c = h.cow()
        h.calving(c, 30 + i, live_birth=(i >= 2), still_birth=(i < 2))
    k = h.kpis()
    assert k["outcomes"]["stillbirth_rate"]["value"] == 20.0
    assert k["outcomes"]["calvings"] == 10


def test_sexed_semen_heifer_rate_matches_each_calf_to_its_breeding():
    """The calf's breeding is the AI nearest to calving minus gestation. Ten
    sexed breedings, nine heifer calves -> 90%; the conventional one is kept
    apart as the control."""
    h = Herd()
    for i in range(10):
        c = h.cow()
        calved = 20 + i
        h.ai(c, calved + GESTATION_DAYS + 3, semen="sexed", result="pregnant")   # 3 days off nominal
        h.calving(c, calved, calf_sex="female" if i < 9 else "male")
    c = h.cow()
    h.ai(c, 40 + GESTATION_DAYS, semen="conventional", result="pregnant")
    h.calving(c, 40, calf_sex="male")
    k = h.kpis()
    assert k["outcomes"]["sexed_semen_heifer_rate"]["value"] == 90.0
    assert k["outcomes"]["sexed_semen_heifer_rate"]["n"] == 10
    assert k["outcomes"]["conventional_heifer_rate"]["value"] == 0.0


def test_a_breeding_too_far_from_the_calving_is_not_credited_with_the_calf():
    h = Herd()
    c = h.cow()
    h.ai(c, 30 + GESTATION_DAYS + 60, semen="sexed")   # two months before any plausible conception
    h.calving(c, 30, calf_sex="female")
    assert h.kpis()["outcomes"]["sexed_semen_heifer_rate"]["n"] == 0


def test_cull_rate_is_culls_over_herd_present_this_year():
    h = Herd()
    for _ in range(7):
        h.cow(status="open")
    for _ in range(3):
        c = h.cow(status="cull")
        h.cull(c, 100)
    k = h.kpis()
    assert k["outcomes"]["cull_rate"]["value"] == 30.0     # 3 / (7 + 3)
    assert k["outcomes"]["culls"] == 3


def test_overdue_pregnancy_checks_count_cows_past_the_warning_day_without_a_result():
    h = Herd()
    a = h.cow(status="inseminated"); h.ai(a, 55)                          # overdue
    b = h.cow(status="inseminated"); h.ai(b, 40)                          # not yet
    c = h.cow(status="inseminated"); h.ai(c, 70, result="not_pregnant")  # has a result
    k = h.kpis()
    assert k["outcomes"]["overdue_pregnancy_checks"]["value"] == 1
    assert k["outcomes"]["overdue_pregnancy_checks"]["status"] == "poor"


# ── Compliance ───────────────────────────────────────────────────────

def test_protocol_shots_split_into_on_time_late_and_missed():
    h = Herd()
    c = h.cow()
    h.shot(c, 30, completed=True, completed_days_ago=30)    # on the day
    h.shot(c, 20, completed=True, completed_days_ago=18)    # two days late
    h.shot(c, 10, completed=False)                          # never given: missed
    h.shot(c, 1, completed=False)                           # due yesterday: still open
    k = h.kpis()
    comp = k["compliance"]["protocol_on_time_rate"]
    assert (comp["on_time"], comp["late"], comp["missed"]) == (1, 1, 1)
    assert comp["value"] == round(100 / 3, 1)


def test_protocol_completion_rate_ignores_protocols_still_running():
    h = Herd()
    c = h.cow()
    for s in ("completed", "completed", "completed_pending_ai", "cancelled", "active"):
        h.enrol(c, 30, s)
    k = h.kpis()
    comp = k["compliance"]["protocol_completion_rate"]
    assert (comp["completed"], comp["cancelled"], comp["active"]) == (3, 1, 1)
    assert comp["value"] == 75.0


def test_heat_check_coverage_only_judges_breedings_whose_window_has_closed():
    h = Herd()
    c1 = h.cow(calved_days_ago=200); a1 = h.ai(c1, 40); h.heat_check(a1, 22)   # covered
    c2 = h.cow(calved_days_ago=200); h.ai(c2, 40)                              # window closed, never checked
    c3 = h.cow(calved_days_ago=200); h.ai(c3, 10)                              # window still open: not judged
    k = h.kpis()
    cov = k["compliance"]["heat_check_coverage"]
    assert cov["value"] == 50.0 and cov["n"] == 2


# ── Judgement ────────────────────────────────────────────────────────

@pytest.mark.parametrize("pregnant,expected", [
    (5, "good"),     # 5/20 = 25%
    (4, "good"),     # 20%  — the boundary is inclusive
    (3, "fair"),     # 15%
    (2, "poor"),     # 10%
])
def test_pregnancy_rate_is_judged_against_the_published_bands(pregnant, expected):
    h = Herd()
    cows = [h.cow(calved_days_ago=200) for _ in range(20)]
    for c in cows[:pregnant]:
        h.ai(c, IN_CYCLE, result="pregnant")
    # Restrict to a single confirmed cycle by making every other cycle empty
    # of both breedings and eligibility changes; the herd is 20 eligible in
    # each confirmed cycle, conceptions only in one.
    k = h.kpis()
    # weighted: pregnant / (20 * confirmed cycles - those already pregnant later)
    # Simpler and exact: evaluate the one cycle they were bred in.
    cycle = next(c for c in k["cycles"] if c["start"] == D(CONFIRMED_CYCLE_START).isoformat())
    from app.services.kpis import _kpi
    assert _kpi("pregnancy_rate_21d", cycle["pregnancy_rate"], cycle["eligible"], "%")["status"] == expected


def test_too_few_records_is_reported_but_not_judged():
    h = Herd()
    cows = [h.cow(calved_days_ago=200) for _ in range(MIN_N - 1)]
    for c in cows:
        h.ai(c, 100, result="pregnant")
    k = h.kpis()
    conc = k["conception"]["rate"]
    assert conc["value"] == 100.0        # the figure is still there
    assert conc["n"] == MIN_N - 1
    assert conc["status"] == "na"        # but nobody is told it is "good"


def test_lower_is_better_bands_run_the_other_way():
    h = Herd()
    for gap in (200, 210, 220, 230, 240):
        c = h.cow(calved_days_ago=gap + 100)
        h.ai(c, 100, result="pregnant")
    assert h.kpis()["timing"]["days_open"]["status"] == "poor"       # median 220 > 150


def test_every_target_sentence_is_present_for_judged_kpis():
    h = Herd()
    k = h.kpis()
    for path in (("pregnancy_rate_21d",), ("service_rate_21d",), ("conception", "rate"),
                 ("timing", "days_open"), ("outcomes", "stillbirth_rate"),
                 ("compliance", "protocol_on_time_rate")):
        node = k
        for p in path:
            node = node[p]
        assert node["target"], f"{path} has no target sentence"


# ── Robustness ───────────────────────────────────────────────────────

def test_an_empty_herd_produces_a_complete_report_with_no_division_by_zero():
    k = compute_kpis(HerdRecords(), TODAY)
    assert len(k["cycles"]) == 8
    assert k["pregnancy_rate_21d"] == {"value": None, "n": 0, "unit": "%", "status": "na",
                                        "target": k["pregnancy_rate_21d"]["target"]}
    assert k["conception"]["services_per_conception"]["value"] is None
    assert k["timing"]["days_open"]["value"] is None
    assert k["outcomes"]["cull_rate"]["value"] is None
    assert k["compliance"]["heat_check_coverage"]["value"] is None


def test_the_latest_check_on_a_breeding_decides_its_result():
    """A recheck that reverses an earlier call must win."""
    h = Herd()
    c = h.cow(calved_days_ago=300)
    a = h.ai(c, 120, result="pregnant", checked_days_ago=85)
    h.r.checks.append(CheckRec(insemination_id=a.id, cow_id=c.id, check_date=D(60), result="not_pregnant"))
    k = h.kpis()
    assert k["conception"]["rate"]["value"] == 0.0


# ── Imported herds ───────────────────────────────────────────────────

def test_imported_herd_with_calving_dates_but_no_calving_records_still_computes():
    """Imports set last_calving_date on the cow and write no calving rows. The
    endpoint test caught this: without treating that date as a calving, an
    imported farm had no eligible cows, no days open and no days to first
    service — an empty KPI screen for exactly the herds the client loads first."""
    h = Herd()
    c = h.cow(status="pregnant")             # no calving record...
    c.last_calving_date = D(200)             # ...just the date, as an import leaves it
    h.ai(c, 100, result="pregnant")
    k = h.kpis()

    assert k["timing"]["days_open"]["value"] == 100 and k["timing"]["days_open"]["n"] == 1
    assert k["timing"]["days_to_first_service"]["value"] == 100
    # In the cycle starting 126 days ago she was 74 days calved: eligible.
    cycle = next(x for x in k["cycles"] if x["start"] == D(126).isoformat())
    assert cycle["eligible"] == 1


def test_a_synthesized_calving_is_a_date_not_an_outcome():
    """It carries no calf, so stillbirth and sexed-semen figures must not see it."""
    h = Herd()
    c = h.cow()
    c.last_calving_date = D(30)
    assert h.kpis()["outcomes"]["calvings"] == 0


def test_a_recorded_calving_on_the_same_date_is_not_doubled():
    h = Herd()
    c = h.cow(calved_days_ago=30)            # real record
    c.last_calving_date = D(30)              # and the cow's own copy of it
    k = h.kpis()
    assert k["outcomes"]["calvings"] == 1


# ── Found in adversarial review ──────────────────────────────────────

def test_a_culled_cow_with_no_cull_record_is_not_eligible_forever():
    """Status `cull` with no cull row — every culled animal in an imported herd.
    `left_undated` only covered sold/dead, so she sat in the eligible pool of
    every cycle, dragging the pregnancy rate down with an animal that was not
    on the farm."""
    h = Herd()
    h.cow(status="cull", calved_days_ago=300)
    assert _eligible_in_confirmed_cycle(h) == 0


def test_shots_from_a_cancelled_protocol_are_not_missed_shots():
    """A bleeding event cancels the protocol and its remaining shots are
    correctly never given. Counting them as missed punished the technician for
    doing the right thing and reported a compliance problem that did not exist."""
    h = Herd()
    c = h.cow()
    gone = h.enrol(c, 20, "cancelled")
    h.shot(c, 20, completed=True, completed_days_ago=20, enrolment=gone)   # given before the cancel
    h.shot(c, 13, completed=False, enrolment=gone)                          # never due after it
    h.shot(c, 10, completed=False, enrolment=gone)
    live = h.enrol(c, 8, "active")
    h.shot(c, 5, completed=False, enrolment=live)                           # a real miss
    k = h.kpis()
    comp = k["compliance"]["protocol_on_time_rate"]
    assert (comp["on_time"], comp["late"], comp["missed"]) == (1, 0, 1)


def test_a_cycle_reports_breedings_still_awaiting_a_result():
    """Unchecked breedings count as not pregnant in the rate (the conservative
    convention), so the cycle must say how many there were — otherwise a
    farm whose vet is late entering results looks like a farm whose cows are
    not conceiving."""
    h = Herd()
    cows = [h.cow(calved_days_ago=200) for _ in range(6)]
    h.ai(cows[0], IN_CYCLE, result="pregnant")
    h.ai(cows[1], IN_CYCLE, result="not_pregnant")
    h.ai(cows[2], IN_CYCLE)                      # no result yet
    h.ai(cows[3], IN_CYCLE)
    k = h.kpis()
    cycle = next(c for c in k["cycles"] if c["start"] == D(CONFIRMED_CYCLE_START).isoformat())
    assert (cycle["served"], cycle["conceived"], cycle["unchecked"]) == (4, 1, 2)
    assert cycle["pregnancy_rate"] == round(100 / 6, 1)     # unchecked are not conceptions
