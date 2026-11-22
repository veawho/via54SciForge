"""Safe 3-way (create/append/skip) KB synchronization with dry-run default & Z:\\ <=5MB guard."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Any, Dict, Optional

from via54sciforge.core.config import HOTCACHE_MAX_BYTES, SciForgeConfig
from via54sciforge.core.storage import atomic_write_json, atomic_write_text
from via54sciforge.kb_bridge.local_kb import LocalKBFederation

FORBIDDEN_HOTCACHE_EXTS = {".pptx", ".pdf", ".mp4", ".mov", ".avi", ".mkv"}


class KBSyncManager:
    """Evaluates and optionally syncs research monographs into D:\\KnowledgeBase\\03_Projects\\via54SciForge."""

    def __init__(self, config: Optional[SciForgeConfig] = None):
        self.config = config or SciForgeConfig.load()
        self.kb = LocalKBFederation(self.config)

    def evaluate_sync(self, title: str, markdown_body: str) -> Dict[str, Any]:
        """Mirror kb_ingest_pipeline.py's create/append/skip decision against read-only via54_kb.db."""
        hits = self.kb.search_fts(title, limit=5)
        if not hits:
            return {
                "decision": "create",
                "reason": "No matching title/concept in via54_kb.db; safe to create new project monograph.",
                "matched_title": None,
                "overlap_ratio": 0.0,
            }

        best = hits[0]
        new_words = set(re.findall(r"[a-z0-9\u4e00-\u9fff]{2,}", markdown_body.lower()))
        old_words = set(re.findall(r"[a-z0-9\u4e00-\u9fff]{2,}", f"{best.title} {best.snippet}".lower()))
        overlap = len(new_words & old_words) / max(len(old_words), 1) if old_words else 0.0

        if title.strip().lower() == best.title.strip().lower() and overlap > 0.8:
            decision = "skip"
            reason = f"Strong match with '{best.title}' (overlap={overlap:.2f}); skip duplicate."
        elif overlap >= 0.45:
            decision = "append"
            reason = f"Related concept '{best.title}' found (overlap={overlap:.2f}); append incremental insights."
        else:
            decision = "create"
            reason = f"Top hit '{best.title}' has low overlap ({overlap:.2f}); create distinct project note."

        return {
            "decision": decision,
            "reason": reason,
            "matched_title": best.title,
            "matched_rel_path": best.rel_path,
            "overlap_ratio": round(overlap, 3),
        }

    def sync_monograph(
        self,
        title: str,
        markdown_body: str,
        metadata: Dict[str, Any],
        apply: bool = False,
    ) -> Dict[str, Any]:
        """Preview (default dry_run) or write bilingual research note to D:\\KnowledgeBase\\03_Projects\\via54SciForge."""
        decision_info = self.evaluate_sync(title, markdown_body)
        slug = re.sub(r"[^A-Za-z0-9\u4e00-\u9fff_\-]+", "_", title).strip("_")[:64] or "sciforge_note"
        target_note = Path(self.config.paths.kb_root) / "03_Projects" / "via54SciForge" / f"{slug}_{date.today().isoformat()}.md"
        hotcache_index = Path(self.config.paths.hotcache_dir) / "via54sciforge_cache" / f"{slug}_index.json"

        payload: Dict[str, Any] = {
            **decision_info,
            "dry_run": not apply,
            "target_note_path": str(target_note),
            "hotcache_index_path": str(hotcache_index),
            "written": False,
        }

        if not apply or decision_info["decision"] == "skip":
            return payload

        if Path(self.config.paths.kb_root).exists():
            atomic_write_text(target_note, markdown_body)
            payload["written"] = True

        # Enforce Z:\KnowledgeBase_HotCache <= 5MB & no PPTX/PDF/video rule strictly
        if Path(self.config.paths.hotcache_dir).exists():
            if hotcache_index.suffix.lower() in FORBIDDEN_HOTCACHE_EXTS:
                raise ValueError(f"Refused forbidden heavy media extension in HotCache: {hotcache_index}")
            meta_bytes = len(str(metadata).encode("utf-8"))
            if meta_bytes <= HOTCACHE_MAX_BYTES:
                atomic_write_json(hotcache_index, metadata)
                payload["hotcache_written"] = True
            else:
                payload["hotcache_written"] = False
                payload["hotcache_note"] = "Skipped HotCache write: exceeds 5MB limit"

        return payload
