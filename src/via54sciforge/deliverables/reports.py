"""Bilingual derivative report generator producing Markdown, interactive self-contained HTML, and Word (.docx)."""

from __future__ import annotations

import base64
import html
from pathlib import Path
from typing import Dict, List, Literal, Optional

from docx import Document
from docx.shared import Inches, Pt, RGBColor

from via54sciforge.core.models import (
    DerivativeReportOutput,
    EvidencePackage,
    EvolutionRunResult,
    ExperimentRun,
    KnowledgeLinkReport,
    ManuscriptOutput,
    ResearchSynthesis,
)
from via54sciforge.core.storage import atomic_write_text

ReportType = Literal["executive_brief", "deep_research", "evidence_matrix", "translation_brief"]

REPORT_TITLES: Dict[str, tuple[str, str]] = {
    "executive_brief": ("Executive Decision Brief", "科研决策高管简报"),
    "deep_research": ("Comprehensive Deep Research Report", "深度科研分析综合报告"),
    "evidence_matrix": ("Evidence Provenance & Contradiction Audit Matrix", "循证冲突与应证审计矩阵报告"),
    "translation_brief": ("Translational & Strategic Roadmap Brief", "临床与产业转化战略路线简报"),
}


def _b64_img(img_path: str) -> str:
    p = Path(img_path)
    if not p.exists():
        return ""
    raw = p.read_bytes()
    return f"data:image/png;base64,{base64.b64encode(raw).decode('ascii')}"


