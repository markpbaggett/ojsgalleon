"""Converts a PDF using pdfplumber (text + tables) and pymupdf (images).

Strategy per page
-----------------
1. pdfplumber  → find table bounding boxes and extract structured row data.
2. pymupdf     → iterate blocks in reading order; grab image bytes for image
                 blocks, collect text-block positions for ordering.
3. pdfplumber  → extract individual words with font-size metadata; skip any
                 word whose top-y falls inside a table bounding box.
4. Merge consecutive body-text lines into paragraphs, then sort everything
   by vertical position so the final output follows reading order.

Images are embedded as base64 data-URIs so the HTML/JATS is self-contained.
"""

import base64
import os
import re
import tempfile
from html import escape
import fitz
import pdfplumber

from converters.html_wrap import wrap

_HEADING_WIDTH_RATIO = 0.6

# Fraction of page height considered a header/footer margin zone.
_MARGIN_RATIO = 0.08

# Patterns that strongly suggest a line is a page number.
# Must match the *entire* stripped line (anchored with ^ and $).
# Matches http/https URLs in plain text.
# Stops at whitespace and characters that are almost never part of a URL but
# commonly appear immediately after one in prose (closing brackets, quotes, etc.)
_URL_RE = re.compile(r"https?://[^\s<>\"')\]]+")

# Trailing punctuation that belongs to the sentence, not the URL.
_URL_TRAIL_RE = re.compile(r"[.,;:!?)]+$")


def _linkify(text: str) -> str:
    """Return HTML with bare http/https URLs wrapped in <a> tags.

    Non-URL segments are HTML-escaped normally.  URL segments are used as both
    the href and the visible label, with trailing sentence punctuation stripped
    from the URL (but left in the surrounding text).
    """
    parts: list[str] = []
    last = 0
    for m in _URL_RE.finditer(text):
        url = _URL_TRAIL_RE.sub("", m.group())   # strip trailing punctuation
        url_end = m.start() + len(url)

        parts.append(escape(text[last:m.start()]))          # text before URL
        parts.append(f'<a href="{escape(url)}">{escape(url)}</a>')
        last = url_end

    parts.append(escape(text[last:]))                        # text after last URL
    return "".join(parts)


_PAGE_NUM_RE = re.compile(
    r"^\s*"
    r"("
    r"\d{1,4}"                           # bare integer: 1 … 9999
    r"|[ivxlcdmIVXLCDM]{1,8}"           # roman numerals: i, xiv, XIV
    r"|page\.?\s+\d{1,4}"               # "Page 1" / "Page. 1"
    r"|\d{1,4}\s+of\s+\d{1,4}"         # "1 of 10"
    r"|page\.?\s+\d{1,4}\s+of\s+\d{1,4}"  # "Page 1 of 10"
    r"|[-–—|·•]\s*\d{1,4}\s*[-–—|·•]"  # "- 1 -" / "| 42 |"
    r")"
    r"\s*$",
    re.IGNORECASE,
)


def _is_page_number(text: str, y: float, page_height: float) -> bool:
    """Return True when a line is almost certainly a page number.

    Both conditions must hold:
    1. The line's top-y sits inside the top or bottom margin zone.
    2. The line's text matches a known page-number pattern.

    Requiring both conditions avoids stripping legitimate header/footer content
    such as journal titles or author names that also appear in the margin area.
    """
    in_margin = (
        y < page_height * _MARGIN_RATIO
        or y > page_height * (1 - _MARGIN_RATIO)
    )
    if not in_margin:
        return False
    return bool(_PAGE_NUM_RE.match(text.strip()))


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _word_in_bboxes(word_top: float, bboxes: list[tuple]) -> bool:
    """Return True if word_top falls inside any of the given bboxes.

    pdfplumber bboxes are (x0, top, x1, bottom) in page-top coordinates.
    """
    return any(bbox[1] <= word_top <= bbox[3] for bbox in bboxes)


def _has_header(row: list) -> bool:
    """Return True if any cell in *row* contains non-whitespace text."""
    return any(str(cell or "").strip() for cell in row)


def _table_to_html(rows: list[list]) -> str:
    """Render extracted table rows as an accessible HTML <table>.

    The first row is treated as a header only when it contains at least one
    non-empty cell.  Each <th> gets scope="col" (WCAG 1.3.1).  Empty cells
    in a header row are rendered as <td> instead to avoid empty <th> elements
    that fail ADA Title II / WCAG 2.1 AA audits.
    """
    if not rows:
        return ""

    lines = ["<table>"]

    if _has_header(rows[0]):
        lines.append("  <thead><tr>")
        for cell in rows[0]:
            text = escape(str(cell or "").strip())
            if text:
                lines.append(f'    <th scope="col">{text}</th>')
            else:
                lines.append("    <td></td>")
        lines.append("  </tr></thead>")
        body_rows = rows[1:]
    else:
        body_rows = rows

    lines.append("  <tbody>")
    for row in body_rows:
        lines.append("  <tr>")
        for cell in row:
            lines.append(f"    <td>{escape(str(cell or ''))}</td>")
        lines.append("  </tr>")
    lines.append("  </tbody>")
    lines.append("</table>")
    return "\n".join(lines)


