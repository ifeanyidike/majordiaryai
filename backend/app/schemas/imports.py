from pydantic import BaseModel
from typing import List, Optional


class ImportRowError(BaseModel):
    """A single row that could not be imported.

    `row` is 1-based and INCLUDES the header row, so the first data row is 2.
    `ear_tag` is whatever we managed to read for that row (may be None).
    """
    row: int
    ear_tag: Optional[str] = None
    message: str


class ImportResult(BaseModel):
    filename: str
    total_rows: int          # number of DATA rows seen (header excluded)
    created: int
    updated: int
    skipped: int
    ignored_columns: List[str] = []
    errors: List[ImportRowError] = []
