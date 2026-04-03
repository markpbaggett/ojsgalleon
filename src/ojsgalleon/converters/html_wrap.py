"""Wraps an HTML fragment in a valid full HTML document to make errors like language and missing title go away.

Common errors currently addressed:
- Missing/uninformative page title (WCAG 2.4.2)
- Missing lang attribute (WCAG 3.1.1)
"""

import os
import re
import unicodedata
from html.parser import HTMLParser

# Typographic characters that Claude may normalise differently from the source.
_TYPO_MAP = str.maketrans({
    "\u201c": '"', "\u201d": '"',   # " "  →  "
    "\u2018": "'", "\u2019": "'",   # ' '  →  '
    "\u00ab": '"', "\u00bb": '"',   # « »  →  "
    "\u2014": "-", "\u2013": "-",   # — –  →  -
    "\u2026": "...",                # …    →  ...
    "\u00a0": " ",                  # NBSP →  space
})


_HEADING_RE = re.compile(r"<h[1-3][^>]*>(.*?)</h[1-3]>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_B64_SRC_RE = re.compile(r'src="data:[^"]*;base64,[^"]*"')
_STYLE_BLOCK_RE = re.compile(r"(<style>)(.*?)(</style>)", re.DOTALL)


# ── Helpers for the AI accessibility pass ────────────────────────────────────

class _TextExtractor(HTMLParser):
    """Collect normalised body text nodes from an HTML document.

    Skips tags whose text content the AI accessibility pass is explicitly
    allowed to create or modify: <script>, <style>, <title>, <caption>,
    <figcaption>.
    """
    _SKIP_TAGS = {"script", "style", "title", "caption", "figcaption"}

    def __init__(self):
        super().__init__()
        self._texts: list[str] = []
        self._skip = False

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP_TAGS:
            self._skip = True

    def handle_endtag(self, tag):
        if tag in self._SKIP_TAGS:
            self._skip = False

    def handle_data(self, data):
        if not self._skip:
            # Collapse all internal whitespace so minor reformatting by the
            # model does not count as a content change.
            normalised = " ".join(data.split())
            if normalised:
                self._texts.append(normalised)


def _extract_texts(html: str) -> list[str]:
    p = _TextExtractor()
    p.feed(html)
    return p._texts


def _body_text(html: str) -> str:
    """Return all visible body text as one normalised string for comparison.

    - Joined into a single string so structural wrapping (new <span>, <abbr>,
      etc.) does not count as a content change.
    - NFKC + typographic normalisation so quote/dash/ellipsis variants that
      the model may canonicalise differently do not trigger false positives.
    """
    raw = " ".join(_extract_texts(html))
    return unicodedata.normalize("NFKC", raw).translate(_TYPO_MAP)


def _strip_heavies(html: str) -> tuple[str, list[str], str]:
    """Replace base64 image data and the <style> block with placeholders.

    Returns (stripped_html, image_originals, style_original).
    """
    images: list[str] = []

    def _img_replacer(m: re.Match) -> str:
        idx = len(images)
        images.append(m.group(0))
        return f'src="data:image/placeholder;base64,IMGPLACEHOLDER{idx}"'

    stripped = _B64_SRC_RE.sub(_img_replacer, html)

    style_original = ""
    m = _STYLE_BLOCK_RE.search(stripped)
    if m:
        style_original = m.group(0)
        stripped = stripped.replace(style_original, "<style>/* STYLEPLACEHOLDER */</style>")

    return stripped, images, style_original


def _restore_heavies(html: str, images: list[str], style_original: str) -> str:
    for idx, original in enumerate(images):
        html = html.replace(f'src="data:image/placeholder;base64,IMGPLACEHOLDER{idx}"', original)
    if style_original:
        html = html.replace("<style>/* STYLEPLACEHOLDER */</style>", style_original)
    return html


def ai_accessibility_pass(html: str) -> tuple[str, str | None]:
    """Post-process *html* with Claude Sonnet to improve WCAG 2.1 AA / ADA Title 2 compliance.

    Only attribute-level and structural changes are permitted — text content is
    never modified. If the model changes any text the result is discarded and
    the original is returned unchanged.

    Returns:
        (html, warning) — warning is None on success, or a message string if
        the pass was skipped, discarded, or failed.
    """
    try:
        import anthropic
    except ImportError:
        return html, "AI accessibility review skipped: 'anthropic' package not installed."

    api_key = os.environ.get("CLAUDE_API")
    if not api_key:
        return html, "AI accessibility review skipped: CLAUDE_API environment variable not set."

    stripped, images, style_original = _strip_heavies(html)
    original_body = _body_text(stripped)

    try:
        client = anthropic.Anthropic(api_key=api_key)
        with client.messages.stream(
            model="claude-sonnet-4-6",
            max_tokens=64000,
            system=(
                "You are an HTML accessibility specialist. Your task is to improve an HTML document "
                "for ADA Title 2 and WCAG 2.1 AA compliance using only structural and attribute-level edits. "
                "Return the complete improved HTML document with no explanation or commentary."
            ),
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Improve the accessibility of this HTML document for ADA Title 2 and "
                        "WCAG 2.1 AA compliance. Follow these rules strictly:\n\n"
                        "NEVER allowed:\n"
                        "- Do not change, add, or remove text inside <p>, <h1>–<h6>, <li>, <td>, "
                        "<th>, <span>, <a>, <em>, <strong>, or any other body element — "
                        "not a single word or character\n\n"
                        "ALLOWED attribute changes:\n"
                        "- Add or modify: aria-label, aria-labelledby, aria-describedby, "
                        "aria-hidden, aria-expanded, aria-controls, role, scope, lang, "
                        "tabindex, headers, for, id\n"
                        "- Fix heading hierarchy by changing heading levels (h1–h6)\n"
                        "- Change <td> to <th> where a cell is clearly a column or row header\n\n"
                        "ALLOWED text additions (these specific elements only):\n"
                        "- Add a <caption> to a table that lacks one — caption text must be "
                        "a concise description derived from visible context, not invented\n"
                        "- Add or update a <figcaption> inside a <figure> that lacks one\n"
                        "- Update the <title> element to be more descriptive if it is generic\n\n"
                        f"{stripped}"
                    ),
                }
            ],
        ) as stream:
            response = stream.get_final_message()
    except Exception as exc:
        return html, f"AI accessibility review failed: {exc}"

    if response.stop_reason == "max_tokens":
        return html, (
            "AI accessibility review was discarded: the response was truncated "
            "(document too large for a single pass). Original document returned."
        )

    improved = response.content[0].text.strip()
    # Strip markdown code fences (Claude sometimes wraps output in ```html ... ```)
    if improved.startswith("```"):
        improved = re.sub(r"^```[^\n]*\n", "", improved)
        improved = re.sub(r"\n```\s*$", "", improved)
        improved = improved.strip()

    # Hard safety guard: discard output if any body text content changed.
    improved_body = _body_text(improved)
    if improved_body != original_body:
        hint = _diff_hint(original_body, improved_body)
        return html, (
            f"AI accessibility review was discarded: the model modified text content{hint}. "
            "Original document returned."
        )

    return _restore_heavies(improved, images, style_original), None


