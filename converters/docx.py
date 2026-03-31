"""Converts DOCX using mammoth (→ HTML) and pypandoc (→ JATS XML)."""

import os
import re
import tempfile
import mammoth
import pypandoc

from converters.html_wrap import wrap

# Matches any <th> tag (with optional attributes) and its content.
_TH_RE = re.compile(r"<th(\s[^>]*)?>(?P<content>.*?)</th>", re.IGNORECASE | re.DOTALL)


def _fix_table_headers(html: str) -> str:
    """Post-process mammoth HTML to address empty/missing-scope <th> elements.

    - Empty <th> → <td> (empty headers fail ADA Title II / WCAG 1.3.1)
    - Non-empty <th> → adds scope="col" if not already present
    """
    def _replace_th(m: re.Match) -> str:
        attrs = m.group(1) or ""
        content = m.group("content").strip()
        if not content:
            return f"<td></td>"
        if "scope=" not in attrs:
            attrs = ' scope="col"' + attrs
        return f"<th{attrs}>{content}</th>"

    return _TH_RE.sub(_replace_th, html)

# Map common Word paragraph styles to semantic HTML elements.
# Extend this as you encounter journal-specific style names.
_STYLE_MAP = """
p[style-name='Title'] => h1.article-title:fresh
p[style-name='Abstract'] => div.abstract > p:fresh
p[style-name='Heading 1'] => h2:fresh
p[style-name='Heading 2'] => h3:fresh
p[style-name='Heading 3'] => h4:fresh
p[style-name='Body Text'] => p:fresh
r[style-name='Strong'] => strong
r[style-name='Emphasis'] => em
"""


def docx_to_html(file_bytes: bytes, lang: str = "en") -> tuple[str, list[str]]:
    """Convert DOCX bytes to a full, accessible HTML5 document.

    Returns:
        (html_string, list_of_mammoth_warning_messages)
    """
    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name

    try:
        with open(tmp_path, "rb") as fh:
            result = mammoth.convert_to_html(fh, style_map=_STYLE_MAP)
        warnings = [str(m) for m in result.messages]
        fixed = _fix_table_headers(result.value)
        return wrap(fixed, lang=lang), warnings
    finally:
        os.unlink(tmp_path)


def docx_to_jats(file_bytes: bytes) -> str:
    """Convert DOCX bytes to JATS XML via pandoc."""
    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name

    try:
        return pypandoc.convert_file(tmp_path, "jats", format="docx")
    finally:
        os.unlink(tmp_path)
