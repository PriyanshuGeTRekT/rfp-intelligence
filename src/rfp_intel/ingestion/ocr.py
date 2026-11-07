"""OCR for PDF pages that are images with no text layer (scans, faxes, copier output).

RapidOCR (ONNX models bundled with the package, CPU only, about 1.3 s per page at 200 DPI)
reads the rendered page; each recognised line comes back with its box, converted from image
pixels to PDF points so the parser treats it like a native text line: running headers are
removed, rows are rebuilt, headings and sections found. Lines below a confidence threshold are
dropped rather than indexed as noise. `RFP_OCR=false` turns it off; without the package,
pages are reported as needing OCR, as before.
"""

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import pymupdf

from rfp_intel.logs import get_logger

log = get_logger(__name__)
DPI = 200
MIN_CONFIDENCE = 0.6


@dataclass(frozen=True)
class OcrLine:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    confidence: float


@lru_cache(maxsize=1)
def _engine() -> Any:
    from rfp_intel.config import get_settings

    if not get_settings().ocr:
        return None
    try:
        from rapidocr_onnxruntime import RapidOCR  # type: ignore[import-untyped]
    except ImportError:
        log.warning("ocr_unavailable", hint="install rapidocr-onnxruntime to read scanned pages")
        return None
    return RapidOCR()


def ocr_available() -> bool:
    return _engine() is not None


def ocr_page(page: pymupdf.Page) -> list[OcrLine]:
    """Recognised lines of one page, in PDF points, top to bottom."""
    engine = _engine()
    if engine is None:
        return []
    png: bytes = page.get_pixmap(dpi=DPI).tobytes("png")  # type: ignore[no-untyped-call]
    result, _ = engine(png)
    scale = 72.0 / DPI
    lines: list[OcrLine] = []
    for box, text, confidence in result or []:
        if float(confidence) < MIN_CONFIDENCE or not str(text).strip():
            continue
        xs = [float(p[0]) for p in box]
        ys = [float(p[1]) for p in box]
        lines.append(
            OcrLine(
                text=str(text).strip(),
                x0=min(xs) * scale,
                y0=min(ys) * scale,
                x1=max(xs) * scale,
                y1=max(ys) * scale,
                confidence=float(confidence),
            )
        )
    return sorted(lines, key=lambda ln: (round(ln.y0), ln.x0))
