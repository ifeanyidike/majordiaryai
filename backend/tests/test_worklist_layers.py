"""The three To-Do layers: farm rotation, report membership, and the actions.

Covers the General To-Do list (which farms today, who covers them) and the
report catalog that layers 2 and 3 are built from. The catalog is the single
source of report membership, so these are the tests that stop a rule change from
silently dropping a cow off the technician's day.
"""

import uuid
from datetime import date, timedelta

import pytest

from app.core.timeutils import local_today

from app.models.models import (
    Cow, CowStatus, Farm, FarmVisitAssignment, HealthStatus, User, UserRole,
)
from app.services.report_catalog import WorklistContext, build_reports
from app.services.visits import (
    VisitStatus, describe_weekdays, is_visit_due, next_visit_date, resolve_visit,
    visit_label, weekdays_for,
)
from app.services.worklist_builder import build_worklist

# The app computes 'today' in the farm timezone; using the machine's
# UTC date made boundary tests flake on CI between 00:00 and 04:00.
TODAY = local_today()


def _farm(days_per_week=6, tech=None, weekdays=None) -> Farm:
    return Farm(
        id=uuid.uuid4(), name="F", owner_name="O", herd_size=0,
        visit_weekdays=list(weekdays if weekdays is not None
                            else weekdays_for(days_per_week)),
        assigned_technician_id=tech,
    )


def _farm_due_today(tech=None) -> Farm:
    """Scheduled on today's weekday, whatever day the suite runs."""
    return _farm(weekdays=[TODAY.weekday()], tech=tech)


def _farm_not_due_today(tech=None) -> Farm:
    """Scheduled only on a different weekday, so it is off the route today."""
    return _farm(weekdays=[(TODAY.weekday() + 1) % 7], tech=tech)


def _ctx(cows, role="technician", **kw) -> WorklistContext:
    return WorklistContext(today=TODAY, role=role, cows=cows, **kw)


def _rows(cows, report_type, **kw):
    reports = {r["type"]: r for r in build_reports(_ctx(cows, **kw))}
    return reports.get(report_type, {"cows": []})["cows"]


# ── Layer 1: the weekday schedule ────────────────────────────────────
# Client: a "5-day farm" is Mon-Fri and a "6-day farm" is Mon-Sat, Sunday off.

# Fixed reference week so these never depend on the day the suite runs.
MONDAY = date(2026, 8, 3)
FRIDAY = MONDAY + timedelta(days=4)
SATURDAY = MONDAY + timedelta(days=5)
SUNDAY = MONDAY + timedelta(days=6)


@pytest.mark.parametrize("days_per_week,day,due", [
    (5, MONDAY, True),
    (5, FRIDAY, True),
    (5, SATURDAY, False),   # the 5-day farm drops off the route on Saturday
    (5, SUNDAY, False),
    (6, MONDAY, True),
    (6, SATURDAY, True),    # ...where the 6-day farm is still due
    (6, SUNDAY, False),     # nobody works Sunday
])
def test_weekday_schedule_decides_which_farms_are_due(days_per_week, day, due):
    assert is_visit_due(_farm(days_per_week), day) is due


def test_nobody_is_scheduled_on_sunday():
    """Sunday is the day off on both schedules — which is what keeps the
    Mon/Tue/Sat breeding-day rule from ever landing on a non-working day."""
    assert not is_visit_due(_farm(5), SUNDAY)
    assert not is_visit_due(_farm(6), SUNDAY)


def test_farm_without_a_configured_schedule_defaults_to_six_days():
    """A missing schedule must not silently hide real work: default to the
    busiest schedule (Mon-Sat), not to "never"."""
    farm = _farm()
    farm.visit_weekdays = None
    assert is_visit_due(farm, SATURDAY) is True
    assert is_visit_due(farm, SUNDAY) is False


def test_irregular_weekday_patterns_are_supported():
    """Storing the day set (not a count) means Mon/Thu needs no schema change."""
    farm = _farm(weekdays=[0, 3])
    assert is_visit_due(farm, MONDAY) is True
    assert is_visit_due(farm, MONDAY + timedelta(days=3)) is True
    assert is_visit_due(farm, FRIDAY) is False


def test_next_visit_date_is_the_next_scheduled_weekday():
    # Friday on a 5-day farm → the following Monday, skipping the weekend.
    assert next_visit_date(_farm(5), FRIDAY) == MONDAY + timedelta(days=7)
    # Friday on a 6-day farm → Saturday.
    assert next_visit_date(_farm(6), FRIDAY) == SATURDAY


