"""MCP 2.x stdio server exposing 13 genuinely wired via54SciForge tools (zero placeholders)."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp.server.mcpserver import MCPServer

from via54sciforge.core.config import SciForgeConfig
from via54sciforge.core.doctor import run_doctor
from via54sciforge.core.llm import LLMRouter
from via54sciforge.core.models import (
    EvidencePackage,
    EvolutionRunResult,
    ExperimentRun,
    ExperimentSpec,
    KnowledgeLinkReport,
    ManuscriptSpec,
    ResearchQuestion,
    ResearchSynthesis,
    SlideSpec,
)
from via54sciforge.core.storage import WorkspaceStore
from via54sciforge.deliverables.pptx_builder import AcademicPPTXBuilder
from via54sciforge.deliverables.reports import DerivativeReportGenerator
from via54sciforge.evolution.engine import EvolutionEngine
from via54sciforge.kb_bridge.graph_engine import HybridKnowledgeGraph
from via54sciforge.kb_bridge.local_kb import LocalKBFederation
from via54sciforge.literature.grader import compute_prisma_counts, grade_evidence_package
from via54sciforge.literature.pdf_audit import classify_pdf_producer
from via54sciforge.literature.researcher import synthesize_research
from via54sciforge.literature.sources import LiteratureRouter
from via54sciforge.literature.verifier import verify_claim_against_pdf
from via54sciforge.orchestrator.pipeline import SciForgePipeline
from via54sciforge.simulation.runner import ExperimentManager
from via54sciforge.writing.composer import ManuscriptComposer

# Ensure all logging stays on stderr so JSON-RPC stdout remains spotless.
logging.basicConfig(stream=sys.stderr, level=logging.INFO)


def create_mcp_server(config: Optional[SciForgeConfig] = None) -> MCPServer:
    cfg = config or SciForgeConfig.load()
    mcp = MCPServer(
        name="via54SciForge",
        instructions="Unified autonomous scientific research, simulation, algorithm evolution, Sovereign KB linking, academic writing, and deliverable suite.",
    )

    @mcp.tool()
    def sciforge_doctor(render_canary: bool = False) -> Dict[str, Any]:
        """Run honest system diagnostics (Python stack, Sovereign KB, LLM providers, Office COM)."""
        return run_doctor(cfg, render_canary=render_canary)

    @mcp.tool()
    async def sciforge_lit_search(
        query: str, max_results: int = 10, sources: Optional[List[str]] = None, offline: bool = False
    ) -> Dict[str, Any]:
        """Run concurrent multi-source literature search (OpenAlex, PubMed, arXiv, S2, EuropePMC) + GRADE."""
        router = LiteratureRouter(cfg)
        q = ResearchQuestion(query=query, max_results=max_results, sources=sources or [])
        papers, used, raw_cnt = await router.search_async(q, offline=offline)
        grade = grade_evidence_package(papers)
        return EvidencePackage(
            run_id=WorkspaceStore.new_run_id("lit"),
            question=q,
            papers=papers,
            prisma_counts=compute_prisma_counts(raw_cnt, papers),
            grade=grade,
            sources_used=used,
        ).model_dump()

    @mcp.tool()
    def sciforge_pdf_audit(pdf_path: str) -> Dict[str, Any]:
        """Classify PDF producer authenticity (real_pdf vs reportlab_wrap vs chrome_screenshot) and extract DOI/NCT."""
        return classify_pdf_producer(Path(pdf_path)).model_dump()

    @mcp.tool()
    def sciforge_claim_verify(pdf_path: str, claim: str, highlight_png: Optional[str] = None) -> Dict[str, Any]:
        """Verify quantitative claim against PDF using semantic numerical equivalence & 5-step provenance."""
        hp = Path(highlight_png) if highlight_png else None
        return verify_claim_against_pdf(claim, Path(pdf_path), highlight_out_path=hp).model_dump()

    @mcp.tool()
    async def sciforge_research_synthesize(query: str, max_results: int = 10, offline: bool = False) -> Dict[str, Any]:
        """Run ASReview active prioritization, PaperQA2 RCS passages, contradiction detection & hypothesis mining."""
        router = LiteratureRouter(cfg)
        q = ResearchQuestion(query=query, max_results=max_results)
        papers, used, raw_cnt = await router.search_async(q, offline=offline)
        pkg = EvidencePackage(
            run_id=WorkspaceStore.new_run_id("res"),
            question=q,
            papers=papers,
            prisma_counts=compute_prisma_counts(raw_cnt, papers),
            grade=grade_evidence_package(papers),
            sources_used=used,
        )
        return synthesize_research(pkg, LLMRouter(cfg.llm)).model_dump()

    @mcp.tool()
    def sciforge_simulate_experiment(topic: str, template: str = "auto", seed: int = 42) -> Dict[str, Any]:
        """Execute sandboxed scientific simulation branches with SciPy stats & Benjamini-Hochberg FDR."""
        store = WorkspaceStore(cfg.paths.runs_path, cfg.paths.state_db_path)
        rid = store.new_run_id("sim")
        rdir = store.prepare_run_dir(rid)
        return ExperimentManager(cfg.simulation.sandbox_timeout_s, cfg.simulation.dpi).run_experiment(
            rid, rdir / "simulation", ExperimentSpec(template=template, seed=seed), topic=topic
        ).model_dump()

    @mcp.tool()
    def sciforge_evolve_algorithm(
        benchmark: str = "symbolic_discovery", generations: int = 8, islands: int = 3, seed: int = 42
    ) -> Dict[str, Any]:
        """Run MAP-Elites multi-island algorithm evolution with UCB1 bandit and novelty rejection."""
        store = WorkspaceStore(cfg.paths.runs_path, cfg.paths.state_db_path)
        rid = store.new_run_id("evo")
        rdir = store.prepare_run_dir(rid)
        return EvolutionEngine(dpi=cfg.simulation.dpi).evolve(
            rid, rdir / "evolution", benchmark_name=benchmark, generations=generations, num_islands=islands, seed=seed, llm_router=LLMRouter(cfg.llm)
        ).model_dump()

    @mcp.tool()
    def sciforge_kb_stats() -> Dict[str, Any]:
        """Inspect live read-only Sovereign Knowledge Base (via54_kb.db & gold_vault_node_z.db) counts."""
        return LocalKBFederation(cfg).inspect_kb_stats()

    @mcp.tool()
    def sciforge_kb_search(query: str, limit: int = 10) -> Dict[str, Any]:
        """Search Sovereign Knowledge Base FTS5 & concepts strictly read-only."""
        hits = LocalKBFederation(cfg).search_fts(query, limit=limit)
        return {"query": query, "hits": [h.model_dump() for h in hits]}

    @mcp.tool()
    def sciforge_kb_link_graph(query: str) -> Dict[str, Any]:
        """Build LightRAG + HippoRAG2 Personalized PageRank multi-hop graph linking query to Sovereign KB."""
        store = WorkspaceStore(cfg.paths.runs_path, cfg.paths.state_db_path)
        rid = store.new_run_id("kb")
        rdir = store.prepare_run_dir(rid)
        return HybridKnowledgeGraph(cfg).link_and_analyze(rid, query, rdir / "knowledge").model_dump()

    @mcp.tool()
    def sciforge_write_paper(run_dir: str, style: str = "academic", paper_type: str = "imrad") -> Dict[str, Any]:
        """Compose bilingual academic manuscript (MD/TeX/BibTeX/DOCX) + citation grounding & peer review."""
        rd = Path(run_dir)
        ev_p, syn_p, exp_p, evo_p, kb_p = (
            rd / "literature" / "evidence_package.json",
            rd / "research" / "synthesis.json",
            rd / "simulation" / "experiment_run.json",
            rd / "evolution" / "evolution_summary.json",
            rd / "knowledge" / "knowledge_link_report.json",
        )
        ev = EvidencePackage.model_validate_json(ev_p.read_text(encoding="utf-8")) if ev_p.exists() else None
        syn = ResearchSynthesis.model_validate_json(syn_p.read_text(encoding="utf-8")) if syn_p.exists() else None
        exp = ExperimentRun.model_validate_json(exp_p.read_text(encoding="utf-8")) if exp_p.exists() else None
        evo = EvolutionRunResult.model_validate_json(evo_p.read_text(encoding="utf-8")) if evo_p.exists() else None
        kb = KnowledgeLinkReport.model_validate_json(kb_p.read_text(encoding="utf-8")) if kb_p.exists() else None
        return ManuscriptComposer(LLMRouter(cfg.llm)).compose(
            rd.name, rd / "manuscript", ev.question.query if ev else rd.name, ManuscriptSpec(paper_type=paper_type, latex_style=style), ev, syn, exp, evo, kb
        ).model_dump()

    @mcp.tool()
    def sciforge_deliver_report_and_ppt(
        run_dir: str, report_type: str = "deep_research", theme: str = "academic_navy", render_visuals: bool = False
    ) -> Dict[str, Any]:
        """Generate bilingual MD/HTML/DOCX derivative report and 12-slide PPTX + dual-source manifest."""
        rd = Path(run_dir)
        ev_p, syn_p, exp_p, evo_p, kb_p = (
            rd / "literature" / "evidence_package.json",
            rd / "research" / "synthesis.json",
            rd / "simulation" / "experiment_run.json",
            rd / "evolution" / "evolution_summary.json",
            rd / "knowledge" / "knowledge_link_report.json",
        )
        ev = EvidencePackage.model_validate_json(ev_p.read_text(encoding="utf-8")) if ev_p.exists() else None
        syn = ResearchSynthesis.model_validate_json(syn_p.read_text(encoding="utf-8")) if syn_p.exists() else None
        exp = ExperimentRun.model_validate_json(exp_p.read_text(encoding="utf-8")) if exp_p.exists() else None
        evo = EvolutionRunResult.model_validate_json(evo_p.read_text(encoding="utf-8")) if evo_p.exists() else None
        kb = KnowledgeLinkReport.model_validate_json(kb_p.read_text(encoding="utf-8")) if kb_p.exists() else None
        topic = ev.question.query if ev else rd.name
        rep = DerivativeReportGenerator().generate(rd.name, rd / "deliverables", topic, report_type, ev, syn, exp, evo, kb)
        deck = AcademicPPTXBuilder().build(rd.name, rd / "deliverables", topic, SlideSpec(theme=theme, render_visuals=render_visuals), ev, syn, exp, evo, kb)
        return {"report": rep.model_dump(), "slides": deck.model_dump()}

    @mcp.tool()
    def sciforge_run_full_pipeline(
        topic: str,
        offline: bool = False,
        benchmark: str = "symbolic_discovery",
        generations: int = 8,
        islands: int = 3,
        theme: str = "academic_navy",
    ) -> Dict[str, Any]:
        """Execute all 7 pillars end-to-end (literature -> research -> simulation -> evolution -> KB -> paper -> report/PPTX)."""
        return SciForgePipeline(cfg).run(
            topic=topic, offline=offline, benchmark=benchmark, generations=generations, islands=islands, ppt_theme=theme
        ).model_dump()

    return mcp


def main() -> None:
    server = create_mcp_server()
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
