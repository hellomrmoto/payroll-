"""OCR corruption repair for SCA occupation codes and mangled titles.

Codes are the dangerous field: a wrong code silently mispairs a worker with the
wrong wage. So repair is *constrained* — we only ever propose a corrected code
that actually exists in the SCA Directory of Occupations, and we never collapse
an ambiguous set down to one silently. Multiple surviving candidates -> hard
confirm. Zero survivors -> hard confirm. Exactly one -> corrected, but with a
confidence penalty and a ``code_corrected`` flag.

Known corruption patterns baked in from real documents:
  * leading ``0`` -> ``@``            (``01311`` -> ``@1311``)
  * ``0`` -> ``6``                    (``01313`` -> ``61313``)
  * ``0`` -> ``e``                    (``09000`` -> ``e9eee``)
  * roman numerals mangled            (``III`` -> ``IIT``)
"""

from __future__ import annotations

import itertools
import re
from dataclasses import dataclass, field
from typing import Optional

from .occupations import Directory, default_directory

# For each observed (corrupt) character, the digit(s) it might really be.
# A character maps to a *set* of candidates; the real digit is always included
# for genuine digits so we never discard a legitimate reading.
_CHAR_CANDIDATES: dict[str, tuple[str, ...]] = {
    "@": ("0",),
    "e": ("0",),
    "E": ("0",),
    "o": ("0",),
    "O": ("0",),
    "D": ("0",),
    "Q": ("0",),
    "l": ("1",),
    "I": ("1",),
    "|": ("1",),
    "S": ("5",),
    "s": ("5",),
    "B": ("8",),
    "g": ("9",),
    "q": ("9",),
    "b": ("6",),
    # Genuine digits that are commonly *confused for each other* by OCR: keep
    # the literal reading plus the plausible alternates so directory lookup can
    # arbitrate. 6<->0 and 8<->0 are the documented failure directions.
    "0": ("0", "6", "8"),
    "1": ("1", "7"),
    "5": ("5", "6"),
    "6": ("6", "0", "8"),
    "7": ("7", "1"),
    "8": ("8", "0"),
    "9": ("9",),
    "2": ("2",),
    "3": ("3",),
    "4": ("4",),
}

_MAX_CANDIDATES = 256  # guard against combinatorial blow-up on pathological input


@dataclass
class CodeRepair:
    """Outcome of attempting to repair a raw code string."""

    raw: str
    normalized: str            # raw with whitespace/separators stripped
    corrected: Optional[str]   # the single valid code, if unambiguous
    candidates: list[str] = field(default_factory=list)  # all directory-valid options
    was_corrupt: bool = False  # raw contained non-digit corruption
    is_clean_valid: bool = False  # raw was already 5 clean digits in directory
    reason: str = ""

    @property
    def ambiguous(self) -> bool:
        return len(self.candidates) > 1

    @property
    def resolved(self) -> bool:
        return self.corrected is not None


def _normalize(raw: str) -> str:
    """Strip spaces and common separators; keep the glyphs themselves."""
    return re.sub(r"[\s\-.]", "", raw.strip())


def repair_code(raw: str, directory: Optional[Directory] = None) -> CodeRepair:
    """Attempt to repair ``raw`` into a valid 5-character SCA code.

    Strategy:
      1. Normalise separators.
      2. If it is already 5 clean digits and in the directory -> accept as-is.
      3. Otherwise generate candidate digit-strings from per-char alternates,
         keep only length-5 all-digit strings that exist in the directory.
      4. Exactly one survivor -> corrected. Zero or many -> unresolved (confirm).
    """
    directory = directory or default_directory()
    norm = _normalize(raw)
    was_corrupt = not norm.isdigit() or len(norm) != 5

    # Fast path: already a clean, known 5-digit code.
    if norm.isdigit() and len(norm) == 5 and directory.has_code(norm):
        return CodeRepair(
            raw=raw,
            normalized=norm,
            corrected=norm,
            candidates=[norm],
            was_corrupt=False,
            is_clean_valid=True,
            reason="clean_valid",
        )

    # Wrong length after normalisation is unrecoverable without more signal.
    if len(norm) != 5:
        return CodeRepair(
            raw=raw,
            normalized=norm,
            corrected=None,
            candidates=[],
            was_corrupt=True,
            reason=f"length_{len(norm)}_expected_5",
        )

    # Build per-position candidate lists.
    per_pos: list[tuple[str, ...]] = []
    for ch in norm:
        cands = _CHAR_CANDIDATES.get(ch)
        if cands is None:
            # Unknown glyph we have no mapping for -> nothing plausible.
            per_pos = []
            break
        per_pos.append(cands)

    valid: list[str] = []
    if per_pos:
        combos = 1
        for c in per_pos:
            combos *= len(c)
        if combos <= _MAX_CANDIDATES:
            seen: set[str] = set()
            for combo in itertools.product(*per_pos):
                candidate = "".join(combo)
                if candidate in seen:
                    continue
                seen.add(candidate)
                if directory.has_code(candidate):
                    valid.append(candidate)

    valid = sorted(set(valid))
    if len(valid) == 1:
        return CodeRepair(
            raw=raw,
            normalized=norm,
            corrected=valid[0],
            candidates=valid,
            was_corrupt=was_corrupt,
            reason="corrected_unique",
        )
    if len(valid) > 1:
        return CodeRepair(
            raw=raw,
            normalized=norm,
            corrected=None,
            candidates=valid,
            was_corrupt=was_corrupt,
            reason="ambiguous_multiple_directory_matches",
        )
    return CodeRepair(
        raw=raw,
        normalized=norm,
        corrected=None,
        candidates=[],
        was_corrupt=was_corrupt,
        reason="no_directory_match",
    )


# --- Roman numeral repair (for titles like "Secretary III") -----------------

_ROMAN_FIX = {
    "IIT": "III",
    "IIl": "III",
    "1II": "III",
    "II1": "III",
    "1I": "II",
    "I1": "II",
    "IV1": "IV",
    "lV": "IV",
}

_ROMAN_TOKEN = re.compile(r"\b([IiVvXxLl1l|T]{1,4})\b")


def repair_title_roman(title: str) -> tuple[str, bool]:
    """Fix common roman-numeral OCR mangles in an occupation title.

    Returns (repaired_title, changed). Conservative: only touches trailing
    numeral-looking tokens, never the descriptive words.
    """
    changed = False
    parts = title.split()
    if parts:
        last = parts[-1]
        fixed = _ROMAN_FIX.get(last)
        if fixed is not None:
            parts[-1] = fixed
            changed = True
    return (" ".join(parts), changed)
