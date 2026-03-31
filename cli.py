"""Adds a command-line interface for OJS Galleon conversions.

Usage:
    uv run python cli.py <file> [--format html|jats] [--output <outfile>]
"""

import argparse
import sys
from pathlib import Path

from converters.docx import docx_to_html, docx_to_jats
from converters.pdf import pdf_to_html, pdf_to_jats

SUPPORTED = {".docx", ".pdf"}


def main():
    parser = argparse.ArgumentParser(
        description="Convert a DOCX or PDF to HTML or JATS XML."
    )
    parser.add_argument("file", help="Path to the input .docx or .pdf file")
    parser.add_argument(
        "--format", choices=["html", "jats"], default="html",
        help="Output format (default: html)"
    )
    parser.add_argument(
        "--output", "-o", default=None,
        help="Write output to this file instead of stdout"
    )
    parser.add_argument(
        "--lang", default="en",
        help="BCP 47 language tag for html[lang] (default: en)"
    )
    args = parser.parse_args()

    src = Path(args.file)
    if not src.exists():
        sys.exit(f"Error: file not found: {src}")

    ext = src.suffix.lower()
    if ext not in SUPPORTED:
        sys.exit(f"Error: unsupported file type '{ext}'. Accepted: {', '.join(sorted(SUPPORTED))}")

    file_bytes = src.read_bytes()
    warnings = []

    if ext == ".docx":
        if args.format == "html":
            result, warnings = docx_to_html(file_bytes, lang=args.lang)
        else:
            result = docx_to_jats(file_bytes)
    else:  # .pdf
        if args.format == "html":
            result = pdf_to_html(file_bytes, lang=args.lang)
        else:
            result = pdf_to_jats(file_bytes)

    if warnings:
        for w in warnings:
            print(f"[warn] {w}", file=sys.stderr)

    if args.output:
        Path(args.output).write_text(result, encoding="utf-8")
        print(f"Written to {args.output}")
    else:
        print(result)


if __name__ == "__main__":
    main()
