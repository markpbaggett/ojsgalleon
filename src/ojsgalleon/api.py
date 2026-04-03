"""OJS Galleon — document-to-HTML/JATS conversion API."""

from enum import Enum
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from ojsgalleon.converters.docx import docx_to_html, docx_to_jats
from ojsgalleon.converters.pdf import pdf_to_html, pdf_to_jats
from ojsgalleon.ui import router as ui_router

app = FastAPI(
    title="OJS Galleon",
    description="Convert DOCX and PDF files to structured HTML or JATS XML for Open Journal Systems.",
    version="0.1.0",
)

app.include_router(ui_router)

SUPPORTED_EXTENSIONS = {".docx", ".pdf"}


class OutputFormat(str, Enum):
    html = "html"
    jats = "jats"


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/api/convert")
async def convert_document(
    file: UploadFile = File(...),
    output_format: OutputFormat = Form(OutputFormat.html),
    lang: str = Form("en"),
):
    """Upload a DOCX or PDF and receive converted HTML or JATS XML.

    - **file**: the document to convert
    - **output_format**: `html` (default) or `jats`
    """
    filename = file.filename or ""
    ext = Path(filename).suffix.lower()

    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type '{ext}'. Accepted: {', '.join(sorted(SUPPORTED_EXTENSIONS))}",
        )

    content = await file.read()
    warnings: list[str] = []

    try:
        if ext == ".docx":
            if output_format == OutputFormat.html:
                converted, warnings = docx_to_html(content, lang=lang)
            else:
                converted = docx_to_jats(content)
        else:  # .pdf
            if output_format == OutputFormat.html:
                converted, warnings = pdf_to_html(content, lang=lang)
            else:
                converted = pdf_to_jats(content)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return JSONResponse(
        {
            "filename": filename,
            "format": output_format,
            "content": converted,
            "warnings": warnings,
        }
    )


def serve():
    """Entry point for `ojsgalleon serve`."""
    import uvicorn
    uvicorn.run("ojsgalleon.api:app", host="0.0.0.0", port=8000, reload=True)
