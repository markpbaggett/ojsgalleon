""" Provides a command-line interface for OJS Galleon conversions.

Usage:
    ojsgalleon convert <file> [--format html|jats] [--output <outfile>] [--lang <lang>]
    ojsgalleon serve   [--host HOST] [--port PORT]
"""

import argparse
import sys
from pathlib import Path

from ojsgalleon.converters.docx import docx_to_html, docx_to_jats
from ojsgalleon.converters.pdf import pdf_to_html, pdf_to_jats

SUPPORTED = {".docx", ".pdf"}


def cmd_convert(args: argparse.Namespace) -> None:
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
    else:
        if args.format == "html":
            result, warnings = pdf_to_html(file_bytes, lang=args.lang)
        else:
            result = pdf_to_jats(file_bytes)

    for w in warnings:
        print(f"[warn] {w}", file=sys.stderr)

    if args.output:
        Path(args.output).write_text(result, encoding="utf-8")
        print(f"Written to {args.output}")
    else:
        print(result)


def cmd_serve(args: argparse.Namespace) -> None:
    import uvicorn
    uvicorn.run("ojsgalleon.api:app", host=args.host, port=args.port, reload=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="ojsgalleon",
        description="Convert DOCX and PDF files to HTML or JATS XML.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # ── convert ──────────────────────────────────────────────────────────────
    p_conv = sub.add_parser("convert", help="Convert a document file.")
    p_conv.add_argument("file", help="Path to the input .docx or .pdf file")
    p_conv.add_argument(
        "--format", choices=["html", "jats"], default="html",
        help="Output format (default: html)",
    )
    p_conv.add_argument(
        "--output", "-o", default=None,
        help="Write output to this file instead of stdout",
    )
    p_conv.add_argument(
        "--lang", default="en",
        help="BCP 47 language tag for html[lang] (default: en)",
    )

    p_serve = sub.add_parser("serve", help="Start the conversion API server.")
    p_serve.add_argument("--host", default="0.0.0.0")
    p_serve.add_argument("--port", type=int, default=8000)

    args = parser.parse_args()
    if args.command == "convert":
        cmd_convert(args)
    elif args.command == "serve":
        cmd_serve(args)


if __name__ == "__main__":
    main()
