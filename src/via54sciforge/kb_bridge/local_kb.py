"""Read-only connector to via54 Sovereign Knowledge Base (via54_kb.db, gold_vault_node_z.db, DCAT-3)."""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from via54sciforge.core.config import SciForgeConfig
from via54sciforge.core.models import KBSearchHit


def _ro_connect(db_path: Path) -> Optional[sqlite3.Connection]:
    if not db_path.exists():
        return None
    conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True, timeout=5.0)
    conn.row_factory = sqlite3.Row
    return conn


def _extract_query_terms(query: str) -> List[str]:
    raw_terms = re.findall(r"[A-Za-z0-9_]{2,}|[\u4e00-\u9fff]{2,}", query or "")
    stop = {"the", "and", "for", "with", "from", "based", "using", "into", "over", "study", "analysis"}
    cleaned: List[str] = []
    for t in raw_terms:
        if t.lower() not in stop and t not in cleaned:
            cleaned.append(t)
    return cleaned[:10]


class LocalKBFederation:
    """Strictly read-only query interface over via54_kb.db, gold_vault_node_z.db, and DCAT-3 catalog."""

    def __init__(self, config: Optional[SciForgeConfig] = None):
        self.config = config or SciForgeConfig.load()
        self.kb_db = Path(self.config.paths.kb_db)
        self.gold_db = Path(self.config.paths.gold_db)
        self.kb_root = Path(self.config.paths.kb_root)
        self.okf_catalog = Path(self.config.paths.okf_catalog)

    def available(self) -> bool:
        return self.kb_db.exists()

    def inspect_kb_stats(self) -> Dict[str, Any]:
        stats: Dict[str, Any] = {
            "kb_db_exists": self.kb_db.exists(),
            "kb_db_path": str(self.kb_db),
            "gold_db_exists": self.gold_db.exists(),
            "gold_db_path": str(self.gold_db),
            "kb_root_exists": self.kb_root.exists(),
            "tables": {},
            "dcat_catalog": {},
        }
        conn = _ro_connect(self.kb_db)
        if conn is not None:
            try:
                for tbl in ("bundles", "concepts", "concept_links", "triples", "kb_fts", "kb_cross_references", "kb_system_inventory"):
                    try:
                        stats["tables"][tbl] = int(conn.execute(f'SELECT COUNT(*) FROM "{tbl}"').fetchone()[0])
                    except sqlite3.Error:
                        pass
            finally:
                conn.close()

        gconn = _ro_connect(self.gold_db)
        if gconn is not None:
            try:
                stats["tables"]["gold_edges_raft"] = int(
                    gconn.execute("SELECT COUNT(*) FROM gold_edges_raft").fetchone()[0]
                )
            except sqlite3.Error:
                pass
            finally:
                gconn.close()

        if self.okf_catalog.exists():
            try:
                cat = json.loads(self.okf_catalog.read_text(encoding="utf-8"))
                stats["dcat_catalog"] = {
                    "title": cat.get("dct:title", ""),
                    "entities_count": cat.get("iso11179:DataElementIndex", {}).get("entities_count", 0),
                    "relations_count": cat.get("iso11179:DataElementIndex", {}).get("relations_count", 0),
                    "gold_edges_count": cat.get("iso11179:DataElementIndex", {}).get("gold_edges_count", 0),
                }
            except Exception:
                pass
        return stats

    def search_fts(self, query: str, limit: int = 12) -> List[KBSearchHit]:
        """Search kb_fts FTS5 safely with fallback LIKE queries over concepts."""
        conn = _ro_connect(self.kb_db)
        if conn is None:
            return []
        terms = _extract_query_terms(query)
        hits: List[KBSearchHit] = []
        seen_titles: set[str] = set()

        try:
            if terms:
                fts_expr = " OR ".join(f'"{t}"' for t in terms[:6])
                try:
                    rows = conn.execute(
                        """
                        SELECT f.title, substr(f.content, 1, 320) AS snippet, f.tags,
                               bm25(kb_fts) AS rank_score, c.concept_id, c.rel_path, c.source_path
                        FROM kb_fts f
                        LEFT JOIN concepts c ON c.title = f.title
                        WHERE kb_fts MATCH ?
                        ORDER BY rank_score
                        LIMIT ?
                        """,
                        (fts_expr, limit),
                    ).fetchall()
                    for r in rows:
                        title = r["title"] or ""
                        if not title or title in seen_titles:
                            continue
                        seen_titles.add(title)
                        tags = []
                        try:
                            tags = json.loads(r["tags"] or "[]")
                        except Exception:
                            pass
                        hits.append(
                            KBSearchHit(
                                concept_id=int(r["concept_id"] or 0),
                                title=title,
                                rel_path=r["rel_path"] or "",
                                source_path=r["source_path"] or "",
                                snippet=(r["snippet"] or "").replace("\n", " ").strip(),
                                score=round(abs(float(r["rank_score"] or 0.0)), 4),
                                tags=[str(x) for x in tags[:6]],
                            )
                        )
                except sqlite3.Error:
                    pass

            if len(hits) < limit:
                like_terms = terms[:4] or [query.strip()[:30]]
                clauses = " OR ".join(["(title LIKE ? OR description LIKE ?)"] * len(like_terms))
                params: List[Any] = []
                for lt in like_terms:
                    pat = f"%{lt}%"
                    params.extend([pat, pat])
                params.append(limit)
                try:
                    rows = conn.execute(
                        f"""
                        SELECT concept_id, title, rel_path, source_path, substr(description, 1, 320) AS snippet, tags_json
                        FROM concepts
                        WHERE {clauses}
                        LIMIT ?
                        """,
                        params,
                    ).fetchall()
                    for r in rows:
                        title = r["title"] or ""
                        if not title or title in seen_titles:
                            continue
                        seen_titles.add(title)
                        tags = []
                        try:
                            tags = json.loads(r["tags_json"] or "[]")
                        except Exception:
                            pass
                        hits.append(
                            KBSearchHit(
                                concept_id=int(r["concept_id"] or 0),
                                title=title,
                                rel_path=r["rel_path"] or "",
                                source_path=r["source_path"] or "",
                                snippet=(r["snippet"] or "").replace("\n", " ").strip(),
                                score=0.5,
                                tags=[str(x) for x in tags[:6]],
                            )
                        )
                        if len(hits) >= limit:
                            break
                except sqlite3.Error:
                    pass
        finally:
            conn.close()
        return hits[:limit]

    def query_triples(self, query: str, limit: int = 30) -> List[Dict[str, Any]]:
        conn = _ro_connect(self.kb_db)
        if conn is None:
            return []
        terms = _extract_query_terms(query)[:5]
        out: List[Dict[str, Any]] = []
        try:
            if terms:
                clauses = " OR ".join(["(subject LIKE ? OR object LIKE ?)"] * len(terms))
                params: List[Any] = []
                for t in terms:
                    params.extend([f"%{t}%", f"%{t}%"])
                params.append(limit)
                rows = conn.execute(
                    f"SELECT subject, predicate, object, concept_id FROM triples WHERE {clauses} LIMIT ?",
                    params,
                ).fetchall()
                out = [dict(r) for r in rows]
            if not out:
                rows = conn.execute(
                    "SELECT subject, predicate, object, concept_id FROM triples LIMIT ?", (min(limit, 12),)
                ).fetchall()
                out = [dict(r) for r in rows]
        except sqlite3.Error:
            pass
        finally:
            conn.close()
        return out

    def query_cross_references(self, titles: List[str], limit: int = 25) -> List[Dict[str, Any]]:
        conn = _ro_connect(self.kb_db)
        if conn is None:
            return []
        out: List[Dict[str, Any]] = []
        try:
            clean = [t for t in titles if t][:5]
            if clean:
                clauses = " OR ".join(["(source_title LIKE ? OR target_title LIKE ?)"] * len(clean))
                params: List[Any] = []
                for t in clean:
                    key = t[:24]
                    params.extend([f"%{key}%", f"%{key}%"])
                params.append(limit)
                rows = conn.execute(
                    f"""
                    SELECT source_title, target_title, relation_type, similarity_score
                    FROM kb_cross_references
                    WHERE {clauses}
                    ORDER BY similarity_score DESC
                    LIMIT ?
                    """,
                    params,
                ).fetchall()
                out = [dict(r) for r in rows]
        except sqlite3.Error:
            pass
        finally:
            conn.close()
        return out

    def query_gold_edges(self, limit: int = 25) -> List[Dict[str, Any]]:
        """Query verified axiomatic edges from gold_vault_node_z.db (or concept_links fallback)."""
        gconn = _ro_connect(self.gold_db)
        if gconn is not None:
            try:
                rows = gconn.execute(
                    """
                    SELECT link_id, src_concept_id, target_path, link_kind, link_text, weight, confidence
                    FROM gold_edges_raft
                    ORDER BY weight DESC, confidence DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
                return [dict(r) for r in rows]
            except sqlite3.Error:
                pass
            finally:
                gconn.close()

        conn = _ro_connect(self.kb_db)
        if conn is None:
            return []
        try:
            rows = conn.execute(
                """
                SELECT link_id, src_concept_id, target_path, link_kind, link_text, weight, confidence
                FROM concept_links
                WHERE is_gold = 1
                ORDER BY weight DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]
        except sqlite3.Error:
            return []
        finally:
            conn.close()
