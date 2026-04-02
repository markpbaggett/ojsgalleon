# OJS Galleon

OJS Galleon is an experimental application that attempts to convert DOCX and PDF files to structured HTML or JATS XML 
in order to provide an HTML galley for [Open Journal Systems (OJS)](https://pkp.sfu.ca/software/ojs/) sites.

While not perfect (this is a hard problem), OJS Galleon attempts to get you 90% there and provide you a nice looking,
professional HTML galley that is ADA Accessible out-of-the-box with some minor needs for copy editing.

## How it works at a high level

OJS Galleon uses two libraries in tandem for PDF extraction: [pdfplumber](https://github.com/jsvine/pdfplumber) (built 
on pdfminer) for text and tables, and [pymupdf](https://github.com/pymupdf/PyMuPDF) (fitz) for images. pdfplumber gives
word-level metadata lik each word's x/y position on the page and its font size which is the foundation for everything 
else. Tables are detected via pdfplumber's find_tables(), which uses line detection to identify ruled grids and extract
cell data.  Images are pulled via pymupdf because it provides reliable cross-reference IDs (xref) needed to extract 
the raw image bytes, which pdfplumber alone doesn't expose cleanly. Both libraries operate on the same PDF simultaneously,
one per concern.

The text pipeline then works in several passes on each page. First, running headers and footers are identified by 
pre-scanning all pages and counting how often each margin line appears. Text that repeats on 40%+ of pages is flagged as
boilerplate and suppressed. Then, for each page, a word-density histogram across the page width is built to detect 
whether a gutter (near-empty vertical strip) exists in the middle third of the page (this is the magic behind how a
two-column layout is identified even if it's not perfect). When a gutter is found, individual lines are further 
classified as either "full-width" (words on both sides with a small gap, like a title or abstract) or "column-confined" 
(words on both sides but with a large inter-column gap, meaning they're two independent parallel lines). Full-width 
regions are read straight across; column regions are read left column first, then right (sorry for lack of international
support). Finally, font-size heuristics promote lines with larger-than-median text into headings, and gap-based 
paragraph detection groups consecutive lines into `<p>` elements by measuring whether the vertical space between lines 
exceeds 1.6× the median line spacing on that page.


| Source | → HTML | → JATS XML |
|--------|--------|------------|
| `.docx` | [mammoth](https://github.com/mwilliamson/python-mammoth) with a Word-style map | [pandoc](https://pandoc.org/) native JATS output |
| `.pdf` | pdfplumber (text + tables) + pymupdf (images) | same |

**PDF extraction features:**
- Two-column layout detection — left column is always read before right
- Tables extracted as `<table>` / JATS `<table-wrap>` with accessible headers (`scope="col"`)
- Embedded raster images extracted and embedded as base64 data-URIs
- Font-size heuristics distinguish headings from body text
- Running headers/footers stripped by repetition detection (footnotes preserved)
- Page numbers stripped
- Bare URLs linkified as `<a>` tags

**HTML output is always valid and accessible:**
- `<html lang="...">` and `<title>` on every document (WCAG 2.4.2 / 3.1.1)
- Empty `<th>` elements converted to `<td>` (ADA Title II / WCAG 1.3.1)
- Self-contained — no external assets, images embedded as data-URIs

## Requirements

- Python ≥ 3.11
- [pandoc](https://pandoc.org/installing.html) on `$PATH` (required for DOCX → JATS only)

```bash
brew install pandoc   # macOS
```

## Installation

### From PyPI

```bash
pip install ojsgalleon
# or
uv add ojsgalleon
```

### From source

```bash
git clone <repo-url>
cd ojsgalleon
uv sync
```

## Usage

### Command line

```bash
# PDF → HTML, saved to file
ojsgalleon convert paper.pdf --output paper.html

# DOCX → JATS XML
ojsgalleon convert paper.docx --format jats --output paper.xml

# Non-English document
ojsgalleon convert paper.pdf --lang fr --output article.html

# Start the API server
ojsgalleon serve
ojsgalleon serve --host 127.0.0.1 --port 9000
```

With `uv run` from a source checkout:
```bash
uv run ojsgalleon convert paper.pdf --output paper.html
```

```
usage: ojsgalleon <command> [options]

commands:
  convert   Convert a .docx or .pdf file
  serve     Start the HTTP API server

convert options:
  file                  Path to the input .docx or .pdf
  --format {html,jats}  Output format (default: html)
  --output, -o          Write to file instead of stdout
  --lang                BCP 47 language tag for html[lang] (default: en)

serve options:
  --host HOST           Bind host (default: 0.0.0.0)
  --port PORT           Bind port (default: 8000)
```

Mammoth warnings (e.g. unmapped Word styles) are written to stderr and do not appear in the output file.

### As a library

```python
from ojsgalleon import pdf_to_html, pdf_to_jats, docx_to_html, docx_to_jats

html, warnings = docx_to_html(Path("paper.docx").read_bytes())
html            = pdf_to_html(Path("paper.pdf").read_bytes())
jats            = pdf_to_jats(Path("paper.pdf").read_bytes())
jats            = docx_to_jats(Path("paper.docx").read_bytes())
```

### API server

```bash
ojsgalleon serve
```

Interactive docs: http://localhost:8000/docs

#### `POST /api/convert`

Accepts `multipart/form-data`:

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `file` | file | yes | — | `.docx` or `.pdf` to convert |
| `output_format` | string | no | `html` | `html` or `jats` |
| `lang` | string | no | `en` | BCP 47 language tag |

Response:

```json
{
  "filename": "paper.docx",
  "format": "html",
  "content": "<!DOCTYPE html>...",
  "warnings": []
}
```

```bash
curl -X POST http://localhost:8000/api/convert \
  -F "file=@paper.pdf" \
  -F "output_format=html" \
  | jq -r .content > paper.html
```

## Project structure

```
src/ojsgalleon/
├── __init__.py          # public API
├── api.py               # FastAPI app
├── cli.py               # CLI (subcommands: convert, serve)
└── converters/
    ├── docx.py          # DOCX → HTML (mammoth) / JATS (pandoc)
    ├── pdf.py           # PDF → HTML or JATS (pdfplumber + pymupdf)
    └── html_wrap.py     # Wraps fragments in a valid, styled HTML5 document
```

## Tuning PDF extraction

Two constants in `src/ojsgalleon/converters/pdf.py` control running header/footer suppression:

| Constant | Default | Effect |
|---|---|---|
| `_MARGIN_RATIO` | `0.08` | Size of the top/bottom margin zone (8% of page height) |
| `_RUNNING_TEXT_THRESHOLD` | `0.40` | Fraction of pages a line must appear on to be suppressed |

Increase `_MARGIN_RATIO` if a journal places running headers unusually deep into the text area. Lower `_RUNNING_TEXT_THRESHOLD` if headers only appear on roughly half the pages.

## Known limitations

- **Scanned / image-only PDFs** — text extraction requires a text layer; OCR is not included.
- **Vector graphics in PDFs** — charts drawn with PDF path commands are not captured; only embedded raster images are extracted.
- **Bold-only headings in PDFs** — section headings marked with bold weight but the same font size as body text cannot be detected by the font-size heuristic.
- **Borderless tables in PDFs** — pdfplumber's table detection works well for ruled tables but may miss borderless ones.
- **JATS metadata** — generated JATS lacks article metadata (title, authors, DOI); these must be filled in manually.
- **DOCX images** — mammoth does not extract embedded images from DOCX files.
