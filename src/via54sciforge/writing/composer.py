"""Bilingual academic manuscript composer outputting Markdown, LaTeX, BibTeX, and publication Word (.docx)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional

from docx import Document
from docx.shared import Inches, Pt, RGBColor

from via54sciforge.core.llm import LLMRouter
from via54sciforge.core.models import (
    EvidencePackage,
    EvolutionRunResult,
    ExperimentRun,
    KnowledgeLinkReport,
    ManuscriptOutput,
    ManuscriptSpec,
    PaperRecord,
    ResearchSynthesis,
)
from via54sciforge.core.storage import atomic_write_text
from via54sciforge.writing.reviewer import audit_citations, peer_review_manuscript
from via54sciforge.writing.stylometry import audit_and_clean_stylometry


def _latex_escape(text: str) -> str:
    repls = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
    }
    out = text or ""
    for k, v in repls.items():
        if k == "\\":
            continue
        out = out.replace(k, v)
    return out


def build_bibtex(papers: List[PaperRecord]) -> str:
    entries: List[str] = []
    for p in papers:
        authors = " and ".join(p.authors) if p.authors else "Unknown Authors"
        year = p.year if p.year > 0 else 2026
        journal = p.journal or "Scientific Archive"
        doi_line = f"  doi = {{{p.doi}}},\n" if p.doi else ""
        entries.append(
            f"@article{{{p.id},\n"
            f"  title = {{{p.title}}},\n"
            f"  author = {{{authors}}},\n"
            f"  journal = {{{journal}}},\n"
            f"  year = {{{year}}},\n"
            f"{doi_line}"
            f"}}"
        )
    return "\n\n".join(entries) + "\n"


class ManuscriptComposer:
    """Composes bilingual IMRaD/Systematic/Monograph manuscripts in MD + LaTeX + BibTeX + DOCX."""

    def __init__(self, llm_router: Optional[LLMRouter] = None):
        self.llm_router = llm_router

    def compose(
        self,
        run_id: str,
        out_dir: Path,
        topic: str,
        spec: Optional[ManuscriptSpec] = None,
        evidence: Optional[EvidencePackage] = None,
        synthesis: Optional[ResearchSynthesis] = None,
        experiment: Optional[ExperimentRun] = None,
        evolution: Optional[EvolutionRunResult] = None,
        knowledge_link: Optional[KnowledgeLinkReport] = None,
    ) -> ManuscriptOutput:
        out_dir.mkdir(parents=True, exist_ok=True)
        ms = spec or ManuscriptSpec()
        papers = evidence.papers if evidence else []
        title_en = f"Closed-Loop Evidence Synthesis, Simulation, and Algorithmic Discovery for {topic}"
        title_zh = f"面向“{topic}”的闭环循证文献研究、科学模拟、算法进化与知识图谱实证研究"

        cite_tags = ", ".join(f"[{p.id}]" for p in papers[:4]) or ""
        grade_str = f"GRADE {evidence.grade.grade} ({evidence.grade.score}/10)" if evidence else "N/A"

        sections: List[str] = [
            f"# {title_en}\n# {title_zh}",
            f"> **Run ID**: `{run_id}` | **Type**: `{ms.paper_type}` | **Style**: `{ms.latex_style}` | **Evidence Rating**: `{grade_str}`",
            "## Abstract / 摘要",
            f"**English:** This study investigates **{topic}** through an integrated computational pipeline combining multi-source literature screening ({len(papers)} included works {cite_tags}), formal contradiction and research-gap synthesis, sandboxed statistical simulation, multi-island MAP-Elites algorithm evolution, and hybrid Personalized PageRank linking with a Sovereign Knowledge Base.",
            f"**中文：** 本研究围绕**“{topic}”**构建端到端计算科研闭环：整合多源循证检索（纳入 {len(papers)} 篇文献 {cite_tags}）、冲突与研究缺口挖掘、AST 沙箱科学模拟统计检验、多岛 MAP-Elites 算法进化以及基于个性化 PageRank 的本地主权知识库关联。",
            "## 1. Introduction & Background / 引言与研究背景",
            (evidence.summary_en if evidence and evidence.summary_en else f"Scientific inquiry in {topic} demands reproducible evidence grounding and quantitative verification {cite_tags}."),
            (evidence.summary_zh if evidence and evidence.summary_zh else f"在“{topic}”领域，亟需建立可复现的循证文献核验与定量实验验证体系 {cite_tags}。"),
            "## 2. Literature Screening, GRADE & Contradictions / 系统文献研究与证据冲突分析",
        ]

        if evidence:
            pc = evidence.prisma_counts
            sections.append(
                f"- **PRISMA Funnel / 筛选漏斗**: Identified `{pc.identified}` → Deduplicated `{pc.deduplicated}` → Included `{pc.included}`.\n"
                f"- **GRADE Assessment / 证据评级**: {evidence.grade.reasoning_en}\n- **中文评级说明**: {evidence.grade.reasoning_zh}"
            )
        if papers:
            tbl = [
                "| ID | Title | Journal / Year | Type | Citations | Sources |",
                "|---|---|---|---|---:|---|",
            ]
            for p in papers[:10]:
                tbl.append(
                    f"| `{p.id}` | {p.title[:65]} | {p.journal or 'Archive'} ({p.year or 'N/A'}) | {p.study_type} | {p.cited_by} | {', '.join(p.source_origins)} |"
                )
            sections.append("\n".join(tbl))

        if synthesis and synthesis.contradictions:
            sections.append("### Empirical Contradictions / 跨文献实证冲突")
            for con in synthesis.contradictions:
                sections.append(f"- **{con.topic_metric}** (`[{con.paper_a_id}]` vs `[{con.paper_b_id}]`, `{con.severity}`): {con.explanation_en} / {con.explanation_zh}")

        sections.append("## 3. Sovereign Knowledge Linking & Multi-Hop Bridges / 本地主权知识库链接与多跳图谱关联")
        if knowledge_link:
            sections.append(
                f"- **KB Federation Status**: `available={knowledge_link.kb_available}`, Matched KB Concepts `{len(knowledge_link.matched_kb_concepts)}`, "
                f"Triples `{len(knowledge_link.matched_triples)}`, Gold Axioms `{len(knowledge_link.gold_edges)}`, "
                f"Communities `{len(knowledge_link.communities)}`."
            )
            if knowledge_link.wiki_links:
                sections.append(f"- **Bidirectional WikiLinks**: {' · '.join(knowledge_link.wiki_links[:6])}")
            if knowledge_link.ppr_multihop_bridges:
                b_lines = ["| Node | Type | PPR Score | Hop Distance |", "|---|---|---:|---:|"]
                for b in knowledge_link.ppr_multihop_bridges[:6]:
                    b_lines.append(f"| {b['label']} | {b['node_type']} | {b['ppr_score']:.5f} | {b['hop_distance']} |")
                sections.append("\n".join(b_lines))
            if knowledge_link.mermaid_diagram:
                sections.append(f"```mermaid\n{knowledge_link.mermaid_diagram}\n```")

        sections.append("## 4. Research Gaps & Falsifiable Hypotheses / 研究缺口与可证伪假设")
        if synthesis:
            for g in synthesis.gaps:
                refs = " ".join(f"[{pid}]" for pid in g.supporting_paper_ids)
                sections.append(f"- **{g.gap_id} ({g.category}) — {g.title_en} / {g.title_zh}**: {g.description_en} {refs}")
            for h in synthesis.hypotheses:
                refs = " ".join(f"[{pid}]" for pid in h.grounding_paper_ids)
                sections.append(f"- **{h.hypothesis_id}: {h.title_en} / {h.title_zh}** — {h.statement_en} (Metric: `{h.primary_metric}`, {refs})")

        sections.append("## 5. Scientific Simulation & Statistical Verification / 科学实验模拟与统计检验")
        if experiment:
            sections.append(f"- **Template**: `{experiment.resolved_template}` | **Winning Branch**: `{experiment.winning_branch_id}`\n- {experiment.summary_en}\n- {experiment.summary_zh}")
            b_tbl = ["| Branch | Primary Metric | Baseline | Delta | Elapsed (s) |", "|---|---:|---:|---:|---:|"]
            for b in experiment.branches:
                b_tbl.append(
                    f"| {b.label} | {b.metrics.get('primary_metric', 0):.4f} | {b.metrics.get('baseline_metric', 0):.4f} | {b.metrics.get('delta', 0):+.4f} | {b.elapsed_s:.3f} |"
                )
            sections.append("\n".join(b_tbl))
            for st in experiment.stats:
                sections.append(
                    f"- **{st.test_name}**: statistic={st.statistic:.4f}, p={st.p_value:.5f}, FDR q={st.fdr_q_value}, "
                    f"{st.effect_size_name}={st.effect_size:.4f}, 95% CI=[{st.ci_low}, {st.ci_high}]."
                )

        sections.append("## 6. Algorithm Evolution & Pareto Optimization / 算法进化与帕累托优化")
        if evolution:
            sections.append(f"- {evolution.summary_en}\n- {evolution.summary_zh}")
            sections.append(f"```python\n{evolution.best_candidate.code}\n```")

        sections.append("## 7. Discussion, Limitations & Conclusion / 讨论、局限性与结论")
        sections.append(
            "Integrating structured multi-source literature grounding with sandboxed statistical simulation and MAP-Elites algorithm "
            "evolution provides verifiable quantitative hypotheses while maintaining full citation traceability. Limitations include reliance "
            "on parameterized simulation models prior to prospective real-world validation."
        )
        sections.append(
            "将多源循证文献检索、沙箱统计检验、MAP-Elites 算法进化与本地主权知识库图谱融合，实现了“假设—验证—进化—沉淀”的闭环；未来需结合真实前瞻性数据进行外部泛化验证。"
        )

        sections.append("## 8. References / 参考文献")
        for p in papers:
            au = ", ".join(p.authors[:3]) if p.authors else "Unknown"
            doi_str = f" DOI: `{p.doi}`." if p.doi else ""
            sections.append(f"- `[{p.id}]` {au} ({p.year or 'N/A'}). *{p.title}*. {p.journal or 'Archive'}.{doi_str}")

        raw_md = "\n\n".join(sections) + "\n"
        cleaned_md, stylometry_report = audit_and_clean_stylometry(raw_md, apply_cleanup=ms.apply_deai)

        bib_text = build_bibtex(papers)
        tex_text = self._build_latex(title_en, title_zh, ms, papers, evidence, experiment, evolution)

        md_path = atomic_write_text(out_dir / "manuscript.md", cleaned_md)
        tex_path = atomic_write_text(out_dir / "manuscript.tex", tex_text)
        bib_path = atomic_write_text(out_dir / "references.bib", bib_text)
        docx_path = out_dir / "manuscript.docx"
        self._build_docx(
            docx_path, title_en, title_zh, run_id, papers, evidence, synthesis, experiment, evolution, knowledge_link
        )

        citation_audit = audit_citations(cleaned_md, [p.id for p in papers])
        review = peer_review_manuscript(cleaned_md, evidence, experiment, evolution, knowledge_link, citation_audit)
        word_count = len(re.findall(r"\S+", cleaned_md))

        return ManuscriptOutput(
            run_id=run_id,
            title_en=title_en,
            title_zh=title_zh,
            md_path=str(md_path),
            tex_path=str(tex_path),
            bib_path=str(bib_path),
            docx_path=str(docx_path),
            word_count=word_count,
            stylometry=stylometry_report,
            citation_audit=citation_audit,
            review=review,
        )

    @staticmethod
    def _build_latex(
        title_en: str,
        title_zh: str,
        ms: ManuscriptSpec,
        papers: List[PaperRecord],
        evidence: Optional[EvidencePackage],
        experiment: Optional[ExperimentRun],
        evolution: Optional[EvolutionRunResult],
    ) -> str:
        cites = ",".join(p.id for p in papers[:4])
        cite_cmd = f"\\cite{{{cites}}}" if cites else ""
        sim_line = _latex_escape(experiment.summary_en) if experiment else "Simulation not attached."
        evo_line = _latex_escape(evolution.summary_en) if evolution else "Evolution not attached."
        grade_line = _latex_escape(evidence.grade.reasoning_en) if evidence else "N/A"
        return (
            "\\documentclass[11pt,a4paper]{article}\n"
            "\\usepackage[UTF8]{ctex}\n"
            "\\usepackage{amsmath,amssymb,booktabs,graphicx,hyperref}\n"
            f"% Style preset: {ms.latex_style}\n"
            f"\\title{{{_latex_escape(title_en)} \\\\ \\large {_latex_escape(title_zh)}}}\n"
            "\\author{via54SciForge Autonomous Research Suite}\n"
            "\\date{\\today}\n"
            "\\begin{document}\n"
            "\\maketitle\n"
            "\\begin{abstract}\n"
            f"This bilingual manuscript synthesizes evidence across {len(papers)} curated works {cite_cmd}. "
            f"{grade_line}\n"
            "\\end{abstract}\n"
            "\\section{Introduction / 引言}\n"
            f"Multi-source evidence integration and hypothesis verification {cite_cmd}.\n"
            "\\section{Simulation Results / 实验模拟结果}\n"
            f"{sim_line}\n"
            "\\section{Algorithm Evolution / 算法进化结果}\n"
            f"{evo_line}\n"
            "\\bibliographystyle{plain}\n"
            "\\bibliography{references}\n"
            "\\end{document}\n"
        )

    @staticmethod
    def _build_docx(
        docx_path: Path,
        title_en: str,
        title_zh: str,
        run_id: str,
        papers: List[PaperRecord],
        evidence: Optional[EvidencePackage],
        synthesis: Optional[ResearchSynthesis],
        experiment: Optional[ExperimentRun],
        evolution: Optional[EvolutionRunResult],
        knowledge_link: Optional[KnowledgeLinkReport],
    ) -> None:
        doc = Document()
        normal_style = doc.styles["Normal"]
        normal_style.font.name = "Microsoft YaHei"
        normal_style.font.size = Pt(10.5)

        h = doc.add_heading(title_en, level=0)
        h.runs[0].font.color.rgb = RGBColor(0x1B, 0x36, 0x5D)
        p_zh = doc.add_paragraph(title_zh)
        p_zh.runs[0].bold = True
        doc.add_paragraph(f"Run ID: {run_id} | Generated by via54SciForge")

        doc.add_heading("1. Abstract / 摘要", level=1)
        if evidence:
            doc.add_paragraph(evidence.summary_en or evidence.grade.reasoning_en)
            doc.add_paragraph(evidence.summary_zh or evidence.grade.reasoning_zh)

        doc.add_heading("2. Literature & Synthesis / 文献与研究假设", level=1)
        if synthesis:
            doc.add_paragraph(synthesis.synthesis_en)
            doc.add_paragraph(synthesis.synthesis_zh)
            for hyp in synthesis.hypotheses:
                doc.add_paragraph(f"[{hyp.hypothesis_id}] {hyp.title_en} / {hyp.title_zh}: {hyp.statement_en}", style="List Bullet")

        if experiment:
            doc.add_heading("3. Scientific Simulation & Statistics / 实验模拟与统计检验", level=1)
            doc.add_paragraph(experiment.summary_en)
            doc.add_paragraph(experiment.summary_zh)
            tbl = doc.add_table(rows=1, cols=4)
            tbl.style = "Light Shading Accent 1"
            hdr = tbl.rows[0].cells
            hdr[0].text, hdr[1].text, hdr[2].text, hdr[3].text = "Branch", "Primary", "Baseline", "Delta"
            for b in experiment.branches:
                row = tbl.add_row().cells
                row[0].text = b.label
                row[1].text = f"{b.metrics.get('primary_metric', 0):.4f}"
                row[2].text = f"{b.metrics.get('baseline_metric', 0):.4f}"
                row[3].text = f"{b.metrics.get('delta', 0):+.4f}"
            for fig in experiment.figure_paths:
                fp = Path(fig)
                if fp.exists():
                    doc.add_picture(str(fp), width=Inches(5.8))

        if evolution:
            doc.add_heading("4. Algorithm Evolution / 算法进化优化", level=1)
            doc.add_paragraph(evolution.summary_en)
            doc.add_paragraph(evolution.summary_zh)
            if evolution.chart_path and Path(evolution.chart_path).exists():
                doc.add_picture(evolution.chart_path, width=Inches(5.8))

        if knowledge_link:
            doc.add_heading("5. Sovereign Knowledge Base Linking / 本地知识库关联", level=1)
            doc.add_paragraph(
                f"Matched Concepts: {len(knowledge_link.matched_kb_concepts)}, "
                f"Triples: {len(knowledge_link.matched_triples)}, Gold Axioms: {len(knowledge_link.gold_edges)}"
            )
            if knowledge_link.wiki_links:
                doc.add_paragraph("WikiLinks: " + ", ".join(knowledge_link.wiki_links[:6]))

        doc.add_heading("6. References / 参考文献", level=1)
        for p in papers:
            au = ", ".join(p.authors[:3]) if p.authors else "Unknown"
            doc.add_paragraph(f"[{p.id}] {au} ({p.year or 'N/A'}). {p.title}. {p.journal}. DOI: {p.doi}")

        doc.save(str(docx_path))