@pytest.mark.parametrize("days_per_week,label", [(5, "Mon–Fri"), (6, "Mon–Sat")])
def test_schedule_label_reads_as_a_range(days_per_week, label):
    assert describe_weekdays(weekdays_for(days_per_week)) == label


# ── Layer 1: reassignment ────────────────────────────────────────────

def test_standing_technician_sees_visit_today():
    me = uuid.uuid4()
    assert resolve_visit(_farm(tech=me), None, me) is VisitStatus.visit_today


def test_reassigned_farm_stays_on_the_list_flagged_to_skip():
    """Per the spec's example table: the farm is still listed, marked
    "Reassigned to Relief Tech — Skip", so a technician knows why a familiar
    farm dropped off rather than wondering."""
    me, relief = uuid.uuid4(), uuid.uuid4()
    farm = _farm(tech=me)
    override = FarmVisitAssignment(farm_id=farm.id, visit_date=TODAY,
                                   assigned_technician_id=relief)
    assert resolve_visit(farm, override, me) is VisitStatus.reassigned
    assert visit_label(VisitStatus.reassigned, "Relief Tech") == \
        "Reassigned to Relief Tech — Skip"


def test_relief_technician_sees_the_farm_he_is_covering():
    me, owner = uuid.uuid4(), uuid.uuid4()
    farm = _farm(tech=owner)
    override = FarmVisitAssignment(farm_id=farm.id, visit_date=TODAY,
                                   assigned_technician_id=me)
    assert resolve_visit(farm, override, me) is VisitStatus.covering


def test_unrelated_technician_never_sees_the_farm():
    farm = _farm(tech=uuid.uuid4())
    assert resolve_visit(farm, None, uuid.uuid4()) is None


def test_explicitly_skipped_day_is_shown_as_skipped():
    me = uuid.uuid4()
    farm = _farm(tech=me)
    override = FarmVisitAssignment(farm_id=farm.id, visit_date=TODAY,
                                   assigned_technician_id=None)
    assert resolve_visit(farm, override, me) is VisitStatus.skipped


# ── Layer 2/3: report membership ─────────────────────────────────────

def _cow(**kw) -> Cow:
    kw.setdefault("id", uuid.uuid4())
    kw.setdefault("farm_id", uuid.uuid4())
    kw.setdefault("ear_tag", "T-1")
    kw.setdefault("lactation_number", 1)
    return Cow(**kw)


@pytest.mark.parametrize("days,on_report", [
    (19, False),   # before the window
    (20, True),
    (25, True),
    (26, False),   # after day 25 there is no more heat check for that cow
])
def test_heat_report_window(days, on_report):
    cow = _cow(status=CowStatus.inseminated,
               last_insemination_date=TODAY - timedelta(days=days))
    assert bool(_rows([cow], "heat")) is on_report


@pytest.mark.parametrize("days,expected_overdue", [
    (30, False),   # appears on the Pregnancy Report
    (49, False),
    (50, True),    # Pregnancy Check Warning
])
def test_pregnancy_report_and_warning_threshold(days, expected_overdue):
    cow = _cow(status=CowStatus.inseminated,
               last_insemination_date=TODAY - timedelta(days=days))
    rows = _rows([cow], "pregnancy-check")
    assert len(rows) == 1
    assert rows[0]["overdue"] is expected_overdue


def test_pregnancy_result_is_recordable_by_technician_and_vet():
    """Client decision (2026-08-06): "either or both" may record the result, so
    both roles get the form. The API allows the same set."""
    cow = _cow(status=CowStatus.inseminated,
               last_insemination_date=TODAY - timedelta(days=40))
    assert _rows([cow], "pregnancy-check", role="technician")[0]["record_kind"] == "preg"
    assert _rows([cow], "pregnancy-check", role="vet")[0]["record_kind"] == "preg"


def test_heat_detected_cow_is_on_the_insemination_report_not_open():
    """She is bred directly, not re-enrolled in a protocol. Excluding her from
    the Open report without giving her one left her on no work list at all."""
    cow = _cow(status=CowStatus.open, current_program="Insemination",
               last_calving_date=TODAY - timedelta(days=90))
    assert len(_rows([cow], "insemination")) == 1
    assert not _rows([cow], "open-report")


