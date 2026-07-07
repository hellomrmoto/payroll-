"""Command-line entry point for the WD Reader.

    python -m wd_reader read <file.pdf> [--county Tulare --state CA]
    python -m wd_reader demo            # run the built-in reference example

``read`` requires Poppler + Tesseract for image-only PDFs; if they are missing
the engine rejects the document rather than guessing (spec Section 8).
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from .conflict import ContractMetadata
from .pipeline import DocumentRejected, ReadResult, read_document, read_pdf
from .schema import SourceType
from .sources import TextLayerExtractor


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="wd_reader", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_read = sub.add_parser("read", help="read a wage-determination PDF")
    p_read.add_argument("pdf", help="path to the WD PDF")
    p_read.add_argument("--state", help="contract place-of-performance state")
    p_read.add_argument("--county", help="contract place-of-performance county")
    p_read.add_argument("--dpi", type=int, default=300, help="OCR DPI (>=300)")

    sub.add_parser("demo", help="run the built-in reference example")

    args = parser.parse_args(argv)

    if args.cmd == "demo":
        return _demo()

    contract = None
    if args.state or args.county:
        contract = ContractMetadata(pop_state=args.state, pop_county=args.county)
    try:
        result = read_pdf(args.pdf, contract=contract, ocr_dpi=args.dpi)
    except DocumentRejected as e:
        print(f"DOCUMENT REJECTED: {e}", file=sys.stderr)
        return 2
    _emit(result)
    return 0


def _demo() -> int:
    from .fixtures_demo import WD_2015_5657_OCR

    doc = TextLayerExtractor.from_text(WD_2015_5657_OCR)
    doc.source_type = SourceType.OCR
    doc.ocr_dpi = 300
    result = read_document(
        doc, contract=ContractMetadata(pop_state="CA", pop_county="Tulare")
    )
    print("# Reference document WD 2015-5657 (hostile OCR, no SAM.gov)\n")
    _emit(result)
    return 0


def _emit(result: ReadResult) -> None:
    print(result.wage_determination.to_json())
    print("\n# Confirmation queue ({} item(s))".format(len(result.confirmation_queue)))
    for it in result.confirmation_queue:
        print(
            json.dumps(
                {
                    "field": it.field_path,
                    "value": it.value,
                    "confidence": round(it.confidence, 3),
                    "disposition": it.disposition,
                    "candidates": it.candidates,
                    "note": it.note,
                },
                ensure_ascii=False,
            )
        )


if __name__ == "__main__":
    raise SystemExit(main())
