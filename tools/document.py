"""PDF text extraction with PyMuPDF."""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, Union

import fitz  # PyMuPDF

MIN_TEXT_CHARS = 200


class DocumentError(Exception):
    """Raised when a PDF cannot be used for evaluation."""


def _clean(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)  # expands ligatures such as "ﬁ"
    text = text.replace("\x00", "")
    text = text.replace(" ", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_pdf_text(source: Union[bytes, str, Path], filename: str = "document") -> Dict[str, Any]:
    try:
        if isinstance(source, (bytes, bytearray)):
            doc = fitz.open(stream=bytes(source), filetype="pdf")
        else:
            doc = fitz.open(str(source))
    except Exception as exc:
        raise DocumentError(f"{filename}: not a readable PDF ({exc}).") from exc

    try:
        if doc.needs_pass:
            raise DocumentError(f"{filename}: password protected PDF cannot be read.")
        pages = []
        for index, page in enumerate(doc, start=1):
            text = _clean(page.get_text("text"))
            if text:
                pages.append(f"[Page {index}]\n{text}")
        full_text = "\n\n".join(pages)
        if len(full_text) < MIN_TEXT_CHARS:
            raise DocumentError(
                f"{filename}: only {len(full_text)} characters of text found; "
                "the file may be scanned or empty."
            )
        return {"text": full_text, "page_count": doc.page_count, "char_count": len(full_text)}
    finally:
        doc.close()
