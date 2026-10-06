"""Import a DairyComp 305 herd list (.xls or .csv) into one farm.

  cd backend
  .venv/bin/python -m scripts.import_dairycomp HERD.xls --farm-name "Farm Name"   # dry run
  .venv/bin/python -m scripts.import_dairycomp HERD.xls --farm-id <uuid> --apply

A dry run (the default) does the whole import inside one transaction, runs the
lifecycle sweep the app runs when its reports load, prints what each report
will show on day one, and then rolls everything back: nothing is written and
no notification is raised. --apply commits.

It only ever ADDS. An animal whose ID is already on the farm is reported and
left alone, so the app's own records -- heats, inseminations, checks recorded
since -- always win over an older export. Re-running a later export therefore
adds the farm's new animals and nothing else.

The farm is never given an email address here: the app emails a farm
automatically (dry-off, breeding, pregnancy-check reminders), and a real farm
should not start receiving those until someone decides it should.

Mapping rules live in app/services/dairycomp.py. Reading .xls needs `xlrd`
(pip install xlrd); it is not a server dependency, because only this script
reads DairyComp's old Excel format.
"""

import argparse
import asyncio
import csv
import os
import sys
import uuid
from collections import Counter
from datetime import date
from typing import Dict, List
from urllib.parse import quote_plus

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.timeutils import local_today
from app.models.models import Farm
from app.services import dairycomp
from app.services import status_engine
from app.services.worklist_builder import build_worklist

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def read_rows(path: str) -> List[Dict]:
    if path.lower().endswith(".xls"):
        try:
            import xlrd
        except ImportError:
            sys.exit("Reading .xls needs xlrd:  .venv/bin/pip install xlrd")
        sheet = xlrd.open_workbook(path).sheet_by_index(0)
        headers = dairycomp.normalize_headers(sheet.row_values(0))
        return [dict(zip(headers, sheet.row_values(i))) for i in range(1, sheet.nrows)]
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        headers = dairycomp.normalize_headers(next(reader))
        return [dict(zip(headers, row)) for row in reader]


def _guard_apply() -> None:
    """--apply against a database that is not on this machine must be meant:
    the connection comes from DB_HOST/DB_NAME in .env, which is production."""
    host = (settings.db_host or "").strip().lower()
    if host in LOCAL_HOSTS:
        return
    if os.getenv("IMPORT_TARGET_HOST", "").strip().lower() == host:
        return
    sys.exit(
        f"REFUSING TO WRITE to {host}/{settings.db_name}, which is not a local database.\n"
        f"If that is intended, re-run with IMPORT_TARGET_HOST={host}"
    )


async def run(args) -> None:
    rows = read_rows(args.file)
    export_date = (date.fromisoformat(args.export_date) if args.export_date
                   else dairycomp.derive_export_date(rows))
    if export_date is None:
        sys.exit("Could not work out the export date from the file; pass --export-date YYYY-MM-DD")
    today = local_today()
    plan = dairycomp.plan_rows(rows, export_date, today)

    port = 5432 if settings.db_port == 6543 else settings.db_port
    engine = create_async_engine(
        f"postgresql+asyncpg://{settings.db_user}:{quote_plus(settings.db_password)}"
        f"@{settings.db_host}:{port}/{settings.db_name}",
        poolclass=NullPool,
    )
    print(f"Target database: {settings.db_host}/{settings.db_name}   "
          f"({'WRITING' if args.apply else 'dry run — nothing will be kept'})")
    print(f"File: {os.path.basename(args.file)} · exported {export_date} · today {today}\n")

    if args.apply:
        async with async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)() as db:
            await _import(db, args, plan, export_date, today)
    else:
        await _dry_run(engine, args, plan, export_date, today)
    await engine.dispose()


async def _dry_run(engine, args, plan, export_date: date, today: date) -> None:
    """Everything a real import would do, kept by nothing.

    Two things make that true, and both are needed:

    * one outer transaction, rolled back at the end, with the session joined
      to it as a SAVEPOINT -- so a commit() anywhere inside (the lifecycle
      sweep commits its own transitions) only releases a savepoint. Without
      this the first dry run against the scratch database kept all 563 cows;
    * email and push delivery switched off. Both fire after COMMIT from a
      background task on the APPLICATION engine, so a savepoint "commit" would
      still have emailed the farm (the same trap tests/conftest.py closes).
    """
    from app.services import notifications, push

    notifications._schedule_email = lambda *a, **k: None
    push._schedule = lambda *a, **k: None
    async with engine.connect() as conn:
        outer = await conn.begin()
        db = AsyncSession(bind=conn, join_transaction_mode="create_savepoint",
                          expire_on_commit=False)
        try:
            await _import(db, args, plan, export_date, today)
        finally:
            await db.close()
            await outer.rollback()
    print("\nDry run: rolled back. Nothing was written, nothing was sent.")


