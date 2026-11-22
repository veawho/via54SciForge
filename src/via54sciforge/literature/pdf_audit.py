"""PDF Producer authenticity classifier, structural parser, L0 Crossref verification & dual-source manifests."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
import pymupdf as fitz

from via54sciforge.core.models import DualSourceManifest, ProducerAuditResult
from via54sciforge.literature.sources import CrossrefAdapter

BLACKLIST_REPORTLAB = ("reportlab",)
BLACKLIST_CHROME = ("skia/pdf", "chromium", "chrome", "weasyprint", "wkhtmltopdf")
WHITELIST_REAL_PDF = (
    "veeva vault",
    "adobe indesign",
    "adobe pdf library",
    "arbortext",
    "acrobat distiller",
    "xpp",
    "tex",
    "latex",
    "pdftex",
    "xetex",
    "luatex",
    "pymupdf",
)
WHITELIST_MEETING = ("pdfmake", "asco", "esmo", "gi symposium", "gi cancer")


def classify_pdf_producer(pdf_path: Path) -> ProducerAuditResult:
    """Classify a PDF using via54Medit's L0 Producer authenticity taxonomy & extract structural metadata."""
    if not pdf_path.exists():
        return ProducerAuditResult(
            pdf_path=str(pdf_path),
            pdf_type="unknown",
            repair_strategy="file_missing",
            issues=[f"File does not exist: {pdf_path}"],
        )

    doc = fitz.open(str(pdf_path))
    try:
        meta = doc.metadata or {}
        producer = (meta.get("producer") or "").strip()
        creator = (meta.get("creator") or "").strip()
        combined_pc = f"{producer} {creator}".lower()

        full_text_parts: List[str] = []
        for page in doc:
            full_text_parts.append(page.get_text("text") or "")
        full_text = "\n".join(full_text_parts)
        page_count = len(doc)
    finally:
        doc.close()

    doi_match = re.search(r"10\.\d{4,9}/[^\s\"'<>\]\)]+", full_text)
    extracted_doi = doi_match.group(0).rstrip(".,;)") if doi_match else ""
    ncts = sorted(set(re.findall(r"NCT\d{8}", full_text.upper())))

    issues: List[str] = []
    if any(k in combined_pc for k in BLACKLIST_REPORTLAB) or "image: fig" in full_text.lower():
        pdf_type = "reportlab_wrap"
        strategy = "replace_with_real_pdf"
        issues.append("Detected ReportLab/screenshot wrapper PDF; verify original publisher PDF.")
    elif any(k in combined_pc for k in BLACKLIST_CHROME) and (
        "mozilla" in combined_pc or len(full_text.strip()) < 600
    ):
        pdf_type = "chrome_screenshot"
        strategy = "find_oa_am_or_dual_source"
        issues.append("Detected Chrome/Skia web print-to-PDF capture; trigger dual-source fallback if incomplete.")
    elif any(k in combined_pc for k in WHITELIST_MEETING) or any(
        k in full_text[:1200].lower() for k in ("asco", "esmo", "abstract #", "gi symposium")
    ):
        pdf_type = "meeting_abstract"
        strategy = "keep_as_is"
    elif any(k in combined_pc for k in WHITELIST_REAL_PDF) or len(full_text.strip()) > 1500:
        pdf_type = "real_pdf"
        strategy = "keep_as_is"
    else:
        pdf_type = "unknown"
        strategy = "use_abstract_as_main_if_paywalled" if extracted_doi else "inspect_manually"
        issues.append("Unknown PDF producer metadata; verify against Crossref L0.")

    if len(full_text.strip()) < 150:
        issues.append("Low extractable text (<150 chars); likely scanned/image-only PDF requiring OCR/VLM.")

    return ProducerAuditResult(
        pdf_path=str(pdf_path),
        pdf_type=pdf_type,
        producer=producer,
        creator=creator,
        page_count=page_count,
        text_char_count=len(full_text),
        extracted_doi=extracted_doi,
        extracted_ncts=ncts,
        repair_strategy=strategy,
        issues=issues,
    )


