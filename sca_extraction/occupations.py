"""SCA Directory of Occupations lookup.

Used to (a) validate that a 5-digit code is a real occupation, and (b) confirm
a repaired code by checking whether an OCR-correction candidate actually exists.
The bundled directory is a curated *subset* (see the JSON header); a full copy
can be supplied via :func:`load_directory`.
"""

from __future__ import annotations

import json
import os
from difflib import SequenceMatcher
from functools import lru_cache
from typing import Optional

_DATA_PATH = os.path.join(os.path.dirname(__file__), "data", "sca_directory.json")


class Directory:
    """In-memory index of code -> canonical title with fuzzy title lookup."""

    def __init__(self, mapping: dict[str, str]):
        self._by_code = dict(mapping)
        # title (lowercased) -> code, for reverse/fuzzy matching
        self._by_title = {t.lower(): c for c, t in mapping.items()}

    def __len__(self) -> int:
        return len(self._by_code)

    def has_code(self, code: str) -> bool:
        return code in self._by_code

    def title_for(self, code: str) -> Optional[str]:
        return self._by_code.get(code)

    def best_title_match(self, title: str, cutoff: float = 0.72) -> Optional[tuple[str, str, float]]:
        """Return (code, canonical_title, ratio) for the closest title, or None.

        Helps recover a code when the code column is corrupt but the title read
        cleanly (or vice versa).  Never used to *invent* a rate — only to
        propose a code candidate for confirmation.
        """
        title_l = title.strip().lower()
        if not title_l:
            return None
        exact = self._by_title.get(title_l)
        if exact is not None:
            return (exact, self._by_code[exact], 1.0)
        best: Optional[tuple[str, str, float]] = None
        for t_l, code in self._by_title.items():
            ratio = SequenceMatcher(None, title_l, t_l).ratio()
            if best is None or ratio > best[2]:
                best = (code, self._by_code[code], ratio)
        if best is not None and best[2] >= cutoff:
            return best
        return None


def load_directory(path: Optional[str] = None) -> Directory:
    """Load a directory from JSON. Defaults to the bundled subset."""
    path = path or _DATA_PATH
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    return Directory(data["occupations"])


@lru_cache(maxsize=1)
def default_directory() -> Directory:
    """Process-wide singleton for the bundled directory."""
    return load_directory()
