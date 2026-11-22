"""Bilingual academic stylometry & surgical De-AI phrasing cleanup."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

EN_AI_TELLS: List[Tuple[str, str]] = [
    (r"\bdelve(?:s|d|ing)?\s+into\b", "examine"),
    (r"\brich\s+tapestry\b", "diverse synthesis"),
    (r"\bgame[\-\s]changer\b", "significant advance"),
    (r"\bserve(?:s)?\s+as\s+a\s+testament\s+to\b", "demonstrates"),
    (r"\bin\s+the\s+ever[\-\s]evolving\s+landscape\s+of\b", "across recent studies in"),
    (r"\bunlock(?:s|ing)?\s+the\s+full\s+potential\s+of\b", "improve the utility of"),
]

ZH_AI_TELLS: List[Tuple[str, str]] = [
    (r"值得注意的是[，,]?", ""),
    (r"总而言之[，,]?", "综上，"),
    (r"毋庸置疑[，,]?", ""),
    (r"赋能", "支持"),
    (r"抓手", "关键机制"),
    (r"全方位多角度", "系统"),
]


def audit_and_clean_stylometry(text: str, apply_cleanup: bool = True) -> tuple[str, Dict[str, Any]]:
    """Scan bilingual prose for AI-tell clichés and optionally apply surgical academic replacements."""
    hits: List[str] = []
    cleaned = text

    for pattern, repl in EN_AI_TELLS + ZH_AI_TELLS:
        found = re.findall(pattern, cleaned, flags=re.IGNORECASE)
        if found:
            hits.extend([str(f) for f in found])
            if apply_cleanup:
                cleaned = re.sub(pattern, repl, cleaned, flags=re.IGNORECASE)

    # Check excessive em-dashes outside code blocks
    em_dash_count = cleaned.count("—")
    if em_dash_count > 12:
        hits.append(f"excessive_em_dash:{em_dash_count}")

    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\n{4,}", "\n\n\n", cleaned)

    penalty = min(40.0, len(hits) * 4.5)
    clarity_score = round(max(60.0, 100.0 - penalty), 2)
    return cleaned, {
        "ai_tells_detected": len(hits),
        "samples": hits[:10],
        "clarity_score": clarity_score,
        "cleanup_applied": apply_cleanup,
    }
