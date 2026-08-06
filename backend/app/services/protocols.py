"""
Needling protocol schedules (per the Major Dairy AI requirement docs).
Each protocol is a list of dicts: {day: int, treatment: str, is_final: bool}
Day 1 = start_date. The is_final flag marks the protocol's last scheduled day
structurally — never rely on string matching of the treatment text.

`is_final` means "last step of the protocol". It does NOT by itself mean
"timed-AI day": Prostaglandin Heat ends with *conditional* insemination on
observed heat, so it must not be pulled onto the Timed Breeding report or
excluded from the Needling report by the same-day overlap rule. Use
TIMED_AI_PROTOCOLS for that distinction.
"""

from datetime import date, timedelta
from typing import List, Dict

# Protocols that end in a scheduled (timed) insemination. Prostaglandin Heat is
# deliberately absent — its final day is heat observation with AI only if the
# cow is actually in heat, which the technician records as a heat event.
TIMED_AI_PROTOCOLS = frozenset({
    "ovsynch",
    "double_ovsynch",
    "presynch",
    "general_synch",
    "general_synch_2",
})

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


# Display names. `cows.current_program` and `enrollments.protocol` store the raw
# enum value ("ovsynch"), which must never reach a technician's instruction line.
PROTOCOL_LABELS = {
    "ovsynch": "Ovsynch",
    "prostaglandin_heat": "PGF Heat",
    "double_ovsynch": "Double Ovsynch",
    "presynch": "Presynch",
    "general_synch": "General Synch",
    "general_synch_2": "General Synch 2",
}


def protocol_label(protocol) -> str:
    """Human label for a protocol value, enum or string. Falls back to the raw
    value so an unknown protocol shows *something* rather than vanishing."""
    if protocol is None:
        return "Protocol"
    raw = getattr(protocol, "value", protocol)
    return PROTOCOL_LABELS.get(raw, raw or "Protocol")


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
