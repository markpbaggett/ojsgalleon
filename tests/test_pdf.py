"""Tests for PDF extraction: column detection, reading order, and HTML output.

Each test targets a specific behaviour that has broken at least once.  Run with:
    uv run pytest tests/ -v
"""

from pathlib import Path

import pdfplumber
import pytest

FIXTURES = Path(__file__).parent.parent / "fixtures"
OWINGS  = FIXTURES / "Owings+et+al+2022.pdf"
SCHACK  = FIXTURES / "01_Schack.pdf"
DAVEY   = FIXTURES / "Hermeneutics+of+Prayer_NDavey.pdf"
DOCX    = FIXTURES / "New Web Archiving Collections Guidelines.docx"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _page_words(pdf_path: Path, page_num: int = 0) -> tuple[list[dict], float, float]:
    """Return (words, page_width, page_height) for a page."""
    with pdfplumber.open(str(pdf_path)) as pdf:
        page = pdf.pages[page_num]
        words = page.extract_words(extra_attrs=["size", "bottom"])
        return words, float(page.width), float(page.height)


# ---------------------------------------------------------------------------
# Unit tests: _detect_column_split
# ---------------------------------------------------------------------------

class TestDetectColumnSplit:
    from ojsgalleon.converters.pdf import _detect_column_split  # noqa: E402

    def test_owings_page1_is_single_column(self):
        from ojsgalleon.converters.pdf import _detect_column_split
        words, page_width, _ = _page_words(OWINGS, page_num=0)
        assert _detect_column_split(words, page_width) is None

    def test_owings_page2_detects_gutter(self):
        from ojsgalleon.converters.pdf import _detect_column_split
        words, page_width, _ = _page_words(OWINGS, page_num=1)
        split_x = _detect_column_split(words, page_width)
        assert split_x is not None
        # Gutter should be near the horizontal centre of the page.
        assert page_width * 0.35 < split_x < page_width * 0.65

    def test_schack_detects_gutter(self):
        from ojsgalleon.converters.pdf import _detect_column_split
        words, page_width, _ = _page_words(SCHACK, page_num=0)
        split_x = _detect_column_split(words, page_width)
        assert split_x is not None

    def test_sparse_page_returns_none(self):
        """Pages with fewer than 30 words should never be split."""
        from ojsgalleon.converters.pdf import _detect_column_split
        fake_words = [{"x0": i * 10, "x1": i * 10 + 8, "top": 100} for i in range(10)]
        assert _detect_column_split(fake_words, 612.0) is None


# ---------------------------------------------------------------------------
# Unit tests: _column_regions
# ---------------------------------------------------------------------------

class TestColumnRegions:

    def test_owings_body_page_is_all_column(self):
        """Owings body pages are true two-column throughout — one 'column' region."""
        from ojsgalleon.converters.pdf import _detect_column_split, _column_regions
        words, page_width, _ = _page_words(OWINGS, page_num=1)
        split_x = _detect_column_split(words, page_width)
        assert split_x is not None
        regions = _column_regions(words, split_x)
        types = [r for r, _ in regions]
        # Body text: may have tiny edge regions but the dominant type is column.
        column_word_count = sum(len(w) for t, w in regions if t == "column")
        full_word_count   = sum(len(w) for t, w in regions if t == "full")
        assert column_word_count > full_word_count * 5, (
            f"Expected mostly column words, got column={column_word_count} full={full_word_count}"
        )

    def test_schack_starts_with_full_width_region(self):
        """Schack title/author block spans the full width → first region is 'full'."""
        from ojsgalleon.converters.pdf import _detect_column_split, _column_regions
        words, page_width, _ = _page_words(SCHACK, page_num=0)
        split_x = _detect_column_split(words, page_width)
        assert split_x is not None
        regions = _column_regions(words, split_x)
        first_type, first_words = regions[0]
        assert first_type == "full", "Expected title block to be classified as full-width"

    def test_schack_body_has_column_region(self):
        """Schack body text is two-column → at least one 'column' region."""
        from ojsgalleon.converters.pdf import _detect_column_split, _column_regions
        words, page_width, _ = _page_words(SCHACK, page_num=0)
        split_x = _detect_column_split(words, page_width)
        regions = _column_regions(words, split_x)
        types = [t for t, _ in regions]
        assert "column" in types

    def test_gap_threshold_separates_full_vs_parallel(self):
        """Lines crossing the gutter with small gap → full; large gap → column."""
        from ojsgalleon.converters.pdf import _column_regions

        split_x = 300.0
        # Two words with a 5 pt gap across the gutter → full-width line.
        full_line = [
            {"x0": 100.0, "x1": 295.0, "top": 100.0},
            {"x0": 300.0, "x1": 500.0, "top": 100.0},
        ]
        # Two words with a 40 pt gap → parallel two-column line.
        col_line = [
            {"x0": 100.0, "x1": 258.0, "top": 200.0},
            {"x0": 320.0, "x1": 500.0, "top": 200.0},
        ]
        regions = _column_regions(full_line + col_line, split_x)
        types_by_y = {round(min(float(w["top"]) for w in wds)): t for t, wds in regions}
        assert types_by_y[100] == "full"
        assert types_by_y[200] == "column"