async def _import(db: AsyncSession, args, plan, export_date: date, today: date) -> None:
    farm = await _farm(db, args)
    added, already = await dairycomp.write_plan(db, farm.id, plan, export_date)
    _print_plan(plan, added, already)
    if args.held_out_csv:
        with open(args.held_out_csv, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["row", "ID", "reason"])
            for h in plan.skipped:
                w.writerow([h.row, h.ear_tag, h.reason])
        print(f"Held-out animals listed in {args.held_out_csv}")

    if args.apply:
        await db.commit()
        print(f"\nWROTE {len(added)} animals to {farm.name} ({farm.id}).")
    else:
        await db.commit()  # releases a savepoint only -- see _dry_run
        # What the technician will see: the sweep the app runs on load,
        # then the farm's reports -- inside the same doomed transaction.
        await status_engine.run_lifecycle_transitions(db, farm_ids=[farm.id], today=today)
        wl = await build_worklist(
            db, {"id": uuid.uuid4(), "role": "admin", "farm_id": None}, today,
            farm_id=farm.id,
        )
        print("\nDay one, after the app's own sweep — reports for this farm:")
        for f in wl["farms"]:
            for r in f["reports"]:
                kind = "work" if r["is_work_report"] else "list"
                print(f"  {r['title']:<26} {r['count']:>4}   ({kind})")


async def _farm(db: AsyncSession, args) -> Farm:
    if args.farm_id:
        farm = await db.get(Farm, uuid.UUID(args.farm_id))
        if farm is None:
            sys.exit(f"No farm {args.farm_id}")
        return farm
    found = (await db.execute(select(Farm).where(Farm.name == args.farm_name))).scalars().all()
    if len(found) == 1:
        return found[0]
    if len(found) > 1:
        sys.exit(f"{len(found)} farms are called {args.farm_name!r}; pass --farm-id")
    if args.apply and not args.create_farm:
        sys.exit(f"No farm called {args.farm_name!r}. Create it in the app first, "
                 "or pass --create-farm --owner-name NAME")
    farm = Farm(id=uuid.uuid4(), name=args.farm_name,
                owner_name=args.owner_name or "(to be confirmed)", herd_size=0)
    db.add(farm)
    await db.flush()
    print(f"Farm {args.farm_name!r} {'created' if args.apply else 'stand-in for the dry run'} "
          "(no email address — see the module docstring)")
    return farm


def _print_plan(plan: dairycomp.Plan, added, already) -> None:
    print(f"Animals in the file: {len(plan.cows) + len(plan.skipped) + len(plan.problems)}")
    print(f"  to add:            {len(added)}")
    if already:
        print(f"  already on farm:   {len(already)} (left as they are)")
    print(f"  held out:          {len(plan.skipped)}")
    for reason, n in Counter(h.reason for h in plan.skipped).most_common():
        print(f"      {n:>4} × {reason}")
    print(f"  could not read:    {len(plan.problems)}")
    for row, tag, why in plan.problems:
        print(f"      row {row} (ID {tag}): {why}")
    print("\nHow they will be held:")
    by = Counter((p.dc_status, p.status.value + (" · ready for 1st breeding"
                                                 if p.current_program else "")) for p in added)
    for (dc, app), n in sorted(by.items()):
        print(f"  {dc:<8} → {app:<34} {n:>4}")
    print(f"  with an insemination record: {sum(1 for p in added if p.insemination_date)}"
          f" · sire known: {sum(1 for p in added if p.sire)}"
          f" · maternal sire known: {sum(1 for p in added if p.maternal_sire)}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("file")
    who = ap.add_mutually_exclusive_group(required=True)
    who.add_argument("--farm-id")
    who.add_argument("--farm-name")
    ap.add_argument("--create-farm", action="store_true",
                    help="with --apply: create the farm if no farm has that name")
    ap.add_argument("--owner-name")
    ap.add_argument("--export-date", help="YYYY-MM-DD (default: read from the file)")
    ap.add_argument("--held-out-csv", help="write the held-out animals' IDs to this file")
    ap.add_argument("--apply", action="store_true", help="write (default is a dry run)")
    args = ap.parse_args()
    if args.apply:
        _guard_apply()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
