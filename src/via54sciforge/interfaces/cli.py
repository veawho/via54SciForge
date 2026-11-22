"""Typer + Rich CLI for via54SciForge with strict machine-readable --json output support."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, List, Optional

import typer
from pydantic import BaseModel
from rich.console import Console
from rich.table import Table

from via54sciforge.core.config import SciForgeConfig
from via54sciforge.core.doctor import run_doctor
from via54sciforge.core.llm import LLMRouter
from via54sciforge.core.models import (
    EvidencePackage,
    ExperimentSpec,
    ManuscriptSpec,
    PipelineRunResult,
    ResearchQuestion,
    SlideSpec,
)
from via54sciforge.core.storage import WorkspaceStore, atomic_write_json
from via54sciforge.deliverables.pptx_builder import AcademicPPTXBuilder
from via54sciforge.deliverables.reports import DerivativeReportGenerator
from via54sciforge.evolution.engine import EvolutionEngine
from via54sciforge.kb_bridge.graph_engine import HybridKnowledgeGraph
from via54sciforge.kb_bridge.local_kb import LocalKBFederation
from via54sciforge.kb_bridge.sync import KBSyncManager
from via54sciforge.literature.grader import compute_prisma_counts, grade_evidence_package
from via54sciforge.literature.pdf_audit import classify_pdf_producer, verify_l0_crossref_async
from via54sciforge.literature.researcher import synthesize_research
from via54sciforge.literature.sources import LiteratureRouter
from via54sciforge.literature.verifier import verify_claim_against_pdf
from via54sciforge.orchestrator.pipeline import SciForgePipeline
from via54sciforge.simulation.runner import ExperimentManager
from via54sciforge.writing.composer import ManuscriptComposer
from via54sciforge.writing.reviewer import audit_citations, peer_review_manuscript

app = typer.Typer(help="via54SciForge — Autonomous Research, Simulation, Evolution, KB & Publication Suite")
lit_app = typer.Typer(help="Literature retrieval, PDF producer auditing & 5-step claim verification")
kb_app = typer.Typer(help="Sovereign Knowledge Base search, PPR linking & safe sync")
write_app = typer.Typer(help="Bilingual academic manuscript authoring & automated peer review")
deliver_app = typer.Typer(help="Derivative reports (MD/HTML/DOCX) & 12-slide PPTX deck generation")

app.add_typer(lit_app, name="lit")
app.add_typer(kb_app, name="kb")
app.add_typer(write_app, name="write")
app.add_typer(deliver_app, name="deliver")

console = Console()


def _emit_json(obj: Any) -> None:
    if isinstance(obj, BaseModel):
        typer.echo(obj.model_dump_json(indent=2))
    else:
        typer.echo(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


@app.command()
def doctor(
    render_canary: bool = typer.Option(False, "--render-canary", help="Run real Office COM canary render test"),
    json_out: bool = typer.Option(False, "--json", help="Emit machine-readable JSON"),
) -> None:
    """Inspect Python environment, Sovereign KB databases, LLM providers, and Office COM readiness."""
    report = run_doctor(SciForgeConfig.load(), render_canary=render_canary)
    if json_out:
        _emit_json(report)
        return
    tbl = Table(title="via54SciForge Doctor / 系统诊断")
    tbl.add_column("Subsystem")
    tbl.add_column("Details")
    tbl.add_row("Status", f"{report['status']} (Python {report['python_version']})")
    tbl.add_row("Active LLM", f"{report['active_llm_provider']} ({report['llm_providers']})")
    kb_db = report["knowledge_base"]["via54_kb_db"]
    tbl.add_row("Sovereign KB", f"exists={kb_db.get('exists')} counts={kb_db.get('counts', {})}")
    tbl.add_row("Office COM", str(report["office_render"]))
    console.print(tbl)


@lit_app.command("search")
def lit_search(
    query: str = typer.Argument(..., help="Scientific or clinical research question"),
    sources: Optional[str] = typer.Option(None, "--sources", help="Comma-separated sources (openalex,pubmed,arxiv,semanticscholar,europepmc)"),
    max_results: int = typer.Option(12, "--max", help="Maximum fused papers"),
    offline: bool = typer.Option(False, "--offline", help="Use deterministic offline seed corpus"),
    json_out: bool = typer.Option(False, "--json", help="Emit machine-readable JSON"),
) -> None:
    """Multi-source concurrent literature search, deduplication, and GRADE rating."""
    cfg = SciForgeConfig.load()
    router = LiteratureRouter(cfg)
    src_list = [s.strip() for s in sources.split(",")] if sources else []
    q = ResearchQuestion(query=query, max_results=max_results, sources=src_list)
    papers, used, raw_cnt = router.search(q, offline=offline)
    grade = grade_evidence_package(papers)
    pkg = EvidencePackage(
        run_id=WorkspaceStore.new_run_id("lit"),
        question=q,
        papers=papers,
        prisma_counts=compute_prisma_counts(raw_cnt, papers),
        grade=grade,
        sources_used=used,
        summary_en=grade.reasoning_en,
        summary_zh=grade.reasoning_zh,
    )
    if json_out:
        _emit_json(pkg)
        return
    console.print(f"[bold green]GRADE {grade.grade}[/] ({grade.score}/10) | Sources: {used}")
    for p in papers:
        console.print(f"  [{p.id}] ({p.year}) {p.title} — {p.source_origins}")


@lit_app.command("audit")
def lit_audit(
    pdf_path: Path = typer.Argument(..., help="Path to PDF file"),
    doi: Optional[str] = typer.Option(None, "--doi", help="Optional DOI for Crossref L0 verification"),
    crossref: bool = typer.Option(False, "--crossref", help="Query live Crossref API for L0 check"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Classify PDF authenticity (Producer whitelist/blacklist) and optionally verify against Crossref."""
    res = classify_pdf_producer(pdf_path)
    if crossref:
        res = asyncio.run(verify_l0_crossref_async(res, doi=doi))
    if json_out:
        _emit_json(res)
        return
    console.print(res.model_dump())


