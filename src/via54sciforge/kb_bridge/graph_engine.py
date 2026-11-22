"""LightRAG dual-level community detection + HippoRAG 2 Personalized PageRank multi-hop KB linker."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import networkx as nx

from via54sciforge.core.config import SciForgeConfig
from via54sciforge.core.models import (
    EvidencePackage,
    EvolutionRunResult,
    ExperimentRun,
    KnowledgeEdge,
    KnowledgeLinkReport,
    KnowledgeNode,
    ResearchSynthesis,
)
from via54sciforge.core.storage import atomic_write_json
from via54sciforge.kb_bridge.local_kb import LocalKBFederation


class HybridKnowledgeGraph:
    """Fuses research findings with Sovereign KB triples/gold edges using PPR and modularity communities."""

    def __init__(self, config: Optional[SciForgeConfig] = None):
        self.config = config or SciForgeConfig.load()
        self.kb = LocalKBFederation(self.config)

    def link_and_analyze(
        self,
        run_id: str,
        query: str,
        kb_dir: Path,
        evidence: Optional[EvidencePackage] = None,
        synthesis: Optional[ResearchSynthesis] = None,
        experiment: Optional[ExperimentRun] = None,
        evolution: Optional[EvolutionRunResult] = None,
    ) -> KnowledgeLinkReport:
        kb_dir.mkdir(parents=True, exist_ok=True)
        kb_stats = self.kb.inspect_kb_stats()
        kb_available = self.kb.available()

        # Retrieve Sovereign KB artifacts
        hits = self.kb.search_fts(query, limit=10)
        if not hits and evidence and evidence.papers:
            hits = self.kb.search_fts(evidence.papers[0].title, limit=8)
        if not hits:
            # General AI/science/strategy fallback query on Sovereign KB so cross-domain bridges always surface if DB exists
            hits = self.kb.search_fts("Agent Knowledge Graph", limit=8)

        triples = self.kb.query_triples(query, limit=25)
        cross_refs = self.kb.query_cross_references([h.title for h in hits], limit=20)
        gold_edges = self.kb.query_gold_edges(limit=15)

        G = nx.DiGraph()
        node_types: Dict[str, str] = {}
        node_labels: Dict[str, str] = {}
        node_meta: Dict[str, Dict[str, Any]] = {}
        edges_list: List[KnowledgeEdge] = []

        def ensure_node(nid: str, label: str, ntype: str, meta: Optional[Dict[str, Any]] = None) -> str:
            if nid not in G:
                G.add_node(nid)
                node_types[nid] = ntype
                node_labels[nid] = label[:80]
                node_meta[nid] = meta or {}
            return nid

        def add_edge(src: str, tgt: str, rel: str, weight: float = 1.0, is_gold: bool = False, ev: str = "") -> None:
            if src == tgt:
                return
            G.add_edge(src, tgt, relation=rel, weight=weight)
            edges_list.append(
                KnowledgeEdge(source=src, target=tgt, relation=rel, weight=weight, is_gold=is_gold, evidence=ev[:160])
            )

        q_node = ensure_node("Q0", f"Research Query: {query[:50]}", "Query", {"query": query})

        # 1. Add papers & extracted topic concepts
        paper_nodes: List[str] = []
        if evidence:
            for p in evidence.papers[:8]:
                pn = ensure_node(p.id, f"{p.id}: {p.title[:48]}", "Paper", {"doi": p.doi, "year": p.year})
                paper_nodes.append(pn)
                add_edge(q_node, pn, "CITES", weight=max(0.4, p.relevance_score))
                for kw in re.findall(r"[A-Za-z][A-Za-z0-9\-]{3,}", p.title)[:3]:
                    kn = ensure_node(f"TERM_{kw.lower()}", kw, "Concept")
                    add_edge(pn, kn, "MENTIONS", weight=0.6)

        # 2. Add hypotheses, contradictions, experiment & evolution nodes
        if synthesis:
            for hyp in synthesis.hypotheses:
                hn = ensure_node(hyp.hypothesis_id, f"{hyp.hypothesis_id}: {hyp.title_en[:45]}", "Hypothesis")
                add_edge(q_node, hn, "PROPOSES", weight=hyp.confidence)
                for pid in hyp.grounding_paper_ids:
                    if pid in G:
                        add_edge(pid, hn, "SUPPORTS", weight=0.85)
            for con in synthesis.contradictions[:2]:
                if con.paper_a_id in G and con.paper_b_id in G:
                    add_edge(con.paper_a_id, con.paper_b_id, "CONTRADICTS", weight=0.9, ev=con.topic_metric)

        if experiment:
            en = ensure_node("EXP1", f"Sim: {experiment.resolved_template}", "Experiment", {"template": experiment.resolved_template})
            add_edge("H1" if "H1" in G else q_node, en, "VALIDATES", weight=0.95)

        if evolution:
            evn = ensure_node(
                "EVO1",
                f"Evolved ({evolution.benchmark_name}, {evolution.improvement_pct:+.1f}%)",
                "Algorithm",
                {"fitness": evolution.best_candidate.fitness},
            )
            add_edge("H2" if "H2" in G else q_node, evn, "OPTIMIZES", weight=0.95)

        # 3. Federate Local Sovereign KB Concepts, Cross-Refs, Triples & Gold Axioms
        kb_node_ids: List[str] = []
        for idx, h in enumerate(hits[:8], start=1):
            kid = f"KB_{h.concept_id or idx}"
            ensure_node(kid, f"KB: {h.title[:46]}", "KBConcept", {"rel_path": h.rel_path, "concept_id": h.concept_id})
            kb_node_ids.append(kid)
            add_edge(q_node, kid, "KB_BRIDGES", weight=0.75)
            # Link to matching paper/term nodes via lexical overlap
            h_low = f"{h.title} {h.snippet}".lower()
            for pn in paper_nodes[:4]:
                p_words = set(re.findall(r"[a-z]{4,}", node_labels[pn].lower()))
                if any(w in h_low for w in p_words):
                    add_edge(pn, kid, "EXTENDS", weight=0.7)

        for cr in cross_refs[:10]:
            s_id = f"CR_{abs(hash(cr['source_title'])) % 100000}"
            t_id = f"CR_{abs(hash(cr['target_title'])) % 100000}"
            ensure_node(s_id, cr["source_title"][:44], "KBConcept")
            ensure_node(t_id, cr["target_title"][:44], "KBConcept")
            add_edge(s_id, t_id, "KB_CROSSREF", weight=float(cr.get("similarity_score") or 0.5))
            if kb_node_ids:
                add_edge(kb_node_ids[0], s_id, "KB_BRIDGES", weight=0.55)

        for tr in triples[:10]:
            s_id = f"TR_{abs(hash(tr['subject'])) % 100000}"
            o_id = f"TR_{abs(hash(tr['object'])) % 100000}"
            ensure_node(s_id, str(tr["subject"])[:40], "KBTriple")
            ensure_node(o_id, str(tr["object"])[:40], "KBTriple")
            add_edge(s_id, o_id, str(tr.get("predicate") or "RELATED_TO")[:24], weight=0.7)
            if kb_node_ids:
                add_edge(kb_node_ids[0], s_id, "KB_BRIDGES", weight=0.5)

        for ge in gold_edges[:6]:
            gid = f"GOLD_{ge.get('link_id', 0)}"
            label = str(ge.get("link_text") or ge.get("link_kind") or "Gold Axiom")[:46]
            ensure_node(gid, f"★ {label}", "GoldAxiom", {"confidence": ge.get("confidence", 0.99)})
            anchor = kb_node_ids[0] if kb_node_ids else q_node
            add_edge(anchor, gid, "GOLD_AXIOM", weight=float(ge.get("weight") or 5.0), is_gold=True)

        # 4. HippoRAG 2 Personalized PageRank (multi-hop associative ranking)
        undir = G.to_undirected()
        personalization = {n: 0.0 for n in undir.nodes()}
        personalization[q_node] = 0.5
        for pn in paper_nodes[:3]:
            personalization[pn] = 0.2
        ppr_scores = nx.pagerank(undir, alpha=0.85, personalization=personalization) if len(undir) > 0 else {}

        # 5. LightRAG community detection
        comm_map: Dict[str, int] = {}
        communities_out: List[Dict[str, Any]] = []
        if len(undir) >= 2 and undir.number_of_edges() >= 1:
            comms = list(nx.algorithms.community.greedy_modularity_communities(undir))
            for cid, members in enumerate(comms):
                m_sorted = sorted(members)
                for m in m_sorted:
                    comm_map[m] = cid
                communities_out.append(
                    {
                        "community_id": cid,
                        "size": len(m_sorted),
                        "sample_labels": [node_labels[m] for m in m_sorted[:5]],
                    }
                )

        # Identify multi-hop KB bridges (KB/Gold/Triple nodes with highest PPR score)
        bridges = []
        for nid, sc in sorted(ppr_scores.items(), key=lambda x: -x[1]):
            if node_types.get(nid) in ("KBConcept", "GoldAxiom", "KBTriple"):
                try:
                    hop_dist = nx.shortest_path_length(undir, q_node, nid)
                except nx.NetworkXNoPath:
                    hop_dist = -1
                bridges.append(
                    {
                        "node_id": nid,
                        "label": node_labels[nid],
                        "node_type": node_types[nid],
                        "ppr_score": round(float(sc), 5),
                        "hop_distance": hop_dist,
                        "community_id": comm_map.get(nid, 0),
                    }
                )

        nodes_out = [
            KnowledgeNode(
                node_id=nid,
                label=node_labels[nid],
                node_type=node_types[nid],
                community_id=comm_map.get(nid, 0),
                ppr_score=round(float(ppr_scores.get(nid, 0.0)), 5),
                metadata=node_meta.get(nid, {}),
            )
            for nid in sorted(G.nodes())
        ]

        wiki_links = [f"[[{h.title}]]" for h in hits[:8]]
        mermaid = self._render_mermaid(nodes_out, edges_list)

        graph_payload = {
            "run_id": run_id,
            "query": query,
            "nodes": [n.model_dump() for n in nodes_out],
            "edges": [e.model_dump() for e in edges_list],
            "communities": communities_out,
            "ppr_multihop_bridges": bridges[:12],
        }
        graph_json_path = atomic_write_json(kb_dir / "knowledge_graph.json", graph_payload)

        return KnowledgeLinkReport(
            run_id=run_id,
            query=query,
            kb_available=kb_available,
            kb_stats=kb_stats,
            matched_kb_concepts=hits,
            matched_triples=triples[:15],
            gold_edges=gold_edges[:10],
            ppr_multihop_bridges=bridges[:12],
            communities=communities_out,
            nodes=nodes_out,
            edges=edges_list,
            wiki_links=wiki_links,
            mermaid_diagram=mermaid,
            graph_json_path=str(graph_json_path),
        )

    @staticmethod
    def _render_mermaid(nodes: List[KnowledgeNode], edges: List[KnowledgeEdge]) -> str:
        """Render Mermaid flowchart TD strictly quoting labels to prevent syntax errors."""
        keep_ids = {n.node_id for n in sorted(nodes, key=lambda x: -x.ppr_score)[:18]}
        lines = ["flowchart LR"]
        for n in nodes:
            if n.node_id not in keep_ids:
                continue
            safe_id = re.sub(r"[^A-Za-z0-9_]", "_", n.node_id)
            safe_lbl = n.label.replace('"', "'").replace("[", "(").replace("]", ")")
            lines.append(f'  {safe_id}["{safe_lbl}"]')
        for e in edges[:28]:
            if e.source in keep_ids and e.target in keep_ids:
                s_id = re.sub(r"[^A-Za-z0-9_]", "_", e.source)
                t_id = re.sub(r"[^A-Za-z0-9_]", "_", e.target)
                rel = e.relation.replace('"', "'")
                lines.append(f"  {s_id} -->|{rel}| {t_id}")
        return "\n".join(lines)
