"""Tests for Pillar 5: Sovereign KB read-only queries, HippoRAG2 PPR linking, LightRAG communities & safe sync."""

import sqlite3
from pathlib import Path

from via54sciforge.core.config import SciForgeConfig
from via54sciforge.core.models import EvidencePackage, PaperRecord, ResearchQuestion
from via54sciforge.kb_bridge.graph_engine import HybridKnowledgeGraph
from via54sciforge.kb_bridge.local_kb import LocalKBFederation
from via54sciforge.kb_bridge.sync import KBSyncManager


def _create_mock_kb(kb_db: Path, gold_db: Path) -> None:
    conn = sqlite3.connect(kb_db)
    conn.executescript(
        """
        CREATE TABLE bundles (bundle_id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE concepts (
            concept_id INTEGER PRIMARY KEY, bundle_id INTEGER, rel_path TEXT, type TEXT,
            title TEXT, description TEXT, resource TEXT, tags_json TEXT, timestamp TEXT, source_path TEXT
        );
        CREATE TABLE concept_links (
            link_id INTEGER PRIMARY KEY, src_concept_id INTEGER, target_path TEXT, link_kind TEXT,
            link_text TEXT, position INTEGER, weight REAL, confidence REAL, is_gold INTEGER
        );
        CREATE TABLE triples (id INTEGER PRIMARY KEY, subject TEXT, predicate TEXT, object TEXT, concept_id INTEGER);
        CREATE TABLE kb_cross_references (
            id INTEGER PRIMARY KEY, source_title TEXT, target_title TEXT, relation_type TEXT, similarity_score REAL, updated_at TEXT
        );
        CREATE TABLE kb_system_inventory (id INTEGER PRIMARY KEY, file_name TEXT);
        CREATE VIRTUAL TABLE kb_fts USING fts5(title, content, tags);
        """
    )
    conn.execute(
        "INSERT INTO concepts VALUES (101, 1, '1.基础知识库/Agent记忆.md', 'concept', 'Agent Memory & Knowledge Graph', 'Multi-hop associative graph memory using Personalized PageRank', 'res', '[\"Agent\",\"Graph\"]', '2026-10-01', 'D:/KB/101.md')"
    )
    conn.execute(
        "INSERT INTO kb_fts (title, content, tags) VALUES ('Agent Memory & Knowledge Graph', 'Multi-hop associative graph memory using Personalized PageRank', '[\"Agent\",\"Graph\"]')"
    )
    conn.execute(
        "INSERT INTO triples VALUES (1, 'Knowledge Graph', 'ENABLES', 'Multi-Hop Reasoning', 101)"
    )
    conn.execute(
        "INSERT INTO kb_cross_references VALUES (1, 'Agent Memory & Knowledge Graph', 'Dissipative Structure Theory', 'CROSS_DISCIPLINE', 0.88, '2026-10-01')"
    )
    conn.commit()
    conn.close()

    gconn = sqlite3.connect(gold_db)
    gconn.execute(
        "CREATE TABLE gold_edges_raft (link_id INTEGER PRIMARY KEY, src_concept_id INTEGER, target_path TEXT, link_kind TEXT, link_text TEXT, weight REAL, confidence REAL)"
    )
    gconn.execute(
        "INSERT INTO gold_edges_raft VALUES (1, 101, 'concept://102', 'AXIOM', 'Cross-Disciplinary Graph Spine', 8.5, 0.99)"
    )
    gconn.commit()
    gconn.close()


def test_mock_kb_federation_and_graph_linking(tmp_path: Path):
    kb_db = tmp_path / "mock_kb.db"
    gold_db = tmp_path / "mock_gold.db"
    _create_mock_kb(kb_db, gold_db)

    cfg = SciForgeConfig.load()
    cfg.paths.kb_db = str(kb_db)
    cfg.paths.gold_db = str(gold_db)
    cfg.paths.kb_root = str(tmp_path / "kb_root")
    cfg.paths.hotcache_dir = str(tmp_path / "hotcache")
    Path(cfg.paths.kb_root).mkdir()
    Path(cfg.paths.hotcache_dir).mkdir()

    # Include punctuation that would crash unsanitized FTS5
    kg = HybridKnowledgeGraph(cfg)
    ev = EvidencePackage(
        run_id="kb_t",
        question=ResearchQuestion(query="Agent Memory: Knowledge Graph (2026)?!"),
        papers=[PaperRecord(id="P1", title="Graph Memory Evaluation", year=2026, abstract="Personalized PageRank", source_origins=["arxiv"])],
    )
    rep = kg.link_and_analyze("kb_t", ev.question.query, tmp_path / "kb_out", evidence=ev)
    assert rep.kb_available is True
    assert len(rep.matched_kb_concepts) >= 1
    assert len(rep.gold_edges) == 1
    assert len(rep.ppr_multihop_bridges) >= 1
    assert len(rep.communities) >= 1
    assert "flowchart LR" in rep.mermaid_diagram
    assert Path(rep.graph_json_path).exists()

    # Test dry-run & apply sync
    sync_mgr = KBSyncManager(cfg)
    prev = sync_mgr.sync_monograph("New Research Note", "Content about Graph Memory.", {"k": "v"}, apply=False)
    assert prev["dry_run"] is True and prev["written"] is False
    applied = sync_mgr.sync_monograph("New Research Note", "Content about Graph Memory.", {"k": "v"}, apply=True)
    assert applied["written"] is True and Path(applied["target_note_path"]).exists()


def test_live_sovereign_kb_read_only_if_present():
    cfg = SciForgeConfig.load()
    fed = LocalKBFederation(cfg)
    stats = fed.inspect_kb_stats()
    if stats["kb_db_exists"]:
        assert stats["tables"]["concepts"] > 100
        assert stats["tables"]["triples"] > 1000
        hits = fed.search_fts("知识图谱", limit=5)
        assert isinstance(hits, list)
