"""5-step semantic claim verification, numerical equivalence expansion, and PDF bbox highlighting."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import pymupdf as fitz

from via54sciforge.core.models import DualSourceManifest
from via54sciforge.literature.pdf_audit import build_dual_source_manifest, classify_pdf_producer

PRIORITY_KEYWORDS = ("mos", "mpfs", "pfs", "hr", "orr", "survival", "ci", "p=", "p<", "r2", "ndcg", "%")


CLINICAL_ABBREV_MAP = {
    "mos": ["mOS", "Median OS", "overall survival"],
    "mpfs": ["mPFS", "median PFS", "progression-free survival"],
    "orr": ["ORR", "objective response rate"],
    "hr": ["HR", "hazard ratio"],
}


def numerical_equivalence_variants(token: str) -> List[str]:
    """Generate precision, unit, and clinical endpoint synonym variants."""
    clean = token.strip()
    variants = [clean]
    if clean.lower() in CLINICAL_ABBREV_MAP:
        for alias in CLINICAL_ABBREV_MAP[clean.lower()]:
            if alias not in variants:
                variants.append(alias)
    no_pct = clean.rstrip("%").strip()
    if no_pct and no_pct != clean:
        variants.append(no_pct)
    # Strip trailing unit like "months" so "23.7 months" also checks "23.7"
    m_unit = re.match(r"^(\d+(?:\.\d+)?)\s+(?:months?|mo|weeks?|days?|years?|yr|mg|kg|月)$", clean, re.I)
    if m_unit and m_unit.group(1) not in variants:
        variants.append(m_unit.group(1))
    try:
        val = float(no_pct)
        for fmt in (f"{val:.0f}", f"{val:.1f}", f"{val:.2f}", f"{val:.3f}"):
            if fmt not in variants:
                variants.append(fmt)
            if "%" in clean and f"{fmt}%" not in variants:
                variants.append(f"{fmt}%")
        if no_pct.endswith(".0"):
            base = no_pct[:-2]
            if base not in variants:
                variants.append(base)
    except ValueError:
        pass
    seen = set()
    out: List[str] = []
    for v in variants:
        if v and v not in seen:
            seen.add(v)
            out.append(v)
    return out


def extract_claim_data_points(text: str) -> List[str]:
    """Extract quantitative endpoints, percentages, trial IDs, and clinical/scientific tokens from a claim."""
    points: List[str] = []
    patterns = [
        r"\b\d+(?:\.\d+)?%",
        r"\b\d+(?:\.\d+)?\s*(?:months?|mo|weeks?|days?|years?|yr|mg|kg|月)\b",
        r"\b(?:HR|mOS|mPFS|ORR|R2|AUC|NDCG|p)\s*[:=<>]\s*\d+(?:\.\d+)?",
        r"\bNCT\d{8}\b",
        r"\b\d+(?:\.\d+)?\b",
    ]
    for pat in patterns:
        for m in re.findall(pat, text, flags=re.IGNORECASE):
            tok = re.sub(r"\s+", " ", m).strip()
            if len(tok) >= 2 and tok not in points:
                if tok.isdigit() and len(tok) < 2:
                    continue
                # Avoid duplicate bare number when unit-qualified token like "14.4%" or "23.7 months" already exists
                if re.fullmatch(r"\d+(?:\.\d+)?", tok) and any(
                    existing.startswith(tok + "%") or existing.startswith(tok + " ") for existing in points
                ):
                    continue
                points.append(tok)

    # Also capture salient domain abbreviations/terms (>=3 chars)
    for term in re.findall(r"\b[A-Za-z][A-Za-z0-9\+\-]{2,}\b", text):
        if term.lower() in {"the", "and", "for", "with", "that", "from", "this", "were", "have"}:
            continue
        if any(ch.isupper() for ch in term) or any(ch.isdigit() for ch in term):
            if term not in points and not any(term in p for p in points):
                points.append(term)
    return points[:16]


def _location_priority(snippet: str, token: str) -> int:
    s_low = snippet.lower()
    t_low = token.lower()
    score = 0
    for kw in PRIORITY_KEYWORDS:
        if kw in s_low or kw in t_low:
            score += 10
    if "%" in token or "." in token:
        score += 5
    return -score


def verify_claim_against_pdf(
    claim_text: str,
    pdf_path: Path,
    item_id: str = "C1",
    highlight_out_path: Optional[Path] = None,
    fallback_pdfs: Optional[List[str]] = None,
) -> DualSourceManifest:
    """Verify a quantitative or scientific claim against a PDF with bbox hits and 5-step provenance chain."""
    audit = classify_pdf_producer(pdf_path)
    data_points = extract_claim_data_points(claim_text)
    if not data_points:
        data_points = [w for w in re.findall(r"[A-Za-z0-9\u4e00-\u9fff]{3,}", claim_text)[:5]]

    doc = fitz.open(str(pdf_path))
    found_locations: List[Dict[str, Any]] = []
    matched_points: set[str] = set()
    equivalent_matches: List[str] = []
    highlight_rects_by_page: Dict[int, List[fitz.Rect]] = {}

    try:
        for dp in data_points:
            variants = numerical_equivalence_variants(dp)
            hit_for_dp = False
            for page_idx, page in enumerate(doc):
                page_text = page.get_text("text") or ""
                for var_idx, var in enumerate(variants):
                    rects = page.search_for(var)
                    if rects:
                        hit_for_dp = True
                        matched_points.add(dp)
                        if var_idx > 0 or var != dp:
                            equiv_note = f"'{dp}' -> PDF variant '{var}' (page {page_idx + 1})"
                            if equiv_note not in equivalent_matches:
                                equivalent_matches.append(equiv_note)
                        snippet = _extract_snippet(page_text, var)
                        r0 = rects[0]
                        found_locations.append(
                            {
                                "data_point": dp,
                                "matched_variant": var,
                                "page_no": page_idx + 1,
                                "bbox": [round(r0.x0, 1), round(r0.y0, 1), round(r0.x1, 1), round(r0.y1, 1)],
                                "text_snippet": snippet,
                            }
                        )
                        highlight_rects_by_page.setdefault(page_idx, []).extend(rects[:3])
                        break
                if hit_for_dp:
                    break

        if highlight_out_path and highlight_rects_by_page:
            target_page_idx = sorted(highlight_rects_by_page.keys())[0]
            page = doc[target_page_idx]
            shape = page.new_shape()
            for r in highlight_rects_by_page[target_page_idx]:
                shape.draw_rect(r)
                shape.finish(color=(0.95, 0.45, 0.05), fill=(1.0, 0.92, 0.2), fill_opacity=0.38, width=1.5)
            shape.commit()
            pix = page.get_pixmap(dpi=150)
            highlight_out_path.parent.mkdir(parents=True, exist_ok=True)
            pix.save(str(highlight_out_path))
    finally:
        doc.close()

    found_locations.sort(key=lambda loc: _location_priority(loc["text_snippet"], loc["data_point"]))
    score = round(len(matched_points) / max(len(data_points), 1), 3)

    verdict = (
        f"⭐ Full Corroboration ({len(matched_points)}/{len(data_points)}, score={score:.2f})"
        if score >= 0.99
        else f"✅ High Corroboration ({len(matched_points)}/{len(data_points)}, score={score:.2f})"
        if score >= 0.70
        else f"⚠️ Partial/Fallback Needed ({len(matched_points)}/{len(data_points)}, score={score:.2f})"
    )

    chain = [
        f"① Claim Anchor / 声明锚点: {claim_text[:160]}",
        f"② Extracted Quantitative Elements / 抽取要素 ({len(data_points)}): {', '.join(data_points)}",
        f"③ Semantic Equivalence Expansion / 语义等价扩展: {', '.join(equivalent_matches[:5]) or 'Direct exact match'}",
        "④ PDF Page & BBox Locations / PDF 定位结果: "
        + (
            "; ".join(
                f"'{l['data_point']}' @ p.{l['page_no']} bbox={l['bbox']}: {l['text_snippet'][:80]}"
                for l in found_locations[:4]
            )
            or "No matching elements found"
        ),
        f"⑤ Verification Verdict / 应证结论: {verdict} [Producer={audit.pdf_type}]",
    ]

    return build_dual_source_manifest(
        item_id=item_id,
        main_pdf=str(pdf_path),
        fallback_pdfs=fallback_pdfs,
        step2_score=score,
        l0_verified=(audit.pdf_type in ("real_pdf", "meeting_abstract") and score >= 0.7),
        evidence_sources=[
            {
                "type": audit.pdf_type,
                "doi": audit.extracted_doi,
                "layout": "main",
                "available": True,
                "data_provided": sorted(matched_points),
            }
        ],
        equivalent_matches=equivalent_matches,
        found_locations=found_locations,
        verification_chain_5step=chain,
        highlight_image_path=str(highlight_out_path) if (highlight_out_path and highlight_rects_by_page) else "",
    )


def _extract_snippet(text: str, token: str, radius: int = 75) -> str:
    idx = text.lower().find(token.lower())
    if idx < 0:
        return ""
    start = max(0, idx - radius)
    end = min(len(text), idx + len(token) + radius)
    snippet = re.sub(r"\s+", " ", text[start:end]).strip()
    snippet = re.sub(r"https?://\S+", "", snippet).strip()
    return snippet
