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
</head>
<body>
{html_fragment}
</body>
</html>
"""
