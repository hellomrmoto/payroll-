"""CLI: extract an SCA wage determination to deterministic JSON.

Usage:
    python -m sca_extraction WD.pdf [--force-ocr] [--pretty]
    python -m sca_extraction --text page1.txt page2.txt   # score raw text pages

Exit codes:
    0  extraction succeeded, nothing needs confirmation
    2  extraction succeeded but items require human confirmation
    3  ingestion/extraction failed (see stderr)
"""

from __future__ import annotations

import argparse
import json
import sys

from .extractor import extract_from_pages


def _emit(result, pretty: bool) -> int:
    payload = result.to_dict()
    indent = 2 if pretty else None
    print(json.dumps(payload, indent=indent, sort_keys=True))
    n = len(result.confirmation_queue)
    if n:
        print(f"[{n} field(s) require confirmation]", file=sys.stderr)
        return 2
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sca_extraction", description=__doc__)
    parser.add_argument("inputs", nargs="+", help="PDF path, or text files with --text")
    parser.add_argument("--text", action="store_true", help="treat inputs as raw text pages")
    parser.add_argument("--force-ocr", action="store_true", help="force OCR path for a PDF")
    parser.add_argument("--pretty", action="store_true", help="pretty-print JSON")
    args = parser.parse_args(argv)

    if args.text:
        pages = []
        for i, path in enumerate(args.inputs, start=1):
            with open(path, "r", encoding="utf-8") as fh:
                pages.append((i, fh.read()))
        result = extract_from_pages(pages, source_file=",".join(args.inputs), is_ocr=True)
        return _emit(result, args.pretty)

    # PDF path (single file).
    from .ingest import IngestError

    if len(args.inputs) != 1:
        parser.error("PDF mode takes exactly one input file")
    try:
        from . import extract_wage_determination

        result = extract_wage_determination(args.inputs[0], force_ocr=args.force_ocr)
    except IngestError as exc:
        print(f"ingest error: {exc}", file=sys.stderr)
        return 3
    return _emit(result, args.pretty)


if __name__ == "__main__":
    raise SystemExit(main())
