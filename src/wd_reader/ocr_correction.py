"""OCR corruption detection and correction for occupation codes (spec Sec. 1, 5).

The reference document (WD 2015-5657, a scanned image PDF) produced corruptions
like ``01311 -> @1311``, ``01313 -> 61313``, ``09000 -> e9eee``. This module
recovers the true 5-digit code by:

  1. mapping known OCR homoglyphs of digits back to digits, and
  2. for characters that are already plausible digits, trying common
     digit<->digit OCR confusions (``6<->0``, ``8<->0``, ``1<->7`` ...),

then ranking every candidate that lands in the SCA Directory by a combined
score of edit distance to the raw code and how well the OCR'd title matches the
Directory title for that candidate.

Crucially this never *invents* a code: candidates are only ever real Directory
codes. If nothing scores, the code is unrecoverable and must go to hard
confirmation (spec Sections 6, 8).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from . import sca_directory


# Homoglyph -> digit. A character in a code position that reads as one of these
# is almost certainly the mapped digit. '0' is by far the most-corrupted digit
# on real scans, which is why so many glyphs map to it.
_HOMOGLYPH_TO_DIGIT: dict[str, str] = {
    "@": "0", "e": "0", "o": "0", "O": "0", "Q": "0", "D": "0", "C": "0",
    "l": "1", "I": "1", "i": "1", "|": "1", "!": "1",
    "z": "2", "Z": "2",
    "E": "3",
    "A": "4", "h": "4",
    "s": "5", "S": "5",
    "b": "6", "G": "6",
    "T": "7", "t": "7", "?": "7",
    "B": "8",
    "g": "9", "q": "9",
}

# Digit -> digits it is commonly confused *with* on scans (both directions of
# the frequent pairs). Used to repair an all-digit-but-wrong code like 61313.
_DIGIT_CONFUSIONS: dict[str, tuple[str, ...]] = {
    "0": ("6", "8", "9"),
    "1": ("7",),
    "2": ("7",),
    "5": ("6",),
    "6": ("0", "8", "5"),
    "7": ("1", "2"),
    "8": ("0", "6", "3"),
    "9": ("0",),
    "3": ("8",),
}


@dataclass
class CodeCandidate:
    code: str
    edit_distance: int  # from the normalized raw code
    title_similarity: float  # 0.0-1.0 vs OCR'd title, 1.0 if no title given
    score: float  # combined; higher is better


@dataclass
class CorrectionResult:
    raw: str
    normalized: str  # homoglyphs mapped to digits, best-effort
    was_corrupted: bool  # raw differed from a clean valid code
    candidates: list[CodeCandidate]  # ranked best-first, real Directory codes

    @property
    def best(self) -> Optional[CodeCandidate]:
        return self.candidates[0] if self.candidates else None

    @property
    def recoverable(self) -> bool:
        return bool(self.candidates)


def normalize_glyphs(raw: str) -> str:
    """Map homoglyphs to digits and strip anything that is not code-relevant.
    Does not force a length; downstream decides if the result is well-formed."""
    out = []
    for ch in raw.strip():
        if ch.isdigit():
            out.append(ch)
        elif ch in _HOMOGLYPH_TO_DIGIT:
            out.append(_HOMOGLYPH_TO_DIGIT[ch])
        # any other character (spaces, stray punctuation) is dropped
    return "".join(out)


def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(
                min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb))
            )
        prev = cur
    return prev[-1]


def _title_similarity(ocr_title: Optional[str], code: str) -> float:
    """Normalized similarity of the OCR'd title to the Directory title for
    ``code``. 1.0 when no OCR title is available (neutral, not penalizing)."""
    if not ocr_title:
        return 1.0
    canon = sca_directory.title_for(code)
    if not canon:
        return 0.0
    a = _norm_title(ocr_title)
    b = _norm_title(canon)
    if not a or not b:
        return 0.0
    dist = _levenshtein(a, b)
    return 1.0 - dist / max(len(a), len(b))


def _norm_title(s: str) -> str:
    return "".join(ch for ch in s.lower() if ch.isalnum() or ch == " ").strip()


def _digit_variants(normalized: str, max_edits: int = 2) -> set[str]:
    """All 5-digit strings reachable from ``normalized`` by up to ``max_edits``
    single-position digit confusions. Bounded and deterministic."""
    if len(normalized) != 5:
        return set()
    results: set[str] = {normalized}
    frontier = {normalized}
    for _ in range(max_edits):
        nxt: set[str] = set()
        for cand in frontier:
            for i, d in enumerate(cand):
                for repl in _DIGIT_CONFUSIONS.get(d, ()):
                    variant = cand[:i] + repl + cand[i + 1:]
                    if variant not in results:
                        nxt.add(variant)
        results |= nxt
        frontier = nxt
    return results


def correct_code(raw: str, ocr_title: Optional[str] = None) -> CorrectionResult:
    """Recover the true occupation code from a (possibly corrupted) OCR string.

    Returns a :class:`CorrectionResult` whose candidates are always real
    Directory codes, ranked best-first. Never fabricates a code.
    """
    normalized = normalize_glyphs(raw)

    # Fast path: already a clean, valid, uncorrupted code.
    if sca_directory.is_valid_code(raw) and raw == normalized:
        return CorrectionResult(
            raw=raw,
            normalized=normalized,
            was_corrupted=False,
            candidates=[CodeCandidate(raw, 0, _title_similarity(ocr_title, raw), 1.0)],
        )

    # Gather candidate codes from three independent signals:
    #  1. the normalized (homoglyph-mapped) form, if it is a valid code;
    #  2. every valid Directory code reachable by bounded digit confusions;
    #  3. every Directory code whose title closely matches the OCR'd title.
    # Signal 3 recovers cases where the digits are corrupted beyond the
    # confusion table but the title read cleanly (e.g. "Secretary III").
    candidate_codes: set[str] = set()
    if sca_directory.is_valid_code(normalized):
        candidate_codes.add(normalized)
    for variant in _digit_variants(normalized):
        if sca_directory.is_valid_code(variant):
            candidate_codes.add(variant)
    if ocr_title:
        for code in sca_directory.all_codes():
            if _title_similarity(ocr_title, code) >= 0.85:
                candidate_codes.add(code)

    scored: list[CodeCandidate] = []
    for code in candidate_codes:
        dist = _levenshtein(normalized, code)
        sim = _title_similarity(ocr_title, code)
        # The title is the primary key: it carries far more signal than the
        # 5-digit code and is what disambiguates 61313->01313. An exact title
        # match is rewarded decisively; a partial one is discounted. Glyph-space
        # closeness (edit distance) is only a tiebreaker.
        title_score = 1.0 if sim >= 0.999 else sim * 0.7
        distance_factor = 1.0 / (1.0 + 0.3 * dist)
        score = title_score * distance_factor
        scored.append(CodeCandidate(code, dist, sim, round(score, 6)))

    scored.sort(key=lambda c: (-c.score, c.edit_distance, c.code))

    # was_corrupted: raw wasn't already a clean valid code.
    was_corrupted = not (sca_directory.is_valid_code(raw) and raw == normalized)
    return CorrectionResult(
        raw=raw,
        normalized=normalized,
        was_corrupted=was_corrupted,
        candidates=scored,
    )
