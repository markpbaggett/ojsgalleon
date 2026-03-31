# OJS Galleon

Convert DOCX and PDF files to structured HTML or JATS XML for additional galleys in OJS
[Open Journal Systems (OJS)](https://pkp.sfu.ca/software/ojs/) sites.

## How things work right now (subject to change)

- **DOCX → HTML** via [mammoth](https://github.com/mwilliamson/python-mammoth) with a Word-style map (headings, abstract, emphasis)
- **DOCX → JATS XML** via [pandoc](https://pandoc.org/) (native JATS output)
- **PDF → HTML / JATS XML** via pdfplumber (text + tables) and pymupdf (images)
  - Tables are extracted as `<table>` / JATS `<table-wrap>`
  - Embedded raster images are extracted as base64 data-URIs
  - Font-size heuristics detect headings vs. body text
- Output HTML always includes `<html lang="...">` and a `<title>` (WCAG 2.4.2 / 3.1.1)
- Self-contained output — no external assets required

## Requirements

- Python ≥ 3.14
- [uv](https://docs.astral.sh/uv/) package manager
- [pandoc](https://pandoc.org/installing.html) installed and on `$PATH` (required for DOCX → JATS)

Install pandoc on macOS:
```bash
brew install pandoc
```

## Installation

```bash
git clone <repo-url>
cd ojsgalleon
uv sync
```

## Usage

### Command line

```bash
# DOCX → HTML (printed to stdout)
uv run python cli.py paper.docx

# DOCX → JATS XML, saved to file
uv run python cli.py paper.docx --format jats --output paper.xml

# PDF → HTML, saved to file
uv run python cli.py paper.pdf --format html --output paper.html

# PDF → JATS XML
uv run python cli.py paper.pdf --format jats --output paper.xml

# Non-English document
uv run python cli.py paper.docx --lang fr --output article.html
```

```
usage: cli.py [-h] [--format {html,jats}] [--output OUTPUT] [--lang LANG] file

positional arguments:
  file                  Path to the input .docx or .pdf file

options:
  --format {html,jats}  Output format (default: html)
  --output, -o          Write output to this file instead of stdout
  --lang                BCP 47 language tag for html[lang] (default: en)
```

**WARNING**: Mammoth conversion warnings (e.g. unmapped Word styles) are written to stderr
and do not appear in the output file.

### API server (WIP)

```bash
uv run python main.py
# or
uv run uvicorn main:app --reload
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

Example with `curl`:

```bash
curl -X POST http://localhost:8000/api/convert \
  -F "file=@paper.docx" \
  -F "output_format=html" \
  | jq -r .content > paper.html
```

## Known limitations

- **Scanned / image-only PDFs** — text extraction requires a text layer. OCR (e.g. pytesseract) is not included (yet).
- **Vector graphics in PDFs** — charts and diagrams drawn with PDF path commands are not captured. Only embedded raster images are extracted.
- **PDF table detection** — pdfplumber works well for clearly ruled tables but sometimes miss borderless tables.
- **JATS metadata** — generated JATS lacks article metadata (title, authors, DOI). These fields must be filled in manually or passed via a future metadata endpoint.
- **DOCX images** — mammoth strips images by default. DOCX image extraction will be added later (Sorry!).
