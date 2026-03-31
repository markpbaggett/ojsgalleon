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
import tempfile
from html import escape
import fitz
import pdfplumber

from converters.html_wrap import wrap

_HEADING_WIDTH_RATIO = 0.6


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _word_in_bboxes(word_top: float, bboxes: list[tuple]) -> bool:
    """Return True if word_top falls inside any of the given bboxes.

    pdfplumber bboxes are (x0, top, x1, bottom) in page-top coordinates.
    """
    return any(bbox[1] <= word_top <= bbox[3] for bbox in bboxes)


def _table_to_html(rows: list[list]) -> str:
    """Render extracted table rows as an HTML <table>."""
    if not rows:
        return ""
    lines = ["<table>"]
    # Always treat the first row as header (I might regret this later).
    lines.append("  <thead><tr>")
    for cell in rows[0]:
        lines.append(f"    <th>{escape(str(cell or ''))}</th>")
    lines.append("  </tr></thead>")
    lines.append("  <tbody>")
    for row in rows[1:]:
        lines.append("  <tr>")
        for cell in row:
            lines.append(f"    <td>{escape(str(cell or ''))}</td>")
        lines.append("  </tr>")
    lines.append("  </tbody>")
    lines.append("</table>")
    return "\n".join(lines)


def _table_to_jats(rows: list[list]) -> str:
    """Render extracted table rows as a JATS <table-wrap>."""
    if not rows:
        return ""
    lines = ["<table-wrap>", "  <table>"]
    lines.append("    <thead><tr>")
    for cell in rows[0]:
        lines.append(f"      <th>{escape(str(cell or ''))}</th>")
    lines.append("    </tr></thead>")
    lines.append("    <tbody>")
    for row in rows[1:]:
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
            # ----------------------------------------------------------------
            words = plumber_page.extract_words(extra_attrs=["size"])
            if words:
                sizes = sorted(float(w.get("size", 12) or 12) for w in words)
                median_size = sizes[len(sizes) // 2]
                page_width = float(plumber_page.width)

                lines: dict[float, list[dict]] = {}
                for w in words:
                    if _word_in_bboxes(float(w["top"]), table_bboxes):
                        continue
                    key = round(float(w["top"]), 0)
                    lines.setdefault(key, []).append(w)

                for y_key, line_words in sorted(lines.items()):
                    line_words.sort(key=lambda w: w["x0"])
                    text = " ".join(w["text"] for w in line_words).strip()
                    if not text:
                        continue
                    avg_size = sum(
                        float(w.get("size", 12) or 12) for w in line_words
                    ) / len(line_words)
                    line_width = line_words[-1]["x1"] - line_words[0]["x0"]
                    width_ratio = line_width / page_width

                    if avg_size > median_size * 1.15 and width_ratio < _HEADING_WIDTH_RATIO:
                        tag = "h2" if avg_size > median_size * 1.4 else "h3"
                    else:
                        tag = "p"
                    page_elements.append({"type": tag, "text": text, "y": y_key})
            else:
                # Fallback: plain text extraction for image-only pages.
                raw = plumber_page.extract_text() or ""
                for i, line in enumerate(raw.splitlines()):
                    line = line.strip()
                    if line:
                        page_elements.append({"type": "p", "text": line, "y": float(i)})

            page_elements.sort(key=lambda e: e["y"])
            all_elements.extend(page_elements)

    fitz_doc.close()

    # Merge consecutive body-text lines into single paragraph blocks.
    merged: list[dict] = []
    for el in all_elements:
        if el["type"] == "p" and merged and merged[-1]["type"] == "p":
            merged[-1]["text"] += " " + el["text"]
        else:
            merged.append(el)

    return merged


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
            parts.append(f"<{tag}>{escape(el['text'])}</{tag}>")
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