# ---------------------------------------------------------------------------
# Integration tests: pdf_to_html content
# ---------------------------------------------------------------------------

class TestPdfToHtmlContent:

    def test_schack_title_is_not_split(self):
        """Title words that span the gutter must end up in the same element."""
        from ojsgalleon.converters.pdf import pdf_to_html
        html = pdf_to_html(SCHACK.read_bytes())
        # 'Compassion in practice' and 'Enhancing sustainability' are on the
        # same line in the PDF; they must appear in the same <p>.
        assert "Compassion in practice" in html
        assert "Enhancing sustainability" in html
        # Both phrases must sit inside the same tag (no closing tag between them).
        idx_compassion = html.index("Compassion in practice")
        idx_enhancing  = html.index("Enhancing sustainability")
        between = html[idx_compassion:idx_enhancing]
        assert "</" not in between, (
            "Title was split across elements — full-width line incorrectly classified as column"
        )

    def test_schack_has_introduction_section(self):
        from ojsgalleon.converters.pdf import pdf_to_html
        html = pdf_to_html(SCHACK.read_bytes())
        assert "Introduction" in html

    def test_owings_abstract_present(self):
        from ojsgalleon.converters.pdf import pdf_to_html
        html = pdf_to_html(OWINGS.read_bytes())
        assert "Abstract" in html or "abstract" in html.lower()

    def test_owings_left_then_right_reading_order(self):
        """In Owings, 'Introduction' (left col heading) must appear before
        'Methods' (later section heading)."""
        from ojsgalleon.converters.pdf import pdf_to_html
        html = pdf_to_html(OWINGS.read_bytes())
        assert html.index("Introduction") < html.index("Methods")

    def test_owings_no_running_footer(self):
        """The journal footer that repeats across pages must be suppressed."""
        from ojsgalleon.converters.pdf import pdf_to_html
        html = pdf_to_html(OWINGS.read_bytes())
        # The footer line appears on multiple pages; suppression means it
        # should appear at most once (first-page header is kept).
        count = html.lower().count("journal of forensic entomology")
        assert count <= 2, f"Running footer appeared {count} times — suppression failed"

    def test_davey_single_column_produces_output(self):
        from ojsgalleon.converters.pdf import pdf_to_html
        html = pdf_to_html(DAVEY.read_bytes())
        assert len(html) > 500


# ---------------------------------------------------------------------------
# Accessibility invariants (apply to every HTML output)
# ---------------------------------------------------------------------------

class TestAccessibility:

    @pytest.mark.parametrize("pdf_path", [OWINGS, SCHACK, DAVEY])
    def test_html_lang_attribute(self, pdf_path):
        from ojsgalleon.converters.pdf import pdf_to_html
        html = pdf_to_html(pdf_path.read_bytes())
        assert '<html lang="' in html, "Missing lang attribute on <html> (WCAG 3.1.1)"

    @pytest.mark.parametrize("pdf_path", [OWINGS, SCHACK, DAVEY])
    def test_html_has_title(self, pdf_path):
        from ojsgalleon.converters.pdf import pdf_to_html
        html = pdf_to_html(pdf_path.read_bytes())
        assert "<title>" in html and "</title>" in html, "Missing <title> element (WCAG 2.4.2)"

    @pytest.mark.parametrize("pdf_path", [OWINGS, SCHACK, DAVEY])
    def test_no_empty_th(self, pdf_path):
        from ojsgalleon.converters.pdf import pdf_to_html
        html = pdf_to_html(pdf_path.read_bytes())
        assert "<th></th>" not in html and "<th> </th>" not in html, (
            "Empty <th> found — violates ADA Title II / WCAG 1.3.1"
        )

    def test_docx_html_lang_attribute(self):
        from ojsgalleon.converters.docx import docx_to_html
        html, _ = docx_to_html(DOCX.read_bytes())
        assert '<html lang="' in html

    def test_docx_html_has_title(self):
        from ojsgalleon.converters.docx import docx_to_html
        html, _ = docx_to_html(DOCX.read_bytes())
        assert "<title>" in html and "</title>" in html
