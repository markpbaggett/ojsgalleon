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
