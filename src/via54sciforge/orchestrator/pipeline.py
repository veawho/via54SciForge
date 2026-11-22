"""End-to-end 7-pillar pipeline orchestrator with JSON checkpointing and WorkspaceStore indexing."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

from via54sciforge.core.config import LLMConfig, SciForgeConfig
from via54sciforge.core.llm import LLMRouter
from via54sciforge.core.models import (
    EvidencePackage,
    ExperimentSpec,
    ManuscriptSpec,
    PipelineRunResult,
    ResearchQuestion,
    SlideSpec,
)
from via54sciforge.core.storage import WorkspaceStore, atomic_write_json, atomic_write_text
from via54sciforge.deliverables.pptx_builder import AcademicPPTXBuilder
from via54sciforge.deliverables.reports import DerivativeReportGenerator, ReportType
from via54sciforge.evolution.engine import EvolutionEngine
from via54sciforge.kb_bridge.graph_engine import HybridKnowledgeGraph
from via54sciforge.kb_bridge.sync import KBSyncManager
from via54sciforge.literature.grader import compute_prisma_counts, grade_evidence_package
from via54sciforge.literature.researcher import synthesize_research
from via54sciforge.literature.sources import LiteratureRouter
from via54sciforge.simulation.runner import ExperimentManager
from via54sciforge.simulation.visualizer import plot_literature_landscape
from via54sciforge.writing.composer import ManuscriptComposer


class SciForgePipeline:
    """Executes all seven pillars of via54SciForge with checkpoint persistence."""

    def __init__(self, config: Optional[SciForgeConfig] = None):
        self.config = config or SciForgeConfig.load()
        self.store = WorkspaceStore(self.config.paths.runs_path, self.config.paths.state_db_path)
        self.llm = LLMRouter(self.config.llm)
        self.lit_router = LiteratureRouter(self.config)
        self.exp_mgr = ExperimentManager(timeout_s=self.config.simulation.sandbox_timeout_s, dpi=self.config.simulation.dpi)
        self.evo_engine = EvolutionEngine(timeout_s=15, dpi=self.config.simulation.dpi)
        self.kg_engine = HybridKnowledgeGraph(self.config)
        self.kb_sync = KBSyncManager(self.config)
        self.composer = ManuscriptComposer(self.llm)
        self.report_gen = DerivativeReportGenerator()
        self.pptx_builder = AcademicPPTXBuilder()

    def run(
        self,
        topic: str,
        offline: bool = False,
        max_papers: int = 10,
        sources: Optional[List[str]] = None,
        sim_template: str = "auto",
        sim_seed: int = 42,
        benchmark: str = "symbolic_discovery",
        generations: int = 8,
        islands: int = 3,
        report_type: ReportType = "deep_research",
        ppt_theme: str = "academic_navy",
        render_visuals: bool = False,
        sync_kb: bool = False,
        run_id: Optional[str] = None,
    ) -> PipelineRunResult:
        rid = run_id or self.store.new_run_id()
        run_dir = self.store.prepare_run_dir(rid)
        statuses: Dict[str, str] = {}
        active_llm = LLMRouter(LLMConfig(provider="offline")) if offline else self.llm

        def save_ckpt(stage: str, status: str) -> None:
            statuses[stage] = status
            atomic_write_json(run_dir / "checkpoint.json", {"run_id": rid, "topic": topic, "stages": statuses})

        # Stage 1: Multi-source literature retrieval & GRADE screening
        question = ResearchQuestion(query=topic, max_results=max_papers, sources=sources or [])
        papers, sources_used, raw_count = self.lit_router.search(question, offline=offline)
        prisma = compute_prisma_counts(raw_count, papers)
        grade = grade_evidence_package(papers)
        evidence = EvidencePackage(
            run_id=rid,
            question=question,
            papers=papers,
            prisma_counts=prisma,
            grade=grade,
            sources_used=sources_used,
            summary_en=f"Retrieved {len(papers)} deduplicated works across {len(sources_used)} sources for '{topic}'. {grade.reasoning_en}",
            summary_zh=f"围绕“{topic}”从 {len(sources_used)} 个文献源去重纳入 {len(papers)} 篇文献。{grade.reasoning_zh}",
        )
        lit_chart = plot_literature_landscape(evidence, run_dir / "literature" / "fig_literature_landscape.png", dpi=self.config.simulation.dpi)
        atomic_write_json(run_dir / "literature" / "evidence_package.json", evidence)
        save_ckpt("1_literature", "completed")

        # Stage 2: Deep research synthesis, contradiction detection & hypothesis mining
        synthesis = synthesize_research(evidence, llm_router=active_llm)
        # Recompute GRADE with contradiction penalty
        evidence.grade = grade_evidence_package(papers, synthesis.contradictions)
        atomic_write_json(run_dir / "literature" / "evidence_package.json", evidence)
        atomic_write_json(run_dir / "research" / "synthesis.json", synthesis)
        save_ckpt("2_research", "completed")

        # Stage 3: Sandboxed scientific experiment simulation & statistical testing
        h1 = synthesis.hypotheses[0] if synthesis.hypotheses else None
        exp_spec = ExperimentSpec(
            hypothesis_id=h1.hypothesis_id if h1 else "H1",
            template=sim_template,
            seed=sim_seed,
        )
        experiment = self.exp_mgr.run_experiment(rid, run_dir / "simulation", exp_spec, hypothesis=h1, topic=topic)
        atomic_write_json(run_dir / "simulation" / "experiment_run.json", experiment)
        save_ckpt("3_simulation", "completed")

        # Stage 4: MAP-Elites multi-island algorithm evolution
        evolution = self.evo_engine.evolve(
            run_id=rid,
            evo_dir=run_dir / "evolution",
            benchmark_name=benchmark,
            generations=generations,
            population_per_gen=self.config.evolution.population_per_gen,
            num_islands=islands,
            migration_interval=self.config.evolution.migration_interval,
            novelty_threshold=self.config.evolution.novelty_threshold,
            seed=sim_seed,
            llm_router=active_llm,
        )
        save_ckpt("4_evolution", "completed")

        # Stage 5: Sovereign KB linking & hybrid Personalized PageRank graph
        knowledge_link = self.kg_engine.link_and_analyze(
            run_id=rid,
            query=topic,
            kb_dir=run_dir / "knowledge",
            evidence=evidence,
            synthesis=synthesis,
            experiment=experiment,
            evolution=evolution,
        )
        knowledge_link.sync_preview = self.kb_sync.sync_monograph(
            title=f"via54SciForge Study: {topic}",
            markdown_body=f"# {topic}\n\n{synthesis.synthesis_zh}\n\n{synthesis.synthesis_en}\n",
            metadata={"run_id": rid, "topic": topic, "grade": evidence.grade.grade, "wiki_links": knowledge_link.wiki_links},
            apply=sync_kb,
        )
        atomic_write_json(run_dir / "knowledge" / "knowledge_link_report.json", knowledge_link)
        save_ckpt("5_knowledge_link", "completed")

        # Stage 6: Academic manuscript authoring, citation grounding & automated peer review
        manuscript = ManuscriptComposer(active_llm).compose(
            run_id=rid,
            out_dir=run_dir / "manuscript",
            topic=topic,
            spec=ManuscriptSpec(),
            evidence=evidence,
            synthesis=synthesis,
            experiment=experiment,
            evolution=evolution,
            knowledge_link=knowledge_link,
        )
        atomic_write_json(run_dir / "manuscript" / "manuscript_output.json", manuscript)
        save_ckpt("6_writing_review", "completed")

        # Stage 7: Derivative reports (MD/HTML/DOCX) + 12-slide PPTX & manifest
        report = self.report_gen.generate(
            run_id=rid,
            out_dir=run_dir / "deliverables",
            topic=topic,
            report_type=report_type,
            evidence=evidence,
            synthesis=synthesis,
            experiment=experiment,
            evolution=evolution,
            knowledge_link=knowledge_link,
            manuscript=manuscript,
            extra_charts=[lit_chart],
        )
        slides = self.pptx_builder.build(
            run_id=rid,
            out_dir=run_dir / "deliverables",
            topic=topic,
            spec=SlideSpec(theme=ppt_theme, render_visuals=render_visuals),
            evidence=evidence,
            synthesis=synthesis,
            experiment=experiment,
            evolution=evolution,
            knowledge_link=knowledge_link,
            manuscript=manuscript,
            lit_chart_path=lit_chart,
        )
        save_ckpt("7_deliverables", "completed")

        summary_md = self._build_run_summary_md(
            rid, topic, run_dir, evidence, synthesis, experiment, evolution, knowledge_link, manuscript, report, slides
        )
        summary_md_path = atomic_write_text(run_dir / "RUN_SUMMARY.md", summary_md)
        result = PipelineRunResult(
            run_id=rid,
            topic=topic,
            workspace_dir=str(run_dir),
            offline_mode=offline,
            stage_statuses=statuses,
            evidence=evidence,
            synthesis=synthesis,
            experiment=experiment,
            evolution=evolution,
            knowledge_link=knowledge_link,
            manuscript=manuscript,
            report=report,
            slides=slides,
            summary_md_path=str(summary_md_path),
            summary_json_path=str(run_dir / "pipeline_summary.json"),
        )
        atomic_write_json(run_dir / "pipeline_summary.json", result)

        self.store.record_run(
            run_id=rid,
            topic=topic,
            workspace_dir=run_dir,
            status="completed",
            grade=evidence.grade.grade,
            improvement_pct=evolution.improvement_pct,
            grounding_rate=manuscript.citation_audit.grounding_rate,
            summary_json_path=str(run_dir / "pipeline_summary.json"),
        )
        self.store.index_text(rid, "run_summary", topic, summary_md)
        return result

    @staticmethod
    def _build_run_summary_md(
        rid, topic, run_dir, evidence, synthesis, experiment, evolution, kb_link, manuscript, report, slides
    ) -> str:
        return "\n".join(
            [
                f"# via54SciForge Run Summary / 全流程运行总览 ({rid})",
                f"- **Topic / 研究主题**: {topic}",
                f"- **Workspace / 运行目录**: `{run_dir}`",
                f"- **Pillar 1 — Literature**: `{len(evidence.papers)}` papers | GRADE `{evidence.grade.grade}` ({evidence.grade.score}/10) | Sources: `{evidence.sources_used}`",
                f"- **Pillar 2 — Deep Research**: `{len(synthesis.contradictions)}` contradictions | `{len(synthesis.gaps)}` gaps | `{len(synthesis.hypotheses)}` hypotheses",
                f"- **Pillar 3 — Simulation**: `{experiment.resolved_template}` | {experiment.summary_zh}",
                f"- **Pillar 4 — Evolution**: `{evolution.benchmark_name}` | `{evolution.seed_fitness:.4f} -> {evolution.best_candidate.fitness:.4f}` ({evolution.improvement_pct:+.2f}%)",
                f"- **Pillar 5 — Sovereign KB**: `available={kb_link.kb_available}` | `{len(kb_link.matched_kb_concepts)}` concepts | `{len(kb_link.gold_edges)}` gold edges | `{len(kb_link.ppr_multihop_bridges)}` PPR bridges",
                f"- **Pillar 6 — Academic Manuscript**: Citation Grounding `{manuscript.citation_audit.grounding_rate:.1%}` | Peer Review `{manuscript.review.overall_score}/10` (`{manuscript.review.decision}`)",
                f"- **Pillar 7 — Deliverables**: `{slides.slide_count}` slides (`{slides.pptx_path}`) | Report `{report.html_path}`",
            ]
        ) + "\n"
