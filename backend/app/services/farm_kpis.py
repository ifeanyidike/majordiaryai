"""A farm's KPI page: three KPIs with the raw numbers behind them.

Josh (Nov 20): "pick the 3 easiest ... make a page showing raw data ... KPI
for each farm". From his "Major Dairy AI KPI" document, as he defines them:

  8. Conception Rate             Confirmed Pregnancies / Total Inseminations
  2. Hard Pregnancy Count        Count of confirmed pregnancies by month
  3. Pregnancy by Semen Type     Pregnancies / Inseminations using semen type

"Confirmed Pregnancy: an insemination that resulted in a positive pregnancy
check." He gives no period, so every record the farm has is counted.
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional


@dataclass
class Breeding:
    id: uuid.UUID
    date: date
    semen_type: Optional[str]


@dataclass
class Check:
    insemination_id: uuid.UUID
    check_date: date
    result: Optional[str]          # "pregnant" | "not_pregnant" | None


# Rows in the order of Josh's example table (Sexed Semen, then Conventional),
# with breedings that have no semen type last.
_SEMEN_ORDER = ["sexed", "conventional", "beef", "not recorded"]


def _semen_order(semen: str) -> tuple:
    return (_SEMEN_ORDER.index(semen) if semen in _SEMEN_ORDER else len(_SEMEN_ORDER), semen)


def _rate(pregnant: int, inseminated: int) -> Optional[float]:
    return None if inseminated == 0 else round(100.0 * pregnant / inseminated, 1)


def _month_after(ym: str) -> str:
    y, m = int(ym[:4]), int(ym[5:])
    return f"{y + m // 12}-{m % 12 + 1:02d}"


def compute(breedings: List[Breeding], checks: List[Check], today: date) -> dict:
    # When each insemination was first confirmed pregnant.
    confirmed: Dict[uuid.UUID, date] = {}
    for c in checks:
        if c.result == "pregnant":
            prev = confirmed.get(c.insemination_id)
            confirmed[c.insemination_id] = c.check_date if prev is None else min(prev, c.check_date)
    known = {b.id for b in breedings}
    confirmed = {k: v for k, v in confirmed.items() if k in known}

    # By month: every month from the first confirmed pregnancy to this one.
    per_month: Dict[str, int] = defaultdict(int)
    for d in confirmed.values():
        per_month[d.strftime("%Y-%m")] += 1
    months: List[str] = []
    if per_month:
        cursor, last = min(per_month), today.strftime("%Y-%m")
        while cursor <= last:
            months.append(cursor)
            cursor = _month_after(cursor)

    groups: Dict[str, List[Breeding]] = defaultdict(list)
    for b in breedings:
        groups[b.semen_type or "not recorded"].append(b)

    pregnant = sum(1 for b in breedings if b.id in confirmed)
    return {
        "conception": {
            "inseminated": len(breedings), "pregnant": pregnant,
            "rate": _rate(pregnant, len(breedings)),
        },
        "pregnancies_by_month": [{"month": m, "pregnant": per_month.get(m, 0)} for m in months],
        "by_semen": [
            {
                "semen_type": semen, "inseminated": len(rows),
                "pregnant": sum(1 for b in rows if b.id in confirmed),
                "rate": _rate(sum(1 for b in rows if b.id in confirmed), len(rows)),
            }
            for semen, rows in sorted(groups.items(), key=lambda kv: _semen_order(kv[0]))
        ],
    }
