import base64
from html import escape
from pathlib import Path

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import HTMLResponse

router = APIRouter()

SUPPORTED = {".docx", ".pdf"}

_PAGE = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>OJS Galleon</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script src="https://unpkg.com/htmx.org@2.0.4/dist/htmx.min.js"></script>
  <style>
    /* HTMX loading indicator */
    .htmx-indicator          { display: none; }
    .htmx-request            .htmx-indicator { display: flex; }
    .htmx-request.htmx-indicator             { display: flex; }

    /* Drop zone active state driven by JS class */
    .drop-active {
      border-color: rgb(99 102 241);   /* indigo-500 */
      background-color: rgb(238 242 255); /* indigo-50 */
    }
  </style>
</head>
<body class="min-h-screen bg-slate-100">

  <!-- ── Header ──────────────────────────────────────────────────────────── -->
  <header class="bg-white border-b border-slate-200 px-6 py-4 flex items-center gap-4">
    <span class="text-2xl">⛵</span>
    <div>
      <h1 class="text-lg font-semibold text-slate-800 leading-tight">OJS Galleon</h1>
      <p class="text-xs text-slate-700">Convert DOCX &amp; PDF → HTML / JATS XML for Open Journal Systems Galleys!</p>
    </div>
  </header>

  <main class="max-w-5xl mx-auto px-4 py-8 space-y-6">

    <!-- ── Upload card ─────────────────────────────────────────────────── -->
    <div class="bg-white rounded-xl shadow-sm border border-slate-200 p-6">
      <form id="convert-form"
            hx-post="/ui/convert"
            hx-target="#preview-pane"
            hx-swap="innerHTML"
            hx-encoding="multipart/form-data"
            hx-indicator="#spinner">

        <!-- Drop zone (also acts as click-to-browse via <label>) -->
        <label id="drop-zone" for="file-input"
               class="flex flex-col items-center justify-center gap-3
                      border-2 border-dashed border-slate-300 rounded-xl
                      p-12 cursor-pointer transition-colors
                      hover:border-indigo-400 hover:bg-indigo-50">

          <input type="file" id="file-input" name="file"
                 accept=".pdf,.docx" class="sr-only">

          <!-- Upload icon -->
          <svg class="w-12 h-12 text-slate-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"
                  d="M9 13h6m-3-3v6m5 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586
                     a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19
                     a2 2 0 01-2 2z"/>
          </svg>

          <div class="text-center">
            <p id="file-label" class="text-slate-600 font-medium">
              Drop a PDF or DOCX here
            </p>
            <p class="text-slate-700 text-sm mt-1">or click to browse</p>
          </div>
        </label>

        <!-- ── Options row ──────────────────────────────────────────────── -->
        <div class="flex flex-wrap items-end gap-4 mt-5">

          <div>
            <label for="output-select" class="block text-xs font-medium text-slate-500 uppercase tracking-wide mb-1">
              Output format
            </label>
            <select id="output-select" name="output_format"
                    class="rounded-lg border border-slate-300 bg-white px-3 py-2
                           text-sm text-slate-700 shadow-sm focus:outline-none
                           focus:ring-2 focus:ring-indigo-500">
              <option value="html">HTML</option>
              <option value="jats">JATS XML</option>
            </select>
          </div>

          <div>
            <label for="lang-select" class="block text-xs font-medium text-slate-500 uppercase tracking-wide mb-1">
              Language
            </label>
            <input id="lang-select" name="lang" value="en" maxlength="10"
                   class="w-24 rounded-lg border border-slate-300 bg-white px-3 py-2
                          text-sm text-slate-700 shadow-sm focus:outline-none
                          focus:ring-2 focus:ring-indigo-500">
          </div>

          <div class="flex items-center gap-2">
            <input type="checkbox" id="gen-alt-text" name="generate_alt_text"
                   value="true"
                   class="h-4 w-4 rounded border-slate-300 text-indigo-600
                          focus:ring-indigo-500">
            <label for="gen-alt-text" class="text-sm text-slate-700 whitespace-nowrap">
              AI alt text <span class="text-slate-800 text-xs">(PDF only)</span>
            </label>
          </div>

          <button type="submit" id="convert-btn"
                  class="ml-auto rounded-lg bg-indigo-600 hover:bg-indigo-700
                         text-white font-medium text-sm px-5 py-2 shadow-sm
                         transition-colors focus:outline-none focus:ring-2
                         focus:ring-indigo-500 focus:ring-offset-2">
            Convert
          </button>
        </div>

        <!-- ── Style panel ───────────────────────────────────────────────── -->
        <details class="mt-4 rounded-lg border border-slate-200 bg-slate-50">
          <summary class="cursor-pointer select-none px-4 py-2.5 text-xs font-medium
                          text-slate-500 uppercase tracking-wide list-none
                          flex items-center justify-between
                          [&::-webkit-details-marker]:hidden">
            <span>Galley styles</span>
            <svg class="w-4 h-4 transition-transform details-chevron" fill="none"
                 stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                    d="M19 9l-7 7-7-7"/>
            </svg>
          </summary>
          <div class="px-4 pb-4 pt-2 grid grid-cols-2 sm:grid-cols-3 gap-x-6 gap-y-3">

            <div>
              <label for="cv-text-primary" class="block text-xs text-slate-500 mb-1">Text</label>
              <div class="flex items-center gap-2">
                <input type="color" id="cv-text-primary" name="cv_text_primary" value="#1c2b3a"
                       class="h-8 w-10 rounded border border-slate-300 cursor-pointer p-0.5">
                <span class="text-xs text-slate-400 font-mono">--ink</span>
              </div>
            </div>

            <div>
              <label for="cv-accent-primary" class="block text-xs text-slate-500 mb-1">Accent (headings &amp; links)</label>
              <div class="flex items-center gap-2">
                <input type="color" id="cv-accent-primary" name="cv_accent_primary" value="#2c5282"
                       class="h-8 w-10 rounded border border-slate-300 cursor-pointer p-0.5">
                <span class="text-xs text-slate-400 font-mono">--accent</span>
              </div>
            </div>

            <div>
              <label for="cv-accent-secondary" class="block text-xs text-slate-500 mb-1">Accent (borders)</label>
              <div class="flex items-center gap-2">
                <input type="color" id="cv-accent-secondary" name="cv_accent_secondary" value="#4a7fb5"
                       class="h-8 w-10 rounded border border-slate-300 cursor-pointer p-0.5">
                <span class="text-xs text-slate-400 font-mono">--accent-mid</span>
              </div>
            </div>

            <div>
              <label for="cv-warm-accent" class="block text-xs text-slate-500 mb-1">Warm accent</label>
              <div class="flex items-center gap-2">
                <input type="color" id="cv-warm-accent" name="cv_warm_accent" value="#b7860b"
                       class="h-8 w-10 rounded border border-slate-300 cursor-pointer p-0.5">
                <span class="text-xs text-slate-400 font-mono">--warm-accent</span>
              </div>
            </div>

            <div>
              <label for="cv-background" class="block text-xs text-slate-500 mb-1">Page background</label>
              <div class="flex items-center gap-2">
                <input type="color" id="cv-background" name="cv_background" value="#dde3ea"
                       class="h-8 w-10 rounded border border-slate-300 cursor-pointer p-0.5">
                <span class="text-xs text-slate-400 font-mono">--bg-page</span>
              </div>
            </div>

            <div>
              <label for="cv-surface" class="block text-xs text-slate-500 mb-1">Article surface</label>
              <div class="flex items-center gap-2">
                <input type="color" id="cv-surface" name="cv_surface" value="#ffffff"
                       class="h-8 w-10 rounded border border-slate-300 cursor-pointer p-0.5">
                <span class="text-xs text-slate-400 font-mono">--bg-card</span>
              </div>
            </div>

          </div>
        </details>

        <!-- Spinner (shown during HTMX request) -->
        <div id="spinner" class="htmx-indicator items-center gap-2 text-slate-500 text-sm mt-3">
          <svg class="animate-spin h-4 w-4 text-indigo-500"
               fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10"
                    stroke="currentColor" stroke-width="4"/>
            <path class="opacity-75" fill="currentColor"
                  d="M4 12a8 8 0 018-8v8H4z"/>
          </svg>
          Converting…
        </div>
      </form>
    </div>

    <!-- ── Preview pane (HTMX swap target) ────────────────────────────── -->
    <div id="preview-pane">
      <div class="flex items-center justify-center h-40 rounded-xl border-2
                  border-dashed border-slate-200 text-slate-700 text-sm">
        Converted output will appear here
      </div>
    </div>

  </main>

  <script>
    const dropZone  = document.getElementById('drop-zone');
    const fileInput = document.getElementById('file-input');
    const fileLabel = document.getElementById('file-label');
    const form      = document.getElementById('convert-form');

    // ── Drag-and-drop ────────────────────────────────────────────────────
    ['dragenter', 'dragover'].forEach(evt =>
      dropZone.addEventListener(evt, e => {
        e.preventDefault();
        dropZone.classList.add('drop-active');
      })
    );
    ['dragleave', 'drop'].forEach(evt =>
      dropZone.addEventListener(evt, e => {
        e.preventDefault();
        dropZone.classList.remove('drop-active');
      })
    );
    dropZone.addEventListener('drop', e => {
      const files = e.dataTransfer.files;
      if (files.length) {
        fileInput.files = files;
        fileInput.dispatchEvent(new Event('change'));
      }
    });

    // ── Auto-submit on file select (browse or drop) ───────────────────
    fileInput.addEventListener('change', () => {
      if (!fileInput.files.length) return;
      const name = fileInput.files[0].name;
      fileLabel.textContent = name;
      fileLabel.classList.add('text-indigo-600', 'font-semibold');
      htmx.trigger(form, 'submit');
    });
  </script>