def test_sick_cow_is_only_listed_when_her_recheck_is_due():
    """Spec: recheck every 7 days — not every day."""
    base = dict(status=CowStatus.open, health_status=HealthStatus.sick,
                last_calving_date=TODAY - timedelta(days=90))
    assert not _rows([_cow(**base, recheck_due_date=TODAY + timedelta(days=3))], "open-report")
    assert _rows([_cow(**base, recheck_due_date=TODAY)], "open-report")


def test_dry_report_covers_both_sides_of_the_day_223_transition():
    """The sweep flips pregnant -> dry on exactly the day the work becomes due,
    so a `pregnant`-only filter drops her the moment she is actionable."""
    approaching = _cow(status=CowStatus.pregnant, dry_date=TODAY + timedelta(days=3))
    transitioned = _cow(status=CowStatus.dry, dry_date=TODAY)
    assert len(_rows([approaching, transitioned], "dry-report")) == 2


def test_confirming_the_pen_change_clears_the_dry_report():
    """Without a completable action the Dry Report repeated every day forever."""
    cow = _cow(status=CowStatus.dry, dry_date=TODAY,
               dry_off_confirmed_date=TODAY)
    assert not _rows([cow], "dry-report")


def test_fresh_report_is_just_calved_not_the_whole_fresh_period():
    """A ~70-day window kept every farm permanently "with work"."""
    just = _cow(status=CowStatus.fresh, last_calving_date=TODAY)
    old = _cow(status=CowStatus.fresh, last_calving_date=TODAY - timedelta(days=20))
    rows = _rows([just, old], "fresh")
    assert len(rows) == 1 and rows[0]["cow_id"] == str(just.id)


def test_recording_the_post_calving_shot_clears_the_report():
    """The report is driven by the calving-linked vaccination record: pending
    keeps her on it, completed takes her off, and a completed record from a
    PREVIOUS lactation must not hide the current shot."""
    cow = _cow(status=CowStatus.fresh, last_calving_date=TODAY - timedelta(days=35))

    done = _ctx([cow], post_calving={str(cow.id): {"completed_on": TODAY - timedelta(days=2)}})
    assert "post-calving" not in {r["type"] for r in build_reports(done)}

    # No completed vaccination at all → she is work.
    no_shot = _ctx([cow])
    assert {r["type"]: r for r in build_reports(no_shot)}["post-calving"]["count"] == 1

    # A shot from the PREVIOUS lactation must not hide the current one.
    old_lactation = _ctx([cow], post_calving={str(cow.id): {
        "completed_on": cow.last_calving_date - timedelta(days=300),
    }})
    assert {r["type"]: r for r in build_reports(old_lactation)}["post-calving"]["count"] == 1


def test_breeding_age_heifer_is_on_the_insemination_report():
    """Master Structure: month-13 heifers go straight to the Insemination
    Program. Her row must not claim a heat detection or a last AI she never had."""
    heifer = _cow(status=CowStatus.open, current_program="Insemination")
    rows = _rows([heifer], "insemination")
    assert len(rows) == 1
    assert rows[0]["action"] == "Ready for first breeding — breed her"
    assert "Heat detected" not in rows[0]["detail"]


def test_extra_pending_shots_are_announced_not_collapsed():
    """Double Ovsynch schedules PGF on days 24 AND 25 — a technician a day
    behind has two shots pending, and the row must say so."""
    cow = _cow(status=CowStatus.needling)
    ctx = _ctx([cow], needling={str(cow.id): {
        "id": str(uuid.uuid4()), "treatment": "2cc PGF", "protocol_day": 24,
        "protocol": "double_ovsynch", "days_overdue": 1,
        "enrollment_id": str(uuid.uuid4()), "also_pending": 1,
    }})
    action = {r["type"]: r for r in build_reports(ctx)}["needling"]["cows"][0]["action"]
    assert "plus 1 more pending shot" in action


def test_missed_earlier_shots_surface_on_the_timed_breeding_row():
    """The overlap rule hides the whole cow from the Needling report on her
    final day; a shot she missed earlier must not vanish from every report."""
    cow = _cow(status=CowStatus.needling)
    ctx = _ctx([cow], breeding={str(cow.id): {
        "protocol": "double_ovsynch", "protocol_day": 27,
        "treatment": "2cc GnRH + Insemination", "injection": "2cc GnRH",
        "needling_record_id": str(uuid.uuid4()), "needling_completed": False,
        "days_overdue": 0, "missed_shots": 2,
    }})
    row = {r["type"]: r for r in build_reports(ctx)}["timed-breeding"]["cows"][0]
    assert "2 earlier shots were missed" in row["action"]


