"""Wraps an HTML fragment in a valid full HTML document to make errors like language and missing title go away.

Common errors currently addressed:
- Missing/uninformative page title (WCAG 2.4.2)
- Missing lang attribute (WCAG 3.1.1)
"""

import re


_HEADING_RE = re.compile(r"<h[1-3][^>]*>(.*?)</h[1-3]>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")


def _extract_title(html_fragment: str, fallback: str) -> str:
    """Return plain text of the first heading, or fallback if none found."""
    match = _HEADING_RE.search(html_fragment)
    if match:
        return _TAG_RE.sub("", match.group(1)).strip()
    return fallback


_CSS = """\
  /* ── Reset ── */
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  /* ── Base ── */
  body {
    font-family: "Georgia", "Times New Roman", serif;
    font-size: 1.05rem;
    line-height: 1.75;
    color: #1a1a1a;
    background: #f9f7f4;
    padding: 2rem 1rem 4rem;
  }

  /* ── Article container ── */
  article {
    max-width: 72ch;
    margin-inline: auto;
  }

  /* ── Headings ── */
  h1, h2, h3, h4 {
    font-family: "Georgia", serif;
    line-height: 1.25;
    margin-top: 2.25rem;
    margin-bottom: 0.6rem;
    color: #111;
  }
  h1.article-title { font-size: 1.9rem; margin-top: 1rem; border-bottom: 2px solid #c8b89a; padding-bottom: 0.4rem; }
  h2 { font-size: 1.35rem; border-bottom: 1px solid #ddd; padding-bottom: 0.2rem; }
  h3 { font-size: 1.1rem; font-style: italic; }
  h4 { font-size: 1rem; }

  /* ── Body text ── */
  p { margin-top: 0.9rem; }
  p + p { text-indent: 1.5em; margin-top: 0; }

  /* ── Abstract ── */
  div.abstract {
    background: #f0ece4;
    border-left: 4px solid #c8b89a;
    padding: 1rem 1.25rem;
    margin: 1.5rem 0;
    font-size: 0.97rem;
  }
  div.abstract p { text-indent: 0; }
  div.abstract::before {
    content: "Abstract";
    display: block;
    font-weight: bold;
    font-variant: small-caps;
    letter-spacing: 0.05em;
    margin-bottom: 0.4rem;
    color: #555;
  }

  /* ── Tables ── */
  table {
    width: 100%;
    border-collapse: collapse;
    margin: 1.75rem 0;
    font-size: 0.93rem;
    background: #fff;
    box-shadow: 0 1px 3px rgba(0,0,0,.08);
  }
  th, td {
    padding: 0.55rem 0.85rem;
    text-align: left;
    vertical-align: top;
    border: 1px solid #ddd;
  }
  thead th {
    background: #3a3a3a;
    color: #fff;
    font-weight: 600;
    font-size: 0.88rem;
    letter-spacing: 0.03em;
  }
  tbody tr:nth-child(even) td { background: #f5f3ef; }
  tbody tr:hover td { background: #eae6de; }

  /* ── Figures & images ── */
  figure {
    margin: 2rem auto;
    text-align: center;
  }
  figure img {
    max-width: 100%;
    height: auto;
    border: 1px solid #ddd;
    border-radius: 3px;
    box-shadow: 0 2px 8px rgba(0,0,0,.10);
  }
  figcaption {
    margin-top: 0.5rem;
    font-size: 0.88rem;
    color: #555;
    font-style: italic;
  }

  /* ── Inline ── */
  strong { font-weight: 700; }
  em     { font-style: italic; }
  a      { color: #7a4419; }
  a:hover{ text-decoration: underline; }

  /* ── Print ── */
  @media print {
    body { background: #fff; font-size: 11pt; }
    table { box-shadow: none; }
    figure img { box-shadow: none; }
  }
"""


def wrap(html_fragment: str, title: str = "", lang: str = "en") -> str:
    """Wrap *html_fragment* in a full, accessible HTML5 document.

    Args:
        html_fragment: Inner HTML content (no <html>/<body> wrapper).
        title: Page title. If empty, the first heading in the fragment is used.
               Falls back to "Converted Document".
        lang: BCP 47 language tag for the html[lang] attribute (default "en").
    """
    resolved_title = title or _extract_title(html_fragment, "Converted Document")

    return f"""\
<!DOCTYPE html>
<html lang="{lang}">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{resolved_title}</title>
  <style>
{_CSS}
  </style>
</head>
<body>
<article>
{html_fragment}
</article>
</body>
</html>
"""