</body>
</html>
"""

def _data_href(content: str, mime: str) -> str:
    """Return a base64 data-URI suitable for an <a download> link."""
    b64 = base64.b64encode(content.encode("utf-8")).decode("ascii")
    return f"data:{mime};charset=utf-8;base64,{b64}"


def _warning_banner(warnings: list[str]) -> str:
    if not warnings:
        return ""
    items = "".join(f"<li>{escape(w)}</li>" for w in warnings)
    return (
        f'<ul class="text-amber-800 text-xs bg-amber-50 border-b border-amber-200 '
        f'px-4 py-2 list-disc list-inside space-y-0.5">{items}</ul>'
    )


@router.get("/", response_class=HTMLResponse)
async def index():
    return HTMLResponse(_PAGE)


@router.post("/ui/convert", response_class=HTMLResponse)
async def ui_convert(
    file: UploadFile = File(...),
    output_format: str = Form("html"),
    lang: str = Form("en"),
    generate_alt_text: str = Form(""),
    cv_text_primary: str = Form("#1c2b3a"),
    cv_accent_primary: str = Form("#2c5282"),
    cv_accent_secondary: str = Form("#4a7fb5"),
    cv_warm_accent: str = Form("#b7860b"),
    cv_background: str = Form("#dde3ea"),
    cv_surface: str = Form("#ffffff"),
):
    filename = file.filename or "document"
    ext = Path(filename).suffix.lower()

    if ext not in SUPPORTED:
        return HTMLResponse(
            f'<div class="rounded-xl border border-red-200 bg-red-50 px-4 py-3 '
            f'text-sm text-red-700">Unsupported file type <code class="font-mono">'
            f'{escape(ext)}</code>. Please upload a <strong>.pdf</strong> or '
            f'<strong>.docx</strong> file.</div>'
        )

    content = await file.read()
    warnings: list[str] = []
    stem = Path(filename).stem
    use_ai_alt = generate_alt_text == "true"

    _DEFAULTS = {
        "--ink": "#1c2b3a",
        "--accent": "#2c5282",
        "--accent-mid": "#4a7fb5",
        "--warm-accent": "#b7860b",
        "--bg-page": "#dde3ea",
        "--bg-card": "#ffffff",
    }
    submitted = {
        "--ink": cv_text_primary,
        "--accent": cv_accent_primary,
        "--accent-mid": cv_accent_secondary,
        "--warm-accent": cv_warm_accent,
        "--bg-page": cv_background,
        "--bg-card": cv_surface,
    }
    style_overrides = {var: val for var, val in submitted.items() if val != _DEFAULTS[var]} or None

    try:
        from ojsgalleon.converters.docx import docx_to_html, docx_to_jats
        from ojsgalleon.converters.pdf import pdf_to_html, pdf_to_jats

        if ext == ".docx":
            if output_format == "html":
                result, warnings = docx_to_html(content, lang=lang, style_overrides=style_overrides)
            else:
                result = docx_to_jats(content)
        else:
            if output_format == "html":
                result = pdf_to_html(content, lang=lang, generate_alt_text=use_ai_alt, style_overrides=style_overrides)
            else:
                result = pdf_to_jats(content, generate_alt_text=use_ai_alt)
    except Exception as exc:
        return HTMLResponse(
            f'<div class="rounded-xl border border-red-200 bg-red-50 px-4 py-3 '
            f'text-sm text-red-700"><strong>Conversion failed:</strong> '
            f'{escape(str(exc))}</div>'
        )

    if output_format == "html":
        out_filename = f"{stem}.html"
        href = _data_href(result, "text/html")
        badge = '<span class="text-xs font-medium px-2 py-0.5 rounded-full bg-blue-100 text-blue-700">HTML</span>'
        dl_label = "Download HTML"
        preview = (
            f'<iframe srcdoc="{escape(result, quote=True)}" '
            f'class="w-full block border-none" style="height: 72vh;"></iframe>'
        )
    else:
        out_filename = f"{stem}.xml"
        href = _data_href(result, "application/xml")
        badge = '<span class="text-xs font-medium px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700">JATS XML</span>'
        dl_label = "Download XML"
        preview = (
            f'<pre class="overflow-auto m-0 p-6 text-xs leading-relaxed font-mono"'
            f' style="height:72vh; background:#0f172a; color:#6ee7b7;">'
            f'{escape(result)}</pre>'
        )

    return HTMLResponse(f"""
<div class="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
  <div class="flex items-center justify-between gap-3 px-4 py-3
              border-b border-slate-200 bg-slate-50">
    <div class="flex items-center gap-2 min-w-0">
      <span class="text-sm font-medium text-slate-700 truncate">{escape(filename)}</span>
      {badge}
    </div>
    <a href="{href}" download="{escape(out_filename)}"
       class="shrink-0 inline-flex items-center gap-1.5 rounded-lg
              bg-slate-700 hover:bg-slate-800 text-white text-sm
              font-medium px-3 py-1.5 transition-colors">
      <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
              d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/>
      </svg>
      {dl_label}
    </a>
  </div>
  {_warning_banner(warnings)}
  {preview}
</div>
""")