def extract_pdf_structure(pdf_path: Path, max_pages: int = 20) -> Dict[str, Any]:
    """Extract structured blocks with exact bounding boxes from a PDF via PyMuPDF."""
    doc = fitz.open(str(pdf_path))
    pages_out: List[Dict[str, Any]] = []
    try:
        for page_idx in range(min(len(doc), max_pages)):
            page = doc[page_idx]
            blocks_raw = page.get_text("blocks") or []
            blocks = []
            for b in blocks_raw:
                x0, y0, x1, y1, text, block_no, block_type = b[:7]
                cleaned = (text or "").strip()
                if cleaned:
                    blocks.append(
                        {
                            "block_no": int(block_no),
                            "type": "text" if block_type == 0 else "image",
                            "bbox": [round(float(x0), 2), round(float(y0), 2), round(float(x1), 2), round(float(y1), 2)],
                            "text": cleaned,
                        }
                    )
            tables_count = 0
            try:
                tf = page.find_tables()
                tables_count = len(tf.tables) if tf else 0
            except Exception:
                tables_count = 0
            pages_out.append(
                {
                    "page_no": page_idx + 1,
                    "width": round(float(page.rect.width), 2),
                    "height": round(float(page.rect.height), 2),
                    "tables_detected": tables_count,
                    "blocks": blocks,
                }
            )
    finally:
        doc.close()
    return {"pdf_path": str(pdf_path), "pages_parsed": len(pages_out), "pages": pages_out}


async def verify_l0_crossref_async(audit: ProducerAuditResult, doi: Optional[str] = None) -> ProducerAuditResult:
    """Verify PDF DOI against Crossref metadata when online."""
    target_doi = (doi or audit.extracted_doi or "").strip()
    if not target_doi:
        return audit
    adapter = CrossrefAdapter()
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0), follow_redirects=True) as client:
            meta = await adapter.lookup_doi(client, target_doi)
        if meta.get("verified"):
            audit.l0_crossref_verified = True
            audit.crossref_title = meta.get("title", "")
    except Exception as exc:
        audit.issues.append(f"Crossref lookup skipped/failed: {exc}")
    return audit


def build_dual_source_manifest(
    item_id: str,
    main_pdf: str,
    fallback_pdfs: Optional[List[str]] = None,
    step2_score: Optional[float] = None,
    l0_verified: bool = False,
    evidence_sources: Optional[List[Dict[str, Any]]] = None,
    equivalent_matches: Optional[List[str]] = None,
    found_locations: Optional[List[Dict[str, Any]]] = None,
    verification_chain_5step: Optional[List[str]] = None,
    highlight_image_path: str = "",
) -> DualSourceManifest:
    """Construct dual-source provenance manifest strictly keeping main + fallback separate (never stitched)."""
    fb_list = list(fallback_pdfs or [])
    reasons: List[str] = []
    if step2_score is not None and step2_score < 0.7:
        reasons.append(f"main step2_score={step2_score:.2f} < 0.70")
    if not l0_verified and fb_list:
        reasons.append("L0 verification incomplete; fallback sources attached")
    if fb_list and not reasons:
        reasons.append("Supplemental fallback provenance attached")

    return DualSourceManifest(
        item_id=item_id,
        main_pdf=main_pdf,
        fallback_pdfs=fb_list,
        fallback_triggered=bool(reasons and fb_list),
        trigger_reason="; ".join(reasons),
        evidence_sources=list(evidence_sources or []),
        step2_score=step2_score,
        equivalent_matches=list(equivalent_matches or []),
        found_locations=list(found_locations or []),
        verification_chain_5step=list(verification_chain_5step or []),
        highlight_image_path=highlight_image_path,
    )