def test_post_calving_and_vaccination_are_different_reports():
    """Spec keeps them apart: Post Calving is the day-30..50 2cc shot, while
    Vaccination is a *schedule* report — eligible after day 30 but waiting on
    the vaccine's own date. Merging them hid every cow with no scheduled
    vaccine; treating them as one filter double-counted the ones that had one.
    """
    cow = _cow(status=CowStatus.fresh, last_calving_date=TODAY - timedelta(days=35))

    # No scheduled vaccine yet → Post Calving only.
    reports = {r["type"]: r for r in build_reports(_ctx([cow]))}
    assert reports["post-calving"]["count"] == 1
    assert "vaccination" not in reports

    # With one scheduled and due → the Vaccination report picks her up too.
    ctx = _ctx([cow], vaccinations={str(cow.id): {
        "id": str(uuid.uuid4()), "vaccine_name": "ScourGuard",
        "scheduled_date": TODAY.isoformat(), "days_overdue": 0,
    }})
    reports = {r["type"]: r for r in build_reports(ctx)}
    assert reports["vaccination"]["count"] == 1
    assert "ScourGuard" in reports["vaccination"]["cows"][0]["action"]


def test_vaccination_waits_for_the_scheduled_date():
    """"cows are ready for vaccination after day 30 but must wait until
    schedule date of vaccine"."""
    cow = _cow(status=CowStatus.fresh, last_calving_date=TODAY - timedelta(days=35))
    # A record scheduled in the future is not fed in by the builder at all, so
    # the report is empty — the cow is eligible but not yet due.
    assert not _rows([cow], "vaccination")


def test_upcoming_calvings_are_not_counted_as_work():
    """The spec's calving work is the Fresh / Calving Report, triggered by the
    birth. A due-date heads-up is useful but must not inflate the workload."""
    cow = _cow(status=CowStatus.pregnant, due_date=TODAY + timedelta(days=2))
    reports = {r["type"]: r for r in build_reports(_ctx([cow]))}
    assert reports["calving-due"]["count"] == 1
    assert reports["calving-due"]["is_work_report"] is False


def test_needling_observation_days_do_not_read_as_injections():
    cow = _cow(status=CowStatus.needling)
    ctx = _ctx([cow], needling={str(cow.id): {
        "id": str(uuid.uuid4()), "treatment": "Heat Examination", "protocol_day": 3,
        "protocol": "prostaglandin_heat", "days_overdue": 0,
        "enrollment_id": str(uuid.uuid4()),
    }})
    action = {r["type"]: r for r in build_reports(ctx)}["needling"]["cows"][0]["action"]
    assert "injection" not in action
    assert action == "Requires Heat Examination today (PGF Heat, Day 3)"


def test_protocol_labels_never_leak_the_raw_enum():
    cow = _cow(status=CowStatus.needling)
    ctx = _ctx([cow], needling={str(cow.id): {
        "id": str(uuid.uuid4()), "treatment": "2cc PGF", "protocol_day": 7,
        "protocol": "ovsynch", "days_overdue": 0, "enrollment_id": str(uuid.uuid4()),
    }})
    action = {r["type"]: r for r in build_reports(ctx)}["needling"]["cows"][0]["action"]
    assert "Ovsynch, Day 7" in action
    assert "ovsynch," not in action


def test_final_day_action_does_not_repeat_the_insemination_clause(make_cow=None):
    cow = _cow(status=CowStatus.needling)
    ctx = _ctx([cow], breeding={str(cow.id): {
        "protocol": "ovsynch", "protocol_day": 10,
        "treatment": "2cc GnRH + Insemination", "injection": "2cc GnRH",
        "needling_record_id": str(uuid.uuid4()), "needling_completed": False,
        "days_overdue": 0,
    }})
    action = {r["type"]: r for r in build_reports(ctx)}["timed-breeding"]["cows"][0]["action"]
    assert action == "Give final 2cc GnRH + inseminate today (Ovsynch, Day 10 — final day)"


