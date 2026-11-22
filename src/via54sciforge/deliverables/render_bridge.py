"""Windows Office COM + PyMuPDF visual rendering bridge with honest status reporting."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List

import pymupdf as fitz


def _rasterize_pdf(pdf_path: Path, out_dir: Path, dpi: int = 150) -> List[str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(str(pdf_path))
    pngs: List[str] = []
    try:
        for idx, page in enumerate(doc, start=1):
            pix = page.get_pixmap(dpi=dpi)
            img_path = out_dir / f"page_{idx:03d}.png"
            pix.save(str(img_path))
            pngs.append(str(img_path))
    finally:
        doc.close()
    return pngs


def render_pptx_to_pngs(pptx_path: Path, out_dir: Path, dpi: int = 150) -> Dict[str, Any]:
    """Render PPTX via Microsoft PowerPoint COM -> PDF -> PyMuPDF PNGs (never fakes low-fidelity output)."""
    if sys.platform != "win32":
        return {"ok": False, "reason": "PowerPoint COM rendering requires Windows Desktop Office.", "png_paths": []}
    if not pptx_path.exists():
        return {"ok": False, "reason": f"Missing PPTX file: {pptx_path}", "png_paths": []}

    try:
        import pythoncom
        import win32com.client
    except ImportError:
        return {"ok": False, "reason": "pywin32 not installed; install office extra.", "png_paths": []}

    out_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = out_dir / f"{pptx_path.stem}.pdf"
    app = None
    pres = None
    pythoncom.CoInitialize()
    try:
        app = win32com.client.DispatchEx("PowerPoint.Application")
        pres = app.Presentations.Open(str(pptx_path.resolve()), WithWindow=False)
        pres.SaveAs(str(pdf_path.resolve()), 32)  # 32 = ppSaveAsPDF
        png_paths = _rasterize_pdf(pdf_path, out_dir, dpi=dpi)
        return {"ok": True, "engine": "powerpoint_com", "pdf_path": str(pdf_path), "png_paths": png_paths}
    except Exception as exc:
        return {
            "ok": False,
            "engine": "powerpoint_com",
            "reason": str(exc),
            "hint": "Ensure Microsoft PowerPoint is licensed and not blocked by a startup modal dialog.",
            "png_paths": [],
        }
    finally:
        if pres is not None:
            try:
                pres.Close()
            except Exception:
                pass
        if app is not None:
            try:
                app.Quit()
            except Exception:
                pass
        pythoncom.CoUninitialize()


def render_canary_probe(work_dir: Path, timeout_s: int = 45) -> Dict[str, Any]:
    """Generate a minimal 1-slide PPTX canary and verify genuine Office COM rendering."""
    from pptx import Presentation
    from pptx.util import Inches

    canary_pptx = work_dir / "render_canary.pptx"
    prs = Presentation()
    sl = prs.slides.add_slide(prs.slide_layouts[5])
    box = sl.shapes.add_textbox(Inches(1), Inches(1), Inches(6), Inches(1))
    box.text_frame.text = "via54SciForge render canary"
    prs.save(str(canary_pptx))
    return render_pptx_to_pngs(canary_pptx, work_dir / "canary_out", dpi=120)
