"""Honest environment and capability diagnostics for via54SciForge."""

from __future__ import annotations

import importlib.util
import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict

from via54sciforge.core.config import SciForgeConfig
from via54sciforge.core.llm import LLMRouter


def _check_pkg(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def _safe_sqlite_counts(db_path: Path, tables: list[str]) -> Dict[str, Any]:
    if not db_path.exists():
        return {"exists": False, "path": str(db_path)}
    try:
        conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True, timeout=3.0)
        counts: Dict[str, int] = {}
        for tbl in tables:
            try:
                counts[tbl] = int(conn.execute(f'SELECT COUNT(*) FROM "{tbl}"').fetchone()[0])
            except sqlite3.Error:
                counts[tbl] = -1
        conn.close()
        return {"exists": True, "path": str(db_path), "size_bytes": db_path.stat().st_size, "counts": counts}
    except Exception as exc:
        return {"exists": True, "path": str(db_path), "error": str(exc)}


def run_doctor(config: Optional[SciForgeConfig] = None, render_canary: bool = False) -> Dict[str, Any]:
    """Run honest capability diagnostics across Python stack, KB databases, Office COM, and external binaries."""
    cfg = config or SciForgeConfig.load()
    llm_router = LLMRouter(cfg.llm)

    python_packages = {
        pkg: _check_pkg(pkg)
        for pkg in (
            "pydantic",
            "httpx",
            "yaml",
            "jinja2",
            "rich",
            "typer",
            "networkx",
            "numpy",
            "scipy",
            "matplotlib",
            "pymupdf",
            "pptx",
            "docx",
            "fastapi",
            "uvicorn",
            "mcp",
            "win32com",
        )
    }

    kb_db_info = _safe_sqlite_counts(
        Path(cfg.paths.kb_db),
        ["concepts", "triples", "kb_fts", "kb_cross_references", "concept_links", "kb_system_inventory"],
    )
    gold_db_info = _safe_sqlite_counts(Path(cfg.paths.gold_db), ["gold_edges_raft"])

    office_info: Dict[str, Any] = {
        "platform": sys.platform,
        "win32com": python_packages["win32com"],
        "powerpoint_installed": os.path.exists(r"C:\Program Files\Microsoft Office\Root\Office16\POWERPNT.EXE"),
        "word_installed": os.path.exists(r"C:\Program Files\Microsoft Office\Root\Office16\WINWORD.EXE"),
    }

    if render_canary:
        from via54sciforge.deliverables.render_bridge import render_canary_probe

        with tempfile.TemporaryDirectory() as td:
            office_info["canary_render"] = render_canary_probe(Path(td), timeout_s=cfg.deliverables.render_timeout_s)

    binaries = {
        "mmx": shutil.which("mmx") or (r"C:\Users\via54\.tools\nodejs\mmx.cmd" if os.path.exists(r"C:\Users\via54\.tools\nodejs\mmx.cmd") else None),
        "via54_medit": cfg.paths.medit_bin if os.path.exists(cfg.paths.medit_bin) else None,
        "go": shutil.which("go"),
        "pandoc": shutil.which("pandoc"),
        "xelatex": shutil.which("xelatex"),
    }

    core_ready = all(
        python_packages[p]
        for p in ("pydantic", "httpx", "networkx", "numpy", "scipy", "matplotlib", "pymupdf", "pptx", "docx", "fastapi", "mcp")
    )

    return {
        "status": "ready" if core_ready else "degraded",
        "python_version": sys.version.split()[0],
        "python_packages": python_packages,
        "llm_providers": llm_router.available_providers(),
        "active_llm_provider": llm_router.resolve_provider(),
        "knowledge_base": {
            "kb_root_exists": Path(cfg.paths.kb_root).exists(),
            "hotcache_exists": Path(cfg.paths.hotcache_dir).exists(),
            "via54_kb_db": kb_db_info,
            "gold_vault_db": gold_db_info,
        },
        "office_render": office_info,
        "external_binaries": binaries,
    }
