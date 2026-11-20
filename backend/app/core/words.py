"""Plain words for messages a person reads (error messages shown in the app).

The app shows the server's message as it is, so it must read like a sentence,
not like code: no field names, no status codes.
"""

_STATUS = {
    "calf": "a calf",
    "heifer": "a heifer",
    "fresh": "Fresh",
    "open": "Open",
    "needling": "on a protocol",
    "inseminated": "Inseminated",
    "pregnant": "Pregnant",
    "dry": "Dry",
    "dnb": "marked Do Not Breed",
    "cull": "culled",
    "sold": "sold",
    "dead": "dead",
}


def status_words(status) -> str:
    """'She is ___': the cow's status as words."""
    value = getattr(status, "value", status)
    return _STATUS.get(str(value), str(value))


def field_words(loc) -> str:
    """A request field's name as words ("check_date" -> "check date")."""
    parts = [str(p) for p in loc if p not in ("body", "query", "path") and not str(p).isdigit()]
    return (parts[-1] if parts else "details").replace("_", " ")
