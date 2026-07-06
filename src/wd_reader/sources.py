"""Source extraction: turning a PDF into a normalized ``Document`` of lines
that the deterministic engine parses (spec Section 3, steps 1-3b).

This is the adapter seam. The engine core depends only on :class:`Document`
and :class:`SourceLine`; how those get produced -- a PDF text layer, or
rasterize-then-OCR -- is behind the :class:`SourceExtractor` protocol.

  * :class:`TextLayerExtractor` is pure (no external process) and fully
    exercised by the test suite.
  * :class:`OcrExtractor` shells out to Poppler (``pdftoppm``) + Tesseract at
    >= 300 DPI with a layout-aware page-segmentation mode (PSM 6), per the
    spec. It is documented and structured but requires those binaries to be
    installed; it is *not* claimed to be exercised where they are absent.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Optional, Protocol

from .schema import SourceType


@dataclass
class SourceLine:
    """One line of extracted text with provenance for citation."""

    page: int
    index: int  # line number within the page
    text: str
    bbox: Optional[list[float]] = None  # [x0, y0, x1, y1] PDF points, if OCR
    column: Optional[int] = None  # detected column (0-based), if multi-column
    # Set by the OCR path when a rate token on this line was resolved from a
    # different layout column than the code -- the two-column separation
    # failure. The deterministic core reads this to flag rate_orphaned.
    rate_orphaned: bool = False

    def span(self) -> str:
        base = f"page {self.page} / line {self.index}"
        if self.bbox is not None:
            base += f" / bbox{self.bbox}"
        return base


@dataclass
class Document:
    lines: list[SourceLine] = field(default_factory=list)
    source_type: SourceType = SourceType.OCR
    ocr_dpi: Optional[int] = None
    # Document-level problems detected during extraction (spec Section 8).
    document_flags: list[str] = field(default_factory=list)

    def page_lines(self, page: int) -> list[SourceLine]:
        return [ln for ln in self.lines if ln.page == page]


class SourceExtractor(Protocol):
    def extract(self, pdf_path: str) -> Document: ...


class TextLayerExtractor:
    """Extracts an existing PDF text layer. Pure Python fallback splits an
    already-decoded text string; a real implementation would use Poppler's
    ``pdftotext -layout``. Provided here as the fully-testable path and as a
    constructor from pre-extracted text for deterministic tests."""

    @staticmethod
    def from_text(text: str, *, page: int = 1) -> Document:
        lines = [
            SourceLine(page=page, index=i, text=raw.rstrip())
            for i, raw in enumerate(text.splitlines())
        ]
        return Document(lines=lines, source_type=SourceType.TEXT_LAYER)

    def extract(self, pdf_path: str) -> Document:
        if not shutil.which("pdftotext"):
            raise SourceUnavailable(
                "pdftotext (Poppler) not installed; cannot read text layer"
            )
        proc = subprocess.run(
            ["pdftotext", "-layout", pdf_path, "-"],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            raise SourceUnavailable(f"pdftotext failed: {proc.stderr.strip()}")
        return self.from_text(proc.stdout)


class OcrExtractor:
    """Rasterize at >= 300 DPI, then OCR with a layout-aware page-segmentation
    mode (spec Section 3, step 3b). Requires ``pdftoppm`` (Poppler) and
    ``tesseract`` on PATH. The higher DPI + PSM 6 is exactly what fixed the
    two-column code/rate separation on the reference document.

    This adapter is deliberately thin and honest: if the binaries are missing
    it raises :class:`SourceUnavailable` rather than degrading silently.
    """

    def __init__(self, dpi: int = 300, psm: int = 6) -> None:
        if dpi < 300:
            raise ValueError("OCR DPI must be >= 300 for reliable WD reading")
        self.dpi = dpi
        self.psm = psm

    def _require_binaries(self) -> None:
        missing = [b for b in ("pdftoppm", "tesseract") if not shutil.which(b)]
        if missing:
            raise SourceUnavailable(
                f"OCR requires {', '.join(missing)} on PATH (install Poppler + "
                "Tesseract). Refusing to guess rates from an unreadable source."
            )

    def extract(self, pdf_path: str) -> Document:  # pragma: no cover - needs binaries
        import glob
        import os
        import tempfile

        self._require_binaries()
        doc = Document(source_type=SourceType.OCR, ocr_dpi=self.dpi)
        with tempfile.TemporaryDirectory() as tmp:
            prefix = os.path.join(tmp, "page")
            rp = subprocess.run(
                ["pdftoppm", "-r", str(self.dpi), "-png", pdf_path, prefix],
                capture_output=True, text=True, check=False,
            )
            if rp.returncode != 0:
                raise SourceUnavailable(f"pdftoppm failed: {rp.stderr.strip()}")
            pages = sorted(glob.glob(prefix + "*.png"))
            if not pages:
                raise SourceUnavailable("rasterization produced no pages")
            for pageno, img in enumerate(pages, 1):
                op = subprocess.run(
                    ["tesseract", img, "-", "--psm", str(self.psm), "--dpi",
                     str(self.dpi), "tsv"],
                    capture_output=True, text=True, check=False,
                )
                if op.returncode != 0:
                    raise SourceUnavailable(f"tesseract failed: {op.stderr.strip()}")
                doc.lines.extend(_parse_tsv(op.stdout, pageno))
        if not any(ln.text.strip() for ln in doc.lines):
            doc.document_flags.append("ocr_empty_output_possible_low_resolution")
        return doc


class SourceUnavailable(RuntimeError):
    """Raised when a required extraction backend is not available. The engine
    surfaces this as a document-level rejection rather than emitting partial
    silent data (spec Section 8)."""


def _parse_tsv(tsv: str, page: int) -> list[SourceLine]:  # pragma: no cover
    """Group Tesseract TSV word rows into lines, carrying bounding boxes."""
    rows = tsv.splitlines()
    if not rows:
        return []
    header = rows[0].split("\t")
    idx = {name: i for i, name in enumerate(header)}
    buckets: dict[tuple, list[dict]] = {}
    for row in rows[1:]:
        cols = row.split("\t")
        if len(cols) < len(header):
            continue

        def g(name: str) -> str:
            return cols[idx[name]] if name in idx else ""

        if g("level") != "5" or not g("text").strip():
            continue
        key = (g("block_num"), g("par_num"), g("line_num"))
        buckets.setdefault(key, []).append(
            {
                "text": g("text"),
                "left": float(g("left") or 0),
                "top": float(g("top") or 0),
                "width": float(g("width") or 0),
                "height": float(g("height") or 0),
                "block": int(g("block_num") or 0),
            }
        )
    lines: list[SourceLine] = []
    for i, (_, words) in enumerate(sorted(buckets.items())):
        text = " ".join(w["text"] for w in words)
        x0 = min(w["left"] for w in words)
        y0 = min(w["top"] for w in words)
        x1 = max(w["left"] + w["width"] for w in words)
        y1 = max(w["top"] + w["height"] for w in words)
        lines.append(
            SourceLine(page=page, index=i, text=text, bbox=[x0, y0, x1, y1],
                       column=words[0]["block"])
        )
    return lines
