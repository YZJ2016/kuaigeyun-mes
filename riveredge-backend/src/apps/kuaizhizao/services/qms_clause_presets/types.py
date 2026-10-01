from __future__ import annotations

from typing import List, Optional, TypedDict


class ClausePresetItem(TypedDict):
    clause_code: str
    title: str
    parent_code: Optional[str]
    sort_order: int
