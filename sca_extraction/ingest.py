"""PDF ingestion: classify text-layer vs image-only, extract or OCR page text.

Kept deliberately thin and dependency-optional. The extraction/scoring core does
not import this module, so it is fully testable without any PDF tooling. When a
real PDF comes in we shell out to poppler (``pdftotext`` / ``pdftoppm``) and
``tesseract`` if present; if they are missing we raise a clear, actionable error
rather than silently returning empty text (silent empties are how corrupt files
sneak through — see the skill's failure modes).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Optional

from .schema import IngestMode

# A page with fewer real characters than this is treated as having no usable
# text layer (scanned image, or a near-empty page).
_MIN_TEXTLAYER_CHARS = 20
OCR_DPI = 300  # skill requires >=300 DPI for image-only pages
TESSERACT_PSM = 6  # layout-aware page segmentation (assume a uniform block)


class IngestError(RuntimeError):
    """Raised when a PDF cannot be ingested (missing tooling or unreadable)."""


@dataclass
class IngestedDocument:
    pages: list[tuple[int, str]]  # (1-indexed page number, text)
    mode: IngestMode
    source_file: str

    @property
    def is_ocr(self) -> bool:
        return self.mode is IngestMode.OCR

    def total_chars(self) -> int:
        return sum(len(t.strip()) for _, t in self.pages)


def _have(tool: str) -> bool:
    return shutil.which(tool) is not None


def _pdftotext_pages(pdf_path: str) -> list[str]:
    """Return per-page text via poppler's ``pdftotext -layout``.

    ``-layout`` preserves columnar spacing, which the row parser relies on to
    separate a code/title from its rate.
    """
    out = subprocess.run(
        ["pdftotext", "-layout", pdf_path, "-"],
        capture_output=True,
        text=True,
        check=True,
    )
    # pdftotext separates pages with a form-feed (\f).
    raw = out.stdout.split("\f")
    # Trailing split artifact.
    if raw and raw[-1].strip() == "":
        raw = raw[:-1]
    return raw


def _looks_image_only(pages_text: list[str]) -> bool:
    real = sum(len(t.strip()) for t in pages_text)
    return real < _MIN_TEXTLAYER_CHARS


def _ocr_pages(pdf_path: str, dpi: int = OCR_DPI, psm: int = TESSERACT_PSM) -> list[str]:
    if not (_have("pdftoppm") and _have("tesseract")):
        raise IngestError(
            "Image-only PDF requires 'pdftoppm' (poppler) and 'tesseract' for OCR, "
            "which are not installed. Install poppler-utils and tesseract-ocr."
        )
    texts: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        prefix = os.path.join(tmp, "page")
        subprocess.run(
            ["pdftoppm", "-r", str(dpi), "-png", pdf_path, prefix],
            capture_output=True,
            check=True,
        )
        images = sorted(f for f in os.listdir(tmp) if f.endswith(".png"))
        for img in images:
            res = subprocess.run(
                ["tesseract", os.path.join(tmp, img), "-", "--psm", str(psm)],
                capture_output=True,
                text=True,
                check=True,
            )
            texts.append(res.stdout)
    return texts


def ingest_pdf(pdf_path: str, force_ocr: bool = False) -> IngestedDocument:
    """Ingest a PDF, choosing text-layer vs OCR automatically.

    ``force_ocr=True`` skips the text-layer probe (useful when a text layer
    exists but is known-garbage). Raises :class:`IngestError` on missing tooling
    or an unreadable/empty result — never returns silent empty text.
    """
    if not os.path.exists(pdf_path):
        raise IngestError(f"file not found: {pdf_path}")
    if not _have("pdftotext"):
        raise IngestError(
            "'pdftotext' (poppler-utils) is required to ingest PDFs and is not installed."
        )

    if force_ocr:
        text_pages = None
        image_only = True
    else:
        try:
            text_pages = _pdftotext_pages(pdf_path)
        except subprocess.CalledProcessError as exc:  # pragma: no cover - env dependent
            raise IngestError(f"pdftotext failed: {exc.stderr}") from exc
        image_only = _looks_image_only(text_pages)

    if image_only:
        ocr_pages = _ocr_pages(pdf_path)
        pages = [(i + 1, t) for i, t in enumerate(ocr_pages)]
        doc = IngestedDocument(pages=pages, mode=IngestMode.OCR, source_file=pdf_path)
    else:
        assert text_pages is not None
        pages = [(i + 1, t) for i, t in enumerate(text_pages)]
        doc = IngestedDocument(pages=pages, mode=IngestMode.TEXT_LAYER, source_file=pdf_path)

    if doc.total_chars() < _MIN_TEXTLAYER_CHARS:
        raise IngestError(
            "No usable text recovered from the document (text layer empty and OCR "
            "produced nothing). Reject and request a re-upload rather than emitting "
            "partial silent data."
        )
    return doc