def test_already_given_final_shot_is_not_requested_twice():
    cow = _cow(status=CowStatus.needling)
    ctx = _ctx([cow], breeding={str(cow.id): {
        "protocol": "ovsynch", "protocol_day": 10,
        "treatment": "2cc GnRH + Insemination", "injection": "2cc GnRH",
        "needling_record_id": str(uuid.uuid4()), "needling_completed": True,
        "days_overdue": 0,
    }})
    row = {r["type"]: r for r in build_reports(ctx)}["timed-breeding"]["cows"][0]
    assert row["action"] == "Requires insemination today (Ovsynch, Day 10 — final day)"
    assert row["treatment"] is None, "would instruct a second injection"


def test_layer_2_counts_equal_layer_3_rows():
    """The count on the Farm To-Do list and the rows inside the report are the
    same evaluation — they cannot disagree."""
    cows = [
        _cow(status=CowStatus.inseminated, last_insemination_date=TODAY - timedelta(days=22)),
        _cow(status=CowStatus.inseminated, last_insemination_date=TODAY - timedelta(days=40)),
        _cow(status=CowStatus.fresh, last_calving_date=TODAY - timedelta(days=35)),
        _cow(status=CowStatus.open, last_calving_date=TODAY - timedelta(days=90)),
    ]
    for report in build_reports(_ctx(cows)):
        assert report["count"] == len(report["cows"])


# ── End to end through the builder ───────────────────────────────────

async def test_rotation_flags_off_rotation_farms_instead_of_hiding_them(db):
    """Route screens filter on the flag; the farm's DATA stays in the payload
    so a farm profile opened on an off-rotation day still shows real counts."""
    tech = User(id=uuid.uuid4(), name="Tech", email=f"{uuid.uuid4().hex[:8]}@t.local",
                role=UserRole.technician)
    db.add(tech)
    await db.flush()

    due = _farm_due_today(tech=tech.id)
    due.name = "Due Today"
    not_due = _farm_not_due_today(tech=tech.id)
    not_due.name = "Mid Rotation"
    db.add_all([due, not_due])
    await db.flush()

    user = {"id": tech.id, "role": "technician", "farm_id": None}
    result = await build_worklist(db, user, TODAY)
    by_name = {f["farm_name"]: f for f in result["farms"]}
    assert set(by_name) == {"Due Today", "Mid Rotation"}
    assert by_name["Due Today"]["schedule"] == "visit_today"
    assert by_name["Due Today"]["schedule_label"] == "Visit Today"
    assert by_name["Mid Rotation"]["schedule"] == "not_due"
    assert by_name["Mid Rotation"]["schedule_label"] == "Not on today's rotation"
    # Farms to actually visit sort above off-rotation reference farms.
    assert [f["farm_name"] for f in result["farms"]] == ["Due Today", "Mid Rotation"]


async def test_off_rotation_farms_keep_their_herd_data(db):
    """The rotation is a route concern. Pregnancy data must not blink in and
    out with the visit schedule — the spec keeps a cow on the Pregnancy Report
    until a result is entered."""
    mid_rotation = _farm_not_due_today()
    mid_rotation.name = "Mid Rotation"
    db.add(mid_rotation)
    await db.flush()
    db.add(Cow(id=uuid.uuid4(), farm_id=mid_rotation.id, ear_tag="P-1",
               status=CowStatus.inseminated, lactation_number=1,
               last_insemination_date=TODAY - timedelta(days=55)))
    await db.flush()

    admin = {"id": uuid.uuid4(), "role": "admin", "farm_id": None}
    result = await build_worklist(db, admin, TODAY)
    row = next(f for f in result["farms"] if f["farm_name"] == "Mid Rotation")
    assert row["schedule"] == "not_due"
    assert row["schedule_label"] == "Not on today's rotation"
    assert any(r["type"] == "pregnancy-check" for r in row["reports"]), \
        "day-55 cow disappeared from the pregnancy view on an off-rotation day"