def _table_to_jats(rows: list[list]) -> str:
    """Render extracted table rows as a JATS <table-wrap>.

    Same header-detection logic as _table_to_html: only emit <thead> when the
    first row has content, and skip empty <th> elements.
    """
    if not rows:
        return ""

    lines = ["<table-wrap>", "  <table>"]

    if _has_header(rows[0]):
        lines.append("    <thead><tr>")
        for cell in rows[0]:
            text = escape(str(cell or "").strip())
            if text:
                lines.append(f"      <th>{text}</th>")
            else:
                lines.append("      <td></td>")
        lines.append("    </tr></thead>")
        body_rows = rows[1:]
    else:
        body_rows = rows

    lines.append("    <tbody>")
    for row in body_rows:
        lines.append("    <tr>")
        for cell in row:
            lines.append(f"      <td>{escape(str(cell or ''))}</td>")
        lines.append("    </tr>")
    lines.append("    </tbody>")
    lines.append("  </table>")
    lines.append("</table-wrap>")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Core extraction
# ---------------------------------------------------------------------------

def _extract_elements(pdf_path: str) -> list[dict]:
    """Return page elements sorted by (page, y-position).

    Each element is a dict with at minimum a 'type' key:
      - {"type": "p"|"h2"|"h3", "text": str}
      - {"type": "table", "rows": [[str, ...], ...]}
      - {"type": "image", "b64": str, "ext": str, "alt": str}
    """
    all_elements: list[dict] = []

    fitz_doc = fitz.open(pdf_path)

    with pdfplumber.open(pdf_path) as plumber_pdf:
        for page_num, plumber_page in enumerate(plumber_pdf.pages):
            fitz_page = fitz_doc[page_num]
            page_elements: list[dict] = []

            # ----------------------------------------------------------------
            # 1. Tables via pdfplumber
            # ----------------------------------------------------------------
            table_bboxes: list[tuple] = []
            for tbl in plumber_page.find_tables():
                rows = tbl.extract()
                if rows:
                    bbox = tbl.bbox  # (x0, top, x1, bottom)
                    table_bboxes.append(bbox)
                    page_elements.append({
                        "type": "table",
                        "rows": rows,
                        "y": bbox[1],
                    })

            # ----------------------------------------------------------------
            # 2. Images via pymupdf — blocks are already in reading order
            # ----------------------------------------------------------------
            fitz_blocks = fitz_page.get_text("dict", sort=True)["blocks"]
            image_top_ys: list[float] = []
            for block in fitz_blocks:
                if block["type"] != 1:  # 1 = image block
                    continue
                xref = block.get("xref", 0)
                if not xref:
                    continue
                try:
                    img_data = fitz_doc.extract_image(xref)
                except Exception:
                    continue
                b64 = base64.b64encode(img_data["image"]).decode()
                y = block["bbox"][1]
                image_top_ys.append(y)
                page_elements.append({
                    "type": "image",
                    "b64": b64,
                    "ext": img_data["ext"],
                    "alt": f"Figure on page {page_num + 1}",
                    "y": y,
                })

            # ----------------------------------------------------------------
            # 3. Text via pdfplumber, excluding table regions
            #    Lines are grouped by their top-y coordinate, then paragraph
            #    breaks are inferred from vertical gaps between lines.
            # ----------------------------------------------------------------
            words = plumber_page.extract_words(extra_attrs=["size", "bottom"])
            if words:
                sizes = sorted(float(w.get("size", 12) or 12) for w in words)
                median_size = sizes[len(sizes) // 2]
                page_width = float(plumber_page.width)

                # Group words into lines keyed by rounded top-y.
                raw_lines: dict[float, list[dict]] = {}
                for w in words:
                    if _word_in_bboxes(float(w["top"]), table_bboxes):
                        continue
                    key = round(float(w["top"]), 0)
                    raw_lines.setdefault(key, []).append(w)

                sorted_lines = sorted(raw_lines.items())  # [(y_top, [words])]

                # Bottom y of each line = max word-bottom in that line.
                line_bottoms = {
                    y: max(float(w.get("bottom", y + 12)) for w in wds)
                    for y, wds in sorted_lines
                }

                # Collect inter-line gaps to find the "normal" line spacing.
                gaps = []
                for i in range(1, len(sorted_lines)):
                    prev_y = sorted_lines[i - 1][0]
                    curr_y = sorted_lines[i][0]
                    gap = curr_y - line_bottoms[prev_y]
                    if gap > 0:
                        gaps.append(gap)

                if gaps:
                    gaps.sort()
                    median_gap = gaps[len(gaps) // 2]
                else:
                    median_gap = 2.0
                # A gap larger than this threshold means a new paragraph.
                para_threshold = median_gap * 1.6

                # Walk lines, accumulating body text into paragraphs and
                # flushing whenever a heading or a large gap is encountered.
                para_lines: list[str] = []
                para_y: float = 0.0

                for i, (y_key, line_words) in enumerate(sorted_lines):
                    line_words.sort(key=lambda w: w["x0"])
                    text = " ".join(w["text"] for w in line_words).strip()
                    if not text:
                        continue

                    avg_size = sum(
                        float(w.get("size", 12) or 12) for w in line_words
                    ) / len(line_words)
                    line_width = line_words[-1]["x1"] - line_words[0]["x0"]
                    width_ratio = line_width / page_width
                    if _is_page_number(text, y_key, float(plumber_page.height)):
                        continue

                    is_heading = (
                        avg_size > median_size * 1.15
                        and width_ratio < _HEADING_WIDTH_RATIO
                    )

                    if is_heading:
                        # Flush any pending paragraph before the heading.
                        if para_lines:
                            page_elements.append({
                                "type": "p",
                                "text": " ".join(para_lines),
                                "y": para_y,
                            })
                            para_lines = []
                        tag = "h2" if avg_size > median_size * 1.4 else "h3"
                        page_elements.append({"type": tag, "text": text, "y": y_key})
                    else:
                        # Check whether the gap from the previous line is large
                        # enough to signal a paragraph break.
                        if i > 0 and para_lines:
                            prev_y = sorted_lines[i - 1][0]
                            gap = y_key - line_bottoms[prev_y]
                            if gap > para_threshold:
                                page_elements.append({
                                    "type": "p",
                                    "text": " ".join(para_lines),
                                    "y": para_y,
                                })
                                para_lines = []

                        if not para_lines:
                            para_y = y_key
                        para_lines.append(text)

                # Flush the last paragraph on the page.
                if para_lines:
                    page_elements.append({
                        "type": "p",
                        "text": " ".join(para_lines),
                        "y": para_y,
                    })

            else:
                # Fallback: plain text extraction for image-only pages.
                # Split on blank lines to preserve paragraph breaks.
                raw = plumber_page.extract_text() or ""
                current: list[str] = []
                for i, line in enumerate(raw.splitlines()):
                    stripped = line.strip()
                    if stripped:
                        current.append(stripped)
                    elif current:
                        page_elements.append({
                            "type": "p",
                            "text": " ".join(current),
                            "y": float(i),
                        })
                        current = []
                if current:
                    page_elements.append({
                        "type": "p",
                        "text": " ".join(current),
                        "y": float(len(raw.splitlines())),
                    })

            page_elements.sort(key=lambda e: e["y"])
            all_elements.extend(page_elements)

    fitz_doc.close()
    return all_elements


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def pdf_to_html(file_bytes: bytes, lang: str = "en") -> str:
    """Convert PDF bytes to a full, accessible HTML5 document."""
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name
    try:
        elements = _extract_elements(tmp_path)
    finally:
        os.unlink(tmp_path)

    parts: list[str] = []
    for el in elements:
        if el["type"] in ("h2", "h3", "p"):
            tag = el["type"]
            parts.append(f"<{tag}>{_linkify(el['text'])}</{tag}>")
        elif el["type"] == "table":
            parts.append(_table_to_html(el["rows"]))
        elif el["type"] == "image":
            mime = f"image/{el['ext']}"
            src = f"data:{mime};base64,{el['b64']}"
            alt = escape(el["alt"])
            parts.append(
                f'<figure>\n'
                f'  <img src="{src}" alt="{alt}">\n'
                f'</figure>'
            )

    return wrap("\n".join(parts), lang=lang)


def pdf_to_jats(file_bytes: bytes) -> str:
    """Convert PDF bytes to a JATS XML document."""
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name
    try:
        elements = _extract_elements(tmp_path)
    finally:
        os.unlink(tmp_path)

    body_parts: list[str] = []
    in_sec = False

    for el in elements:
        if el["type"] in ("h2", "h3"):
            if in_sec:
                body_parts.append("    </sec>")
            body_parts.append(f"    <sec>\n      <title>{escape(el['text'])}</title>")
            in_sec = True
        elif el["type"] == "p":
            body_parts.append(f"      <p>{escape(el['text'])}</p>")
        elif el["type"] == "table":
            body_parts.append("      " + _table_to_jats(el["rows"]).replace("\n", "\n      "))
        elif el["type"] == "image":
            mime = f"image/{el['ext']}"
            src = f"data:{mime};base64,{el['b64']}"
            alt = escape(el["alt"])
            body_parts.append(
                f'      <fig>\n'
                f'        <caption><p>{alt}</p></caption>\n'
                f'        <graphic xlink:href="{src}"/>\n'
                f'      </fig>'
            )

    if in_sec:
        body_parts.append("    </sec>")

    body = "\n".join(body_parts)
    return f"""\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE article PUBLIC "-//NLM//DTD JATS (Z39.96) Journal Article Tag Suite (JATS) DTD v1.2 20190208//EN" "JATS-archivearticle1.dtd">
<article xmlns:xlink="http://www.w3.org/1999/xlink" article-type="research-article" xml:lang="en">
  <body>
{body}
  </body>
</article>
"""