class DerivativeReportGenerator:
    """Generates bilingual MD, interactive HTML dashboard, and DOCX derivative reports."""

    def generate(
        self,
        run_id: str,
        out_dir: Path,
        topic: str,
        report_type: ReportType = "deep_research",
        evidence: Optional[EvidencePackage] = None,
        synthesis: Optional[ResearchSynthesis] = None,
        experiment: Optional[ExperimentRun] = None,
        evolution: Optional[EvolutionRunResult] = None,
        knowledge_link: Optional[KnowledgeLinkReport] = None,
        manuscript: Optional[ManuscriptOutput] = None,
        extra_charts: Optional[List[str]] = None,
    ) -> DerivativeReportOutput:
        out_dir.mkdir(parents=True, exist_ok=True)
        en_lbl, zh_lbl = REPORT_TITLES.get(report_type, ("Research Report", "研究报告"))

        papers = evidence.papers if evidence else []
        grade = evidence.grade if evidence else None
        charts = list(extra_charts or [])
        if experiment:
            charts.extend(experiment.figure_paths)
        if evolution and evolution.chart_path:
            charts.append(evolution.chart_path)
        dedup_charts = []
        for c in charts:
            if c and c not in dedup_charts and Path(c).exists():
                dedup_charts.append(c)

        md_text = self._build_markdown(
            run_id, topic, report_type, en_lbl, zh_lbl, evidence, synthesis, experiment, evolution, knowledge_link, manuscript
        )
        html_text = self._build_html(
            run_id, topic, en_lbl, zh_lbl, evidence, synthesis, experiment, evolution, knowledge_link, manuscript, dedup_charts
        )
        md_path = atomic_write_text(out_dir / f"{report_type}.md", md_text)
        html_path = atomic_write_text(out_dir / f"{report_type}.html", html_text)
        docx_path = out_dir / f"{report_type}.docx"
        self._build_docx(
            docx_path, run_id, topic, en_lbl, zh_lbl, evidence, synthesis, experiment, evolution, knowledge_link, dedup_charts
        )

        return DerivativeReportOutput(
            run_id=run_id,
            report_type=report_type,
            md_path=str(md_path),
            html_path=str(html_path),
            docx_path=str(docx_path),
        )

    @staticmethod
    def _build_markdown(
        run_id: str,
        topic: str,
        report_type: str,
        en_lbl: str,
        zh_lbl: str,
        evidence: Optional[EvidencePackage],
        synthesis: Optional[ResearchSynthesis],
        experiment: Optional[ExperimentRun],
        evolution: Optional[EvolutionRunResult],
        knowledge_link: Optional[KnowledgeLinkReport],
        manuscript: Optional[ManuscriptOutput],
    ) -> str:
        papers = evidence.papers if evidence else []
        lines = [
            f"# {en_lbl}: {topic}",
            f"# {zh_lbl}：{topic}",
            f"- **Run ID**: `{run_id}` | **Report Type**: `{report_type}`",
            "",
            "## 1. Executive Synthesis / 核心结论摘要",
            f"- **English**: {synthesis.synthesis_en if synthesis else (evidence.summary_en if evidence else topic)}",
            f"- **中文**: {synthesis.synthesis_zh if synthesis else (evidence.summary_zh if evidence else topic)}",
            "",
            "## 2. Quantitative Scorecard / 核心量化指标",
            "| Dimension | Metric Value | Notes |",
            "|---|---|---|",
            f"| Literature Grounding | {len(papers)} papers | GRADE {evidence.grade.grade if evidence else 'N/A'} ({evidence.grade.score if evidence else 0}/10) |",
            f"| Simulation Experiment | {experiment.resolved_template if experiment else 'N/A'} | Delta {experiment.branches[0].metrics.get('delta', 0):+.4f} |" if experiment and experiment.branches else "| Simulation Experiment | N/A | - |",
            f"| Algorithm Evolution | {evolution.improvement_pct if evolution else 0:+.2f}% | Best fitness {evolution.best_candidate.fitness if evolution else 0:.4f} |",
            f"| Sovereign KB Links | {len(knowledge_link.matched_kb_concepts) if knowledge_link else 0} concepts | {len(knowledge_link.gold_edges) if knowledge_link else 0} gold edges |",
            f"| Citation Grounding | {manuscript.citation_audit.grounding_rate * 100 if manuscript else 100:.1f}% | Peer Review {manuscript.review.overall_score if manuscript else 0:.2f}/10 |",
            "",
            "## 3. Evidence & Contradiction Matrix / 证据与冲突矩阵",
        ]
        for p in papers[:10]:
            lines.append(f"- **[{p.id}]** ({p.year}, {p.study_type}, cites={p.cited_by}) {p.title} — DOI: `{p.doi or 'N/A'}`")
        if synthesis and synthesis.contradictions:
            lines.append("\n### Contradictions / 实证冲突")
            for c in synthesis.contradictions:
                lines.append(f"- `{c.paper_a_id}` vs `{c.paper_b_id}` ({c.severity}): {c.explanation_en} / {c.explanation_zh}")
        if knowledge_link and knowledge_link.wiki_links:
            lines.append("\n## 4. Knowledge Graph WikiLinks / 本地知识库双向链接")
            lines.append(" · ".join(knowledge_link.wiki_links))
        return "\n".join(lines) + "\n"

    @staticmethod
    def _build_html(
        run_id: str,
        topic: str,
        en_lbl: str,
        zh_lbl: str,
        evidence: Optional[EvidencePackage],
        synthesis: Optional[ResearchSynthesis],
        experiment: Optional[ExperimentRun],
        evolution: Optional[EvolutionRunResult],
        knowledge_link: Optional[KnowledgeLinkReport],
        manuscript: Optional[ManuscriptOutput],
        charts: List[str],
    ) -> str:
        papers = evidence.papers if evidence else []
        grade_badge = f"GRADE {evidence.grade.grade} ({evidence.grade.score}/10)" if evidence else "N/A"
        sim_delta = f"{experiment.branches[0].metrics.get('delta', 0):+.4f}" if experiment and experiment.branches else "0.0000"
        evo_gain = f"{evolution.improvement_pct:+.2f}%" if evolution else "0.0%"
        kb_cnt = len(knowledge_link.matched_kb_concepts) if knowledge_link else 0
        grounding = f"{manuscript.citation_audit.grounding_rate * 100:.1f}%" if manuscript else "100.0%"

        rows_html = []
        for p in papers:
            rows_html.append(
                f"<tr><td><code>{html.escape(p.id)}</code></td>"
                f"<td>{html.escape(p.title)}</td>"
                f"<td>{html.escape(p.journal or 'Archive')} ({p.year or 'N/A'})</td>"
                f"<td><span class='tag'>{html.escape(p.study_type)}</span></td>"
                f"<td>{p.cited_by}</td>"
                f"<td>{html.escape(', '.join(p.source_origins))}</td></tr>"
            )

        charts_html = []
        for c in charts:
            uri = _b64_img(c)
            if uri:
                charts_html.append(f"<div class='chart-card'><img src='{uri}' alt='{html.escape(Path(c).stem)}'/></div>")

        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{html.escape(en_lbl)} — {html.escape(topic)}</title>