async def test_vet_worklist_is_scoped_to_pregnancy_work(db):
    """Vet Area spec: exclusively pregnancy diagnosis. The vet payload must not
    carry the technician's needling/heat/post-calving route."""
    from app.models.models import Vet, VetFarmAssignment

    vet_user = User(id=uuid.uuid4(), name="Vet", email=f"{uuid.uuid4().hex[:8]}@t.local",
                    role=UserRole.vet)
    db.add(vet_user)
    await db.flush()
    vet = Vet(id=uuid.uuid4(), user_id=vet_user.id, name="Vet")
    farm = _farm_not_due_today()  # off-rotation on purpose
    db.add_all([vet, farm])
    await db.flush()
    db.add(VetFarmAssignment(vet_id=vet.id, farm_id=farm.id))
    db.add_all([
        Cow(id=uuid.uuid4(), farm_id=farm.id, ear_tag="P-2",
            status=CowStatus.inseminated, lactation_number=1,
            last_insemination_date=TODAY - timedelta(days=40)),
        # Would be Post Calving work on a technician's list.
        Cow(id=uuid.uuid4(), farm_id=farm.id, ear_tag="F-2",
            status=CowStatus.fresh, lactation_number=1,
            last_calving_date=TODAY - timedelta(days=35)),
    ])
    await db.flush()

    result = await build_worklist(db, {"id": vet_user.id, "role": "vet", "farm_id": None}, TODAY)
    assert len(result["farms"]) == 1
    types = {r["type"] for r in result["farms"][0]["reports"]}
    assert "pregnancy-check" in types
    assert types <= {"pregnancy-check", "pregnant", "calving-due"}, \
        f"vet payload leaked technician reports: {types}"


async def test_worklist_flags_a_farm_handed_to_a_relief_technician(db):
    mine = User(id=uuid.uuid4(), name="Mine", email=f"{uuid.uuid4().hex[:8]}@t.local",
                role=UserRole.technician)
    relief = User(id=uuid.uuid4(), name="Relief Tech", email=f"{uuid.uuid4().hex[:8]}@t.local",
                  role=UserRole.technician)
    db.add_all([mine, relief])
    await db.flush()

    farm = _farm_due_today(tech=mine.id)
    farm.name = "Vandenberg Farm"
    db.add(farm)
    await db.flush()
    db.add(FarmVisitAssignment(id=uuid.uuid4(), farm_id=farm.id, visit_date=TODAY,
                               assigned_technician_id=relief.id, reason="on leave"))
    await db.flush()

    result = await build_worklist(db, {"id": mine.id, "role": "technician", "farm_id": None}, TODAY)
    row = result["farms"][0]
    assert row["schedule"] == "reassigned"
    assert row["schedule_label"] == "Reassigned to Relief Tech — Skip"
    assert row["covering_technician"] == "Relief Tech"

    covering = await build_worklist(
        db, {"id": relief.id, "role": "technician", "farm_id": None}, TODAY
    )
    assert covering["farms"][0]["schedule"] == "covering"


@pytest.mark.parametrize("report_type,role,can_record", [
    # Vets record pregnancy results and nothing else — the API agrees.
    ("pregnancy-check", "vet", True),
    ("pregnancy-check", "technician", True),
    ("pregnancy-check", "admin", True),
    ("heat", "vet", False),
    ("heat", "technician", True),
    ("needling", "vet", False),
    ("timed-breeding", "vet", False),
    ("open-report", "vet", False),
    # A farm manager records nothing anywhere.
    ("heat", "farm", False),
    ("pregnancy-check", "farm", False),
])
def test_record_forms_match_the_api_role_gates(report_type, role, can_record):
    """A row must not offer a form the API rejects. A vet once filled in a whole
    insemination and was refused on submit — record_roles here must mirror each
    router's require_roles()."""
    cows = [
        _cow(status=CowStatus.inseminated,
             last_insemination_date=TODAY - timedelta(days=40)),
        _cow(status=CowStatus.inseminated,
             last_insemination_date=TODAY - timedelta(days=22)),
        _cow(status=CowStatus.open, last_calving_date=TODAY - timedelta(days=90)),
        _cow(status=CowStatus.needling),
    ]
    ctx = _ctx(cows, role=role, needling={str(cows[3].id): {
        "id": str(uuid.uuid4()), "treatment": "2cc PGF", "protocol_day": 7,
        "protocol": "ovsynch", "days_overdue": 0, "enrollment_id": str(uuid.uuid4()),
    }}, breeding={str(cows[3].id): {
        "protocol": "ovsynch", "protocol_day": 10, "treatment": "2cc GnRH + Insemination",
        "injection": "2cc GnRH", "needling_record_id": str(uuid.uuid4()),
        "needling_completed": False, "days_overdue": 0,
    }})

    report = {r["type"]: r for r in build_reports(ctx)}.get(report_type)
    if report is None:
        pytest.skip(f"{report_type} has no rows in this fixture")
    assert report["can_record"] is can_record
    kinds = {c["record_kind"] for c in report["cows"]}
    if can_record:
        assert kinds != {None}, "recordable report offered no form"
    else:
        assert kinds == {None}, "offered a form the API would reject with 403"