@lit_app.command("verify")
def lit_verify(
    pdf_path: Path = typer.Argument(..., help="Path to PDF file"),
    claim: str = typer.Option(..., "--claim", help="Claim or quantitative assertion to verify"),
    highlight: Optional[Path] = typer.Option(None, "--highlight", help="Optional PNG output path for bbox highlight"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Verify claim against PDF using 5-step provenance & semantic numerical equivalence."""
    res = verify_claim_against_pdf(claim, pdf_path, highlight_out_path=highlight)
    if json_out:
        _emit_json(res)
        return
    for step in res.verification_chain_5step:
        console.print(step)


@app.command()
def research(
    query: str = typer.Argument(..., help="Research topic"),
    max_results: int = typer.Option(10, "--max"),
    offline: bool = typer.Option(False, "--offline"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Deep research synthesis: ASReview ranking, PaperQA2 RCS passages, contradiction matrix & hypotheses."""
    cfg = SciForgeConfig.load()
    router = LiteratureRouter(cfg)
    q = ResearchQuestion(query=query, max_results=max_results)
    papers, used, raw_cnt = router.search(q, offline=offline)
    pkg = EvidencePackage(
        run_id=WorkspaceStore.new_run_id("res"),
        question=q,
        papers=papers,
        prisma_counts=compute_prisma_counts(raw_cnt, papers),
        grade=grade_evidence_package(papers),
        sources_used=used,
    )
    syn = synthesize_research(pkg, LLMRouter(cfg.llm))
    if json_out:
        _emit_json(syn)
        return
    console.print(f"[bold]Synthesis (EN):[/] {syn.synthesis_en}\n[bold]综合摘要 (ZH):[/] {syn.synthesis_zh}")
    for h in syn.hypotheses:
        console.print(f"  - {h.hypothesis_id}: {h.title_en} / {h.title_zh}")


@app.command()
def simulate(
    topic: str = typer.Option("Adaptive Scientific Hypothesis", "--topic"),
    template: str = typer.Option("auto", "--template"),
    seed: int = typer.Option(42, "--seed"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Run AST-verified sandboxed simulation experiment with multi-branch ablations and FDR stats."""
    cfg = SciForgeConfig.load()
    store = WorkspaceStore(cfg.paths.runs_path, cfg.paths.state_db_path)
    rid = store.new_run_id("sim")
    run_dir = store.prepare_run_dir(rid)
    mgr = ExperimentManager(timeout_s=cfg.simulation.sandbox_timeout_s, dpi=cfg.simulation.dpi)
    exp = mgr.run_experiment(rid, run_dir / "simulation", ExperimentSpec(template=template, seed=seed), topic=topic)
    if json_out:
        _emit_json(exp)
        return
    console.print(f"[bold green]{exp.resolved_template}[/]: {exp.summary_zh}")


@app.command()
def evolve(
    benchmark: str = typer.Option("symbolic_discovery", "--benchmark", help="symbolic_discovery|circle_packing|evidence_scoring"),
    generations: int = typer.Option(10, "--generations"),
    islands: int = typer.Option(3, "--islands"),
    seed: int = typer.Option(42, "--seed"),
    seed_file: Optional[Path] = typer.Option(None, "--seed-file", help="Custom seed Python algorithm file"),
    eval_file: Optional[Path] = typer.Option(None, "--eval-file", help="Custom evaluator Python file"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Run MAP-Elites multi-island algorithm evolution with UCB1 bandit and novelty filtering."""
    cfg = SciForgeConfig.load()
    store = WorkspaceStore(cfg.paths.runs_path, cfg.paths.state_db_path)
    rid = store.new_run_id("evo")
    run_dir = store.prepare_run_dir(rid)
    eng = EvolutionEngine(dpi=cfg.simulation.dpi)
    res = eng.evolve(
        run_id=rid,
        evo_dir=run_dir / "evolution",
        benchmark_name=benchmark,
        generations=generations,
        num_islands=islands,
        seed=seed,
        llm_router=LLMRouter(cfg.llm),
        seed_file=seed_file,
        eval_file=eval_file,
    )
    if json_out:
        _emit_json(res)
        return
    console.print(f"[bold cyan]{res.summary_zh}[/]\nBest code: {res.best_code_path}")


@kb_app.command("stats")
def kb_stats(json_out: bool = typer.Option(False, "--json")) -> None:
    """Inspect live read-only Sovereign Knowledge Base row counts & DCAT-3 catalog."""
    stats = LocalKBFederation(SciForgeConfig.load()).inspect_kb_stats()
    if json_out:
        _emit_json(stats)
        return
    console.print(stats)


@kb_app.command("search")
def kb_search(
    query: str = typer.Argument(..., help="Search query"),
    limit: int = typer.Option(10, "--limit"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Search Sovereign Knowledge Base (via54_kb.db FTS5 + concepts) read-only."""
    hits = LocalKBFederation(SciForgeConfig.load()).search_fts(query, limit=limit)
    if json_out:
        _emit_json([h.model_dump() for h in hits])
        return
    for h in hits:
        console.print(f"[{h.concept_id}] {h.title} ({h.rel_path})")


@kb_app.command("link")
def kb_link(
    query: str = typer.Argument(..., help="Topic or path to evidence_package.json"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Build hybrid research + Sovereign KB graph with HippoRAG2 PPR multi-hop discovery."""
    cfg = SciForgeConfig.load()
    store = WorkspaceStore(cfg.paths.runs_path, cfg.paths.state_db_path)
    rid = store.new_run_id("kb")
    run_dir = store.prepare_run_dir(rid)
    evidence: Optional[EvidencePackage] = None
    p = Path(query)
    if p.exists() and p.suffix.lower() == ".json":
        evidence = EvidencePackage.model_validate_json(p.read_text(encoding="utf-8"))
        q_txt = evidence.question.query
    else:
        q_txt = query
    rep = HybridKnowledgeGraph(cfg).link_and_analyze(rid, q_txt, run_dir / "knowledge", evidence=evidence)
    if json_out:
        _emit_json(rep)
        return
    console.print(f"Nodes={len(rep.nodes)}, Edges={len(rep.edges)}, Bridges={len(rep.ppr_multihop_bridges)}, Gold={len(rep.gold_edges)}")


@kb_app.command("sync")
def kb_sync_cmd(
    artifact_md: Path = typer.Argument(..., help="Markdown monograph file to evaluate/sync"),
    apply: bool = typer.Option(False, "--apply", help="Actually write to D:\\KnowledgeBase\\03_Projects\\via54SciForge (default: dry-run)"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Evaluate 3-way create/append/skip KB ingestion (dry-run by default; --apply writes safely)."""
    body = artifact_md.read_text(encoding="utf-8")
    title = artifact_md.stem
    res = KBSyncManager(SciForgeConfig.load()).sync_monograph(title, body, {"source_file": str(artifact_md)}, apply=apply)
    if json_out:
        _emit_json(res)
        return
    console.print(res)


@write_app.command("paper")
def write_paper(
    run_dir: Path = typer.Option(..., "--run-dir", help="Existing run directory containing JSON artifacts"),
    style: str = typer.Option("academic", "--style", help="ieee|nature|neurips|academic"),
    paper_type: str = typer.Option("imrad", "--type", help="imrad|systematic_review|technical_monograph"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Compose bilingual academic manuscript (MD + LaTeX + BibTeX + DOCX) from a run directory."""
    ev_p = run_dir / "literature" / "evidence_package.json"
    syn_p = run_dir / "research" / "synthesis.json"
    exp_p = run_dir / "simulation" / "experiment_run.json"
    evo_p = run_dir / "evolution" / "evolution_summary.json"
    kb_p = run_dir / "knowledge" / "knowledge_link_report.json"

    from via54sciforge.core.models import EvolutionRunResult, ExperimentRun, KnowledgeLinkReport, ResearchSynthesis

    ev = EvidencePackage.model_validate_json(ev_p.read_text(encoding="utf-8")) if ev_p.exists() else None
    syn = ResearchSynthesis.model_validate_json(syn_p.read_text(encoding="utf-8")) if syn_p.exists() else None
    exp = ExperimentRun.model_validate_json(exp_p.read_text(encoding="utf-8")) if exp_p.exists() else None
    evo = EvolutionRunResult.model_validate_json(evo_p.read_text(encoding="utf-8")) if evo_p.exists() else None
    kb = KnowledgeLinkReport.model_validate_json(kb_p.read_text(encoding="utf-8")) if kb_p.exists() else None

    topic = ev.question.query if ev else run_dir.name
    ms = ManuscriptComposer(LLMRouter(SciForgeConfig.load().llm)).compose(
        run_id=run_dir.name,
        out_dir=run_dir / "manuscript",
        topic=topic,
        spec=ManuscriptSpec(paper_type=paper_type, latex_style=style),
        evidence=ev,
        synthesis=syn,
        experiment=exp,
        evolution=evo,
        knowledge_link=kb,
    )
    if json_out:
        _emit_json(ms)
        return
    console.print(f"Manuscript written: {ms.md_path}, {ms.tex_path}, {ms.docx_path} (grounding={ms.citation_audit.grounding_rate:.1%})")


@write_app.command("review")
def write_review(
    manuscript_md: Path = typer.Argument(..., help="Path to manuscript Markdown file"),
    evidence_json: Optional[Path] = typer.Option(None, "--evidence", help="Optional evidence_package.json"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Run zero-hallucination citation grounding audit and 6-dimension automated peer review."""
    text = manuscript_md.read_text(encoding="utf-8")
    ev = EvidencePackage.model_validate_json(evidence_json.read_text(encoding="utf-8")) if (evidence_json and evidence_json.exists()) else None
    ca = audit_citations(text, [p.id for p in (ev.papers if ev else [])])
    rev = peer_review_manuscript(text, evidence=ev, citation_audit=ca)
    out = {"citation_audit": ca.model_dump(), "peer_review": rev.model_dump()}
    if json_out:
        _emit_json(out)
        return
    console.print(out)


@deliver_app.command("report")
def deliver_report(
    run_dir: Path = typer.Option(..., "--run-dir"),
    report_type: str = typer.Option("deep_research", "--type", help="executive_brief|deep_research|evidence_matrix|translation_brief"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Generate bilingual derivative report (MD + interactive HTML + DOCX) from run directory."""
    from via54sciforge.core.models import EvolutionRunResult, ExperimentRun, KnowledgeLinkReport, ManuscriptOutput, ResearchSynthesis

    ev_p = run_dir / "literature" / "evidence_package.json"
    syn_p = run_dir / "research" / "synthesis.json"
    exp_p = run_dir / "simulation" / "experiment_run.json"
    evo_p = run_dir / "evolution" / "evolution_summary.json"
    kb_p = run_dir / "knowledge" / "knowledge_link_report.json"
    ms_p = run_dir / "manuscript" / "manuscript_output.json"

    ev = EvidencePackage.model_validate_json(ev_p.read_text(encoding="utf-8")) if ev_p.exists() else None
    syn = ResearchSynthesis.model_validate_json(syn_p.read_text(encoding="utf-8")) if syn_p.exists() else None
    exp = ExperimentRun.model_validate_json(exp_p.read_text(encoding="utf-8")) if exp_p.exists() else None
    evo = EvolutionRunResult.model_validate_json(evo_p.read_text(encoding="utf-8")) if evo_p.exists() else None
    kb = KnowledgeLinkReport.model_validate_json(kb_p.read_text(encoding="utf-8")) if kb_p.exists() else None
    ms = ManuscriptOutput.model_validate_json(ms_p.read_text(encoding="utf-8")) if ms_p.exists() else None

    rep = DerivativeReportGenerator().generate(
        run_id=run_dir.name,
        out_dir=run_dir / "deliverables",
        topic=ev.question.query if ev else run_dir.name,
        report_type=report_type,
        evidence=ev,
        synthesis=syn,
        experiment=exp,
        evolution=evo,
        knowledge_link=kb,
        manuscript=ms,
    )
    if json_out:
        _emit_json(rep)
        return
    console.print(f"Report generated: {rep.html_path}")


@deliver_app.command("ppt")
def deliver_ppt(
    run_dir: Path = typer.Option(..., "--run-dir"),
    theme: str = typer.Option("academic_navy", "--theme", help="academic_navy|clinical_clean|executive_slate|dark_keynote"),
    render: bool = typer.Option(False, "--render", help="Render slides to PNG via Windows PowerPoint COM"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Generate 12-slide bilingual PPTX + dual-source provenance manifest."""
    from via54sciforge.core.models import EvolutionRunResult, ExperimentRun, KnowledgeLinkReport, ManuscriptOutput, ResearchSynthesis

    ev_p = run_dir / "literature" / "evidence_package.json"
    syn_p = run_dir / "research" / "synthesis.json"
    exp_p = run_dir / "simulation" / "experiment_run.json"
    evo_p = run_dir / "evolution" / "evolution_summary.json"
    kb_p = run_dir / "knowledge" / "knowledge_link_report.json"
    ms_p = run_dir / "manuscript" / "manuscript_output.json"

    ev = EvidencePackage.model_validate_json(ev_p.read_text(encoding="utf-8")) if ev_p.exists() else None
    syn = ResearchSynthesis.model_validate_json(syn_p.read_text(encoding="utf-8")) if syn_p.exists() else None
    exp = ExperimentRun.model_validate_json(exp_p.read_text(encoding="utf-8")) if exp_p.exists() else None
    evo = EvolutionRunResult.model_validate_json(evo_p.read_text(encoding="utf-8")) if evo_p.exists() else None
    kb = KnowledgeLinkReport.model_validate_json(kb_p.read_text(encoding="utf-8")) if kb_p.exists() else None
    ms = ManuscriptOutput.model_validate_json(ms_p.read_text(encoding="utf-8")) if ms_p.exists() else None

    deck = AcademicPPTXBuilder().build(
        run_id=run_dir.name,
        out_dir=run_dir / "deliverables",
        topic=ev.question.query if ev else run_dir.name,
        spec=SlideSpec(theme=theme, render_visuals=render),
        evidence=ev,
        synthesis=syn,
        experiment=exp,
        evolution=evo,
        knowledge_link=kb,
        manuscript=ms,
    )
    if json_out:
        _emit_json(deck)
        return
    console.print(f"PPTX generated ({deck.slide_count} slides): {deck.pptx_path}")


@app.command()
def run(
    topic: str = typer.Argument(..., help="Research topic or clinical/scientific question"),
    offline: bool = typer.Option(False, "--offline", help="Run strictly without external network APIs"),
    max_papers: int = typer.Option(10, "--max-papers"),
    sim_template: str = typer.Option("auto", "--sim-template"),
    benchmark: str = typer.Option("symbolic_discovery", "--benchmark"),
    generations: int = typer.Option(8, "--generations"),
    islands: int = typer.Option(3, "--islands"),
    report_type: str = typer.Option("deep_research", "--report-type"),
    theme: str = typer.Option("academic_navy", "--theme"),
    render: bool = typer.Option(False, "--render"),
    sync_kb: bool = typer.Option(False, "--sync-kb"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Execute the complete 7-pillar end-to-end scientific discovery & publication pipeline."""
    pipe = SciForgePipeline(SciForgeConfig.load())
    res: PipelineRunResult = pipe.run(
        topic=topic,
        offline=offline,
        max_papers=max_papers,
        sim_template=sim_template,
        benchmark=benchmark,
        generations=generations,
        islands=islands,
        report_type=report_type,
        ppt_theme=theme,
        render_visuals=render,
        sync_kb=sync_kb,
    )
    if json_out:
        _emit_json(res)
        return
    console.print(f"[bold green]Pipeline Completed[/]: {res.run_id}")
    console.print(f"Summary MD: {res.summary_md_path}")
    console.print(f"PPTX: {res.slides.pptx_path if res.slides else 'N/A'}")
    console.print(f"HTML Report: {res.report.html_path if res.report else 'N/A'}")


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8540, "--port"),
) -> None:
    """Start the FastAPI REST API + Interactive Bilingual Web Workbench."""
    import uvicorn
    from via54sciforge.interfaces.api import create_app

    uvicorn.run(create_app(), host=host, port=port)


@app.command("mcp")
def mcp_cmd() -> None:
    """Start the via54SciForge stdio MCP server (13 tools)."""
    from via54sciforge.interfaces.mcp_server import main as mcp_main

    mcp_main()


if __name__ == "__main__":
    app()