<style>
  body {{ font-family: 'Microsoft YaHei', 'Segoe UI', sans-serif; background: #f4f6fa; color: #1f2937; margin: 0; padding: 24px; }}
  .wrap {{ max-width: 1180px; margin: auto; }}
  .hero {{ background: linear-gradient(135deg, #1b365d 0%, #0f766e 100%); color: #fff; padding: 28px 32px; border-radius: 14px; margin-bottom: 22px; }}
  .hero h1 {{ margin: 0 0 6px 0; font-size: 24px; }}
  .hero h2 {{ margin: 0 0 12px 0; font-size: 18px; font-weight: 400; opacity: 0.92; }}
  .kpis {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 14px; margin-bottom: 22px; }}
  .kpi {{ background: #fff; border-radius: 10px; padding: 16px 18px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); border-left: 4px solid #0f766e; }}
  .kpi .lbl {{ font-size: 12px; color: #6b7280; text-transform: uppercase; }}
  .kpi .val {{ font-size: 22px; font-weight: 700; color: #1b365d; margin-top: 4px; }}
  .card {{ background: #fff; border-radius: 10px; padding: 20px 24px; margin-bottom: 18px; box-shadow: 0 2px 8px rgba(0,0,0,0.05); }}
  .card h3 {{ margin-top: 0; color: #1b365d; border-bottom: 1px solid #e5e7eb; padding-bottom: 8px; }}
  .charts {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(460px, 1fr)); gap: 16px; }}
  .chart-card img {{ width: 100%; border-radius: 8px; border: 1px solid #e5e7eb; }}
  input.filter {{ width: 100%; max-width: 380px; padding: 8px 12px; margin-bottom: 12px; border: 1px solid #d1d5db; border-radius: 6px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13.5px; }}
  th, td {{ padding: 9px 10px; border-bottom: 1px solid #e5e7eb; text-align: left; }}
  th {{ background: #f9fafb; color: #1b365d; }}
  .tag {{ background: #e0f2fe; color: #0369a1; padding: 2px 8px; border-radius: 12px; font-size: 12px; }}
</style>
</head>
<body>
<div class="wrap">
  <div class="hero">
    <h1>{html.escape(en_lbl)} — {html.escape(topic)}</h1>
    <h2>{html.escape(zh_lbl)}：{html.escape(topic)}</h2>
    <div>Run ID: <code>{html.escape(run_id)}</code> · Powered by <strong>via54SciForge</strong></div>
  </div>
  <div class="kpis">
    <div class="kpi"><div class="lbl">Papers & GRADE / 文献评级</div><div class="val">{len(papers)} · {html.escape(grade_badge)}</div></div>
    <div class="kpi"><div class="lbl">Simulation Delta / 实验净增益</div><div class="val">{html.escape(sim_delta)}</div></div>
    <div class="kpi"><div class="lbl">Evolution Gain / 算法进化提升</div><div class="val">{html.escape(evo_gain)}</div></div>
    <div class="kpi"><div class="lbl">Sovereign KB Concepts / 知识库关联</div><div class="val">{kb_cnt}</div></div>
    <div class="kpi"><div class="lbl">Citation Grounding / 引文实证率</div><div class="val">{html.escape(grounding)}</div></div>
  </div>
  <div class="card">
    <h3>Executive Synthesis / 综合研究摘要</h3>
    <p><strong>EN:</strong> {html.escape(synthesis.synthesis_en if synthesis else '')}</p>
    <p><strong>ZH:</strong> {html.escape(synthesis.synthesis_zh if synthesis else '')}</p>
  </div>
  <div class="card">
    <h3>Scientific Visualizations / 科学实验与进化图表</h3>
    <div class="charts">{''.join(charts_html) or '<p>No figures generated.</p>'}</div>
  </div>
  <div class="card">
    <h3>Evidence Matrix / 纳入文献证据矩阵</h3>
    <input class="filter" type="text" placeholder="Filter papers by title, venue, or type..." oninput="filterRows(this.value)"/>
    <table id="evTable">
      <thead><tr><th>ID</th><th>Title</th><th>Venue / Year</th><th>Type</th><th>Citations</th><th>Sources</th></tr></thead>
      <tbody>{''.join(rows_html)}</tbody>
    </table>
  </div>
</div>
<script>
function filterRows(q) {{
  const term = q.toLowerCase();
  for (const row of document.querySelectorAll('#evTable tbody tr')) {{
    row.style.display = row.innerText.toLowerCase().includes(term) ? '' : 'none';
  }}
}}
</script>
</body>
</html>"""

    @staticmethod
    def _build_docx(
        docx_path: Path,
        run_id: str,
        topic: str,
        en_lbl: str,
        zh_lbl: str,
        evidence: Optional[EvidencePackage],
        synthesis: Optional[ResearchSynthesis],
        experiment: Optional[ExperimentRun],
        evolution: Optional[EvolutionRunResult],
        knowledge_link: Optional[KnowledgeLinkReport],
        charts: List[str],
    ) -> None:
        doc = Document()
        doc.styles["Normal"].font.name = "Microsoft YaHei"
        doc.styles["Normal"].font.size = Pt(10.5)
        h = doc.add_heading(f"{en_lbl}: {topic}", level=0)
        h.runs[0].font.color.rgb = RGBColor(0x1B, 0x36, 0x5D)
        doc.add_paragraph(f"{zh_lbl}：{topic} | Run ID: {run_id}")

        if synthesis:
            doc.add_heading("1. Synthesis / 研究综合", level=1)
            doc.add_paragraph(synthesis.synthesis_en)
            doc.add_paragraph(synthesis.synthesis_zh)
        if evidence and evidence.papers:
            doc.add_heading("2. Evidence Matrix / 文献证据矩阵", level=1)
            tbl = doc.add_table(rows=1, cols=4)
            tbl.style = "Light Shading Accent 1"
            hdr = tbl.rows[0].cells
            hdr[0].text, hdr[1].text, hdr[2].text, hdr[3].text = "ID", "Title", "Year", "Citations"
            for p in evidence.papers[:8]:
                r = tbl.add_row().cells
                r[0].text, r[1].text, r[2].text, r[3].text = p.id, p.title[:65], str(p.year), str(p.cited_by)
        if experiment:
            doc.add_heading("3. Simulation / 实验模拟", level=1)
            doc.add_paragraph(experiment.summary_en)
            doc.add_paragraph(experiment.summary_zh)
        if evolution:
            doc.add_heading("4. Algorithm Evolution / 算法进化", level=1)
            doc.add_paragraph(evolution.summary_en)
            doc.add_paragraph(evolution.summary_zh)
        if knowledge_link:
            doc.add_heading("5. Sovereign KB Linking / 知识关联", level=1)
            doc.add_paragraph(f"Matched KB Concepts: {len(knowledge_link.matched_kb_concepts)}; Gold Edges: {len(knowledge_link.gold_edges)}")
        for c in charts:
            if Path(c).exists():
                doc.add_picture(c, width=Inches(5.6))
        doc.save(str(docx_path))