def _diff_hint(before: str, after: str) -> str:
    """Return a short diagnostic string showing the first word-level difference.

    Both strings should already be the output of _body_text() so typographic
    normalisation has been applied before this comparison.
    """
    bw = before.split()
    aw = after.split()
    for i, (b, a) in enumerate(zip(bw, aw)):
        if b != a:
            start = max(0, i - 2)
            snippet = " ".join(bw[start : i + 3])
            return f' (near: "{snippet}" → "{a}")'
    if len(bw) != len(aw):
        return f" (word count changed: {len(bw)} → {len(aw)})"
    return ""


def _extract_title(html_fragment: str, fallback: str) -> str:
    """Return plain text of the first heading, or fallback if none found."""
    match = _HEADING_RE.search(html_fragment)
    if match:
        return _TAG_RE.sub("", match.group(1)).strip()
    return fallback


_CSS = """\
  /* ── Reset ── */
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  /* ── Design tokens ── */
  :root {
    --ink:        #1c2b3a;   /* near-black with a cool undertone            */
    --ink-light:  #4a5568;   /* secondary text                              */
    --accent:     #2c5282;   /* ink navy — headings, links, rule accents    */
    --accent-mid: #4a7fb5;   /* lighter accent for borders                  */
    --rule:       #d6dde6;   /* subtle dividers                             */
    --bg-page:    #dde3ea;   /* cool warm-gray page background              */
    --bg-card:    #ffffff;   /* article card surface                        */
    --bg-tint:    #f0f4f8;   /* abstract / even-row tint                    */
    --warm-accent: #b7860b;  /* warm accent for abstract label, top bar     */
    --font-serif: "Georgia", "Times New Roman", serif;
    --shadow-card: 0 2px 8px rgba(0,0,0,.08), 0 8px 32px rgba(0,0,0,.06);
  }

  /* ── Page shell ── */
  body {
    font-family: var(--font-serif);
    font-size: 1.0625rem;    /* ≈ 17px — comfortable for long-form reading  */
    line-height: 1.8;
    color: var(--ink);
    background-color: var(--bg-page);
    /* Subtle linen-like texture via a repeating gradient */
    background-image: repeating-linear-gradient(
      135deg,
      transparent,
      transparent 2px,
      rgba(255,255,255,.03) 2px,
      rgba(255,255,255,.03) 4px
    );
    min-height: 100vh;
    padding: 3rem 1rem 6rem;
  }

  /* ── Article card ── */
  article {
    max-width: 960px;          /* ~letter-page width at screen resolution    */
    margin-inline: auto;
    background: var(--bg-card);
    border-radius: 3px;
    box-shadow: var(--shadow-card);
    /* Thin gold accent bar across the top */
    border-top: 4px solid var(--warm-accent);
    padding: 3.5rem 5rem 4rem;
  }

  /* ── Headings ── */
  h1, h2, h3, h4 {
    font-family: var(--font-serif);
    color: var(--accent);
    line-height: 1.2;
    font-weight: normal;       /* Georgia italic/bold weight managed per level */
  }

  h1.article-title {
    font-size: 2rem;
    letter-spacing: -0.01em;
    margin-bottom: 1.5rem;
    color: var(--ink);
    border-bottom: 2px solid var(--warm-accent);
    padding-bottom: 0.75rem;
  }

  h2 {
    font-size: 1.3rem;
    font-variant: small-caps;
    letter-spacing: 0.06em;
    margin-top: 2.5rem;
    margin-bottom: 0.5rem;
    padding-bottom: 0.25rem;
    border-bottom: 1px solid var(--rule);
  }

  h3 {
    font-size: 1.05rem;
    font-style: italic;
    margin-top: 1.75rem;
    margin-bottom: 0.35rem;
    color: var(--ink-light);
  }

  h4 {
    font-size: 1rem;
    font-style: italic;
    margin-top: 1.25rem;
    margin-bottom: 0.25rem;
    color: var(--ink-light);
  }

  /* ── Body text ── */
  p {
    margin-top: 1rem;
    hyphens: auto;
    -webkit-hyphens: auto;
  }
  /* Indent continuation paragraphs — classic book convention */
  p + p {
    text-indent: 1.75em;
    margin-top: 0;
  }
  /* But never indent the first paragraph after a heading */
  h1 + p, h2 + p, h3 + p, h4 + p { text-indent: 0; }

  /* ── Abstract ── */
  div.abstract {
    background: var(--bg-tint);
    border: 1px solid var(--rule);
    border-left: 4px solid var(--warm-accent);
    border-radius: 0 3px 3px 0;
    padding: 1.25rem 1.5rem;
    margin: 2rem 0;
    font-size: 0.95rem;
    line-height: 1.7;
  }
  div.abstract p { text-indent: 0; margin-top: 0.5rem; }
  div.abstract p:first-child { margin-top: 0; }
  div.abstract::before {
    content: "Abstract";
    display: block;
    font-variant: small-caps;
    letter-spacing: 0.1em;
    font-size: 0.78rem;
    color: var(--warm-accent);
    margin-bottom: 0.6rem;
  }

  /* ── Tables ── */
  table {
    width: 100%;
    border-collapse: collapse;
    margin: 2rem 0;
    font-size: 0.9rem;
    line-height: 1.5;
    border: 1px solid var(--rule);
    border-radius: 3px;
    overflow: hidden;   /* clip thead corner radius */
  }
  th, td {
    padding: 0.6rem 1rem;
    text-align: left;
    vertical-align: top;
  }
  thead th {
    background: var(--accent);
    color: #fff;
    font-family: var(--font-serif);
    font-variant: small-caps;
    font-size: 0.82rem;
    letter-spacing: 0.08em;
    font-weight: normal;
    border-bottom: 2px solid var(--accent-mid);
  }
  tbody tr { border-bottom: 1px solid var(--rule); }
  tbody tr:last-child { border-bottom: none; }
  tbody tr:nth-child(even) td { background: var(--bg-tint); }
  tbody tr:hover td { background: #e6edf5; transition: background 0.15s; }

  /* ── Figures & images ── */
  figure {
    margin: 2.5rem 0;
    text-align: center;
  }
  figure img {
    max-width: 100%;
    height: auto;
    border: 1px solid var(--rule);
    border-radius: 3px;
    box-shadow: 0 2px 12px rgba(0,0,0,.10);
  }
  figcaption {
    margin-top: 0.6rem;
    font-size: 0.85rem;
    color: var(--ink-light);
    font-style: italic;
    line-height: 1.5;
  }

  /* ── Inline ── */
  strong { font-weight: bold; color: var(--ink); }
  em     { font-style: italic; }
  a      { color: var(--accent); text-underline-offset: 3px; }
  a:hover { color: var(--warm-accent); }

  /* ── Responsive — collapse padding on small screens ── */
  @media (max-width: 1020px) {
    article { padding: 2.5rem 3rem 3rem; }
  }
  @media (max-width: 640px) {
    article { padding: 1.5rem 1.25rem 2rem; }
    h1.article-title { font-size: 1.5rem; }
  }

  /* ── Print ── */
  @media print {
    body { background: #fff; padding: 0; }
    article {
      box-shadow: none;
      border-top: none;
      padding: 0;
      max-width: 100%;
    }
    a { color: var(--ink); text-decoration: none; }
    tbody tr:hover td { background: none; }
  }
"""


def wrap(
    html_fragment: str,
    title: str = "",
    lang: str = "en",
    style_overrides: dict[str, str] | None = None,
) -> str:
    """Wrap *html_fragment* in a full, accessible HTML5 document.

    Args:
        html_fragment: Inner HTML content (no <html>/<body> wrapper).
        title: Page title. If empty, the first heading in the fragment is used.
               Falls back to "Converted Document".
        lang: BCP 47 language tag for the html[lang] attribute (default "en").
        style_overrides: Optional mapping of CSS variable names to values,
                         e.g. {"--accent": "#c0392b"}. These are injected as a
                         second :root block that overrides the defaults.
    """
    resolved_title = title or _extract_title(html_fragment, "Converted Document")

    override_block = ""
    if style_overrides:
        declarations = "\n".join(
            f"    {var}: {val};" for var, val in style_overrides.items()
        )
        override_block = f"\n  <style>\n  :root {{\n{declarations}\n  }}\n  </style>"

    return f"""\
<!DOCTYPE html>
<html lang="{lang}">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{resolved_title}</title>
  <style>
{_CSS}
  </style>{override_block}
</head>
<body>
<main>
<article>
{html_fragment}
</article>
</main>
</body>
</html>
"""
