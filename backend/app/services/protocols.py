"""
Needling protocol schedules (per the Major Dairy AI requirement docs).
Each protocol is a list of dicts: {day: int, treatment: str, is_final: bool}
Day 1 = start_date. The is_final flag marks the protocol's final (AI) day
structurally — never rely on string matching of the treatment text.
"""

from datetime import date, timedelta
from typing import List, Dict

PROTOCOLS: Dict[str, List[Dict]] = {
    "ovsynch": [
        {"day": 1,  "treatment": "2cc GnRH"},
        {"day": 7,  "treatment": "2cc PGF"},
        {"day": 10, "treatment": "2cc GnRH + Insemination", "is_final": True},
    ],
    "prostaglandin_heat": [
        {"day": 1, "treatment": "2cc PGF"},
        {"day": 3, "treatment": "Heat Examination"},
        {"day": 4, "treatment": "Heat Observation"},
        {"day": 5, "treatment": "Heat Observation + Insemination if in heat", "is_final": True},
    ],
    "double_ovsynch": [
        {"day": 1,  "treatment": "2cc GnRH"},
        {"day": 7,  "treatment": "2cc PGF"},
        {"day": 10, "treatment": "2cc GnRH"},
        {"day": 17, "treatment": "2cc GnRH"},
        {"day": 24, "treatment": "2cc PGF"},
        {"day": 25, "treatment": "2cc PGF"},
        {"day": 27, "treatment": "2cc GnRH + Insemination", "is_final": True},
    ],
    "presynch": [
        {"day": 1,  "treatment": "2cc PGF"},
        {"day": 14, "treatment": "2cc PGF"},
        {"day": 17, "treatment": "2cc GnRH"},
        {"day": 24, "treatment": "2cc GnRH"},
        {"day": 31, "treatment": "2cc PGF"},
        {"day": 34, "treatment": "2cc GnRH + Insemination", "is_final": True},
    ],
    "general_synch": [
        {"day": 1,  "treatment": "2cc PGF"},
        {"day": 12, "treatment": "2cc GnRH"},
        {"day": 19, "treatment": "2cc PGF"},
        {"day": 22, "treatment": "2cc GnRH + Insemination", "is_final": True},
    ],
    "general_synch_2": [
        {"day": 1,  "treatment": "2cc PGF"},
        {"day": 10, "treatment": "2cc GnRH"},
        {"day": 17, "treatment": "2cc PGF"},
        {"day": 20, "treatment": "2cc GnRH + Insemination", "is_final": True},
    ],
}


class UnknownProtocolError(ValueError):
    """Raised for a protocol name not defined in PROTOCOLS."""


def get_protocol_steps(protocol: str) -> List[Dict]:
    steps = PROTOCOLS.get(protocol)
    if steps is None:
        raise UnknownProtocolError(f"Unknown protocol: {protocol}")
    return steps


def get_final_day(protocol: str) -> int:
    """Return the protocol day of the final (AI) step."""
    for step in get_protocol_steps(protocol):
        if step.get("is_final"):
            return step["day"]
    # Every protocol table above declares exactly one final step.
    raise UnknownProtocolError(f"Protocol has no final day: {protocol}")


def get_scheduled_records(protocol: str, start_date: date) -> List[Dict]:
    """Return list of records with absolute scheduled_date for each protocol step.

    Raises UnknownProtocolError for an unknown protocol name (callers must map
    this to a 422 — never silently return an empty schedule).
    """
    return [
        {
            "protocol_day": step["day"],
            "scheduled_date": start_date + timedelta(days=step["day"] - 1),
            "treatment": step["treatment"],
            "is_final": bool(step.get("is_final", False)),
        }
        for step in get_protocol_steps(protocol)
    ]
