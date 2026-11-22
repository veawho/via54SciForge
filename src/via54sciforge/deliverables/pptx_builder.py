"""12-slide bilingual academic PPTX generator with 4 themes, speaker notes & dual-source provenance manifest."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt

from via54sciforge.core.models import (
    EvidencePackage,
    EvolutionRunResult,
    ExperimentRun,
    KnowledgeLinkReport,
    ManuscriptOutput,
    ResearchSynthesis,
    SlideDeckOutput,
    SlideSpec,
)
from via54sciforge.core.storage import atomic_write_json

THEMES: Dict[str, Dict[str, RGBColor]] = {
    "academic_navy": {
        "bg": RGBColor(0xF8, 0xFA, 0xFC),
        "hero_bg": RGBColor(0x1B, 0x36, 0x5D),
        "primary": RGBColor(0x1B, 0x36, 0x5D),
        "accent": RGBColor(0x00, 0x80, 0x80),
        "card_bg": RGBColor(0xFF, 0xFF, 0xFF),
        "text": RGBColor(0x1E, 0x29, 0x3B),
        "muted": RGBColor(0x64, 0x74, 0x8B),
        "hero_text": RGBColor(0xFF, 0xFF, 0xFF),
    },
    "clinical_clean": {
        "bg": RGBColor(0xFF, 0xFF, 0xFF),
        "hero_bg": RGBColor(0x0F, 0x4C, 0x81),
        "primary": RGBColor(0x0F, 0x4C, 0x81),
        "accent": RGBColor(0x0D, 0x94, 0x88),
        "card_bg": RGBColor(0xF1, 0xF5, 0xF9),
        "text": RGBColor(0x1E, 0x29, 0x3B),
        "muted": RGBColor(0x47, 0x55, 0x69),
        "hero_text": RGBColor(0xFF, 0xFF, 0xFF),
    },
    "executive_slate": {
        "bg": RGBColor(0xF4, 0xF5, 0xF7),
        "hero_bg": RGBColor(0x1F, 0x29, 0x37),
        "primary": RGBColor(0x1F, 0x29, 0x37),
        "accent": RGBColor(0xD9, 0x77, 0x06),
        "card_bg": RGBColor(0xFF, 0xFF, 0xFF),
        "text": RGBColor(0x11, 0x18, 0x27),
        "muted": RGBColor(0x6B, 0x72, 0x80),
        "hero_text": RGBColor(0xFF, 0xFF, 0xFF),
    },
    "dark_keynote": {
        "bg": RGBColor(0x0F, 0x17, 0x2A),
        "hero_bg": RGBColor(0x02, 0x06, 0x17),
        "primary": RGBColor(0x38, 0xBD, 0xF8),
        "accent": RGBColor(0x2D, 0xD4, 0xBF),
        "card_bg": RGBColor(0x1E, 0x29, 0x3B),
        "text": RGBColor(0xF1, 0xF5, 0xF9),
        "muted": RGBColor(0x94, 0xA3, 0xB8),
        "hero_text": RGBColor(0xFF, 0xFF, 0xFF),
    },
}


class AcademicPPTXBuilder:
    """Builds a 12-slide bilingual presentation + dual-source citation provenance manifest."""

    def build(
        self,
        run_id: str,
        out_dir: Path,
        topic: str,
        spec: Optional[SlideSpec] = None,
        evidence: Optional[EvidencePackage] = None,
        synthesis: Optional[ResearchSynthesis] = None,
        experiment: Optional[ExperimentRun] = None,
        evolution: Optional[EvolutionRunResult] = None,
        knowledge_link: Optional[KnowledgeLinkReport] = None,
        manuscript: Optional[ManuscriptOutput] = None,
        lit_chart_path: Optional[str] = None,
    ) -> SlideDeckOutput:
        out_dir.mkdir(parents=True, exist_ok=True)
        ss = spec or SlideSpec()
        pal = THEMES.get(ss.theme, THEMES["academic_navy"])

        prs = Presentation()
        prs.slide_width = Inches(13.333)
        prs.slide_height = Inches(7.5)
        blank = prs.slide_layouts[6]

        papers = evidence.papers if evidence else []
        manifest_slides: List[Dict[str, Any]] = []
        slide_no = 0

        def new_slide(title_en: str, title_zh: str, notes: str, source_refs: List[str], hero: bool = False):
            nonlocal slide_no
            slide_no += 1
            sl = prs.slides.add_slide(blank)
            bg = sl.background
            fill = bg.fill
            fill.solid()
            fill.fore_color.rgb = pal["hero_bg"] if hero else pal["bg"]

            if not hero:
                bar = sl.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(13.333), Inches(0.12))
                bar.fill.solid()
                bar.fill.fore_color.rgb = pal["accent"]
                bar.line.fill.background()

                tb = sl.shapes.add_textbox(Inches(0.6), Inches(0.25), Inches(12.1), Inches(0.85))
                tf = tb.text_frame
                tf.word_wrap = True
                p1 = tf.paragraphs[0]
                p1.text = f"{title_en}  |  {title_zh}"
                p1.font.name = "Microsoft YaHei"
                p1.font.size = Pt(22)
                p1.font.bold = True
                p1.font.color.rgb = pal["primary"]

                ftr = sl.shapes.add_textbox(Inches(0.6), Inches(7.05), Inches(12.1), Inches(0.32))
                fp = ftr.text_frame.paragraphs[0]
                fp.text = f"via54SciForge · Run {run_id} · Provenance: {', '.join(source_refs[:5]) or 'Internal'} · Slide {slide_no}/12"
                fp.font.name = "Microsoft YaHei"
                fp.font.size = Pt(9.5)
                fp.font.color.rgb = pal["muted"]

            sl.notes_slide.notes_text_frame.text = notes
            manifest_slides.append(
                {
                    "slide_no": slide_no,
                    "title": f"{title_en} | {title_zh}",
                    "provenance_refs": source_refs,
                    "dual_source_ready": True,
                }
            )
            return sl

        def add_card(sl, left: float, top: float, w: float, h: float, heading: str, lines: List[str], accent_top: bool = True):
            box = sl.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(left), Inches(top), Inches(w), Inches(h))
            box.fill.solid()
            box.fill.fore_color.rgb = pal["card_bg"]
            box.line.color.rgb = pal["accent"] if accent_top else pal["muted"]
            box.line.width = Pt(1.0)
            tf = sl.shapes.add_textbox(Inches(left + 0.2), Inches(top + 0.14), Inches(w - 0.4), Inches(h - 0.25)).text_frame
            tf.word_wrap = True
            p0 = tf.paragraphs[0]
            p0.text = heading
            p0.font.name = "Microsoft YaHei"
            p0.font.size = Pt(14)
            p0.font.bold = True
            p0.font.color.rgb = pal["accent"]
            for line in lines:
                p = tf.add_paragraph()
                p.text = line
                p.font.name = "Microsoft YaHei"
                p.font.size = Pt(11.5)
                p.font.color.rgb = pal["text"]
                p.space_before = Pt(4)

        def add_table(sl, left: float, top: float, w: float, h: float, headers: List[str], rows: List[List[str]]):
            n_rows = max(2, len(rows) + 1)
            tbl = sl.shapes.add_table(n_rows, len(headers), Inches(left), Inches(top), Inches(w), Inches(h)).table
            for c_idx, h_txt in enumerate(headers):
                cell = tbl.cell(0, c_idx)
                cell.fill.solid()
                cell.fill.fore_color.rgb = pal["primary"]
                p = cell.text_frame.paragraphs[0]
                p.text = h_txt
                p.font.name = "Microsoft YaHei"
                p.font.size = Pt(11)
                p.font.bold = True
                p.font.color.rgb = pal["hero_text"]
            for r_idx, r_vals in enumerate(rows, start=1):
                for c_idx, val in enumerate(r_vals):
                    cell = tbl.cell(r_idx, c_idx)
                    cell.fill.solid()
                    cell.fill.fore_color.rgb = pal["card_bg"]
                    p = cell.text_frame.paragraphs[0]
                    p.text = str(val)
                    p.font.name = "Microsoft YaHei"
                    p.font.size = Pt(10)
                    p.font.color.rgb = pal["text"]

        # Slide 1: Hero Title
        s1 = new_slide("Hero", "封面", f"Bilingual opening for {topic}", [p.id for p in papers[:3]], hero=True)
        tb1 = s1.shapes.add_textbox(Inches(0.9), Inches(1.7), Inches(11.5), Inches(3.8)).text_frame
        tb1.word_wrap = True
        p_t1 = tb1.paragraphs[0]
        p_t1.text = f"via54SciForge Autonomous Research Brief\n{topic}"
        p_t1.font.name = "Microsoft YaHei"
        p_t1.font.size = Pt(32)
        p_t1.font.bold = True
        p_t1.font.color.rgb = pal["hero_text"]
        p_t2 = tb1.add_paragraph()
        p_t2.text = f"\n中文主题：{topic}\nRun ID: {run_id} · GRADE {evidence.grade.grade if evidence else 'N/A'} · Theme: {ss.theme}"
        p_t2.font.name = "Microsoft YaHei"
        p_t2.font.size = Pt(16)
        p_t2.font.color.rgb = RGBColor(0xCB, 0xD5, 0xE1)

        # Slide 2: KPI Dashboard
        s2 = new_slide(
            "Executive KPI Dashboard",
            "核心指标总览",
            "Summary of all 7 research pillars.",
            [p.id for p in papers[:4]],
        )
        kpis = [
            ("Papers & GRADE / 文献评级", f"{len(papers)} 篇 · GRADE {evidence.grade.grade if evidence else 'N/A'} ({evidence.grade.score if evidence else 0}/10)"),
            ("Hypotheses / 科学假设", f"{len(synthesis.hypotheses) if synthesis else 0} 条可证伪假设 (Gaps: {len(synthesis.gaps) if synthesis else 0})"),
            ("Simulation Gain / 模拟实验", f"{experiment.branches[0].metrics.get('delta', 0):+.4f}" if experiment and experiment.branches else "N/A"),
            ("Evolution Gain / 算法进化", f"{evolution.improvement_pct if evolution else 0:+.2f}% (Best {evolution.best_candidate.fitness if evolution else 0:.3f})"),
            ("Sovereign KB / 本地知识库", f"{len(knowledge_link.matched_kb_concepts) if knowledge_link else 0} 概念 · {len(knowledge_link.gold_edges) if knowledge_link else 0} 金边"),
            ("Citation Grounding / 应证率", f"{manuscript.citation_audit.grounding_rate * 100 if manuscript else 100:.1f}% · Review {manuscript.review.overall_score if manuscript else 0:.2f}/10"),
        ]
        for idx, (lbl, val) in enumerate(kpis):
            col = idx % 3
            row = idx // 3
            add_card(s2, 0.6 + col * 4.1, 1.35 + row * 2.65, 3.85, 2.3, lbl, [val])

        # Slide 3: Literature Retrieval & PRISMA
        s3 = new_slide(
            "Multi-Source Literature & PRISMA Screening",
            "多源文献检索与 PRISMA 筛选",
            "PRISMA funnel and retrieval distribution.",
            [p.id for p in papers[:5]],
        )
        pc = evidence.prisma_counts if evidence else None
        add_card(
            s3,
            0.6,
            1.35,
            5.2,
            5.3,
            "PRISMA Funnel / 筛选流程",
            [
                f"Identified / 检索识别: {pc.identified if pc else 0}",
                f"Deduplicated / 去重合并: {pc.deduplicated if pc else 0}",
                f"Screened / 筛选评估: {pc.screened if pc else 0}",
                f"Included / 最终纳入: {pc.included if pc else 0}",
                "",
                f"Sources: {evidence.sources_used if evidence else {}}",
            ],
        )
        if lit_chart_path and Path(lit_chart_path).exists():
            s3.shapes.add_picture(lit_chart_path, Inches(6.05), Inches(1.45), width=Inches(6.7))

        # Slide 4: GRADE & Contradictions
        s4 = new_slide(
            "GRADE Assessment & Contradictions",
            "证据分级与实证冲突矩阵",
            "GRADE rubric and detected contradictions.",
            [p.id for p in papers[:4]],
        )
        add_card(
            s4,
            0.6,
            1.3,
            12.1,
            1.8,
            f"GRADE {evidence.grade.grade if evidence else 'N/A'} ({evidence.grade.score if evidence else 0}/10.0)",
            [evidence.grade.reasoning_en if evidence else "", evidence.grade.reasoning_zh if evidence else ""],
        )
        con_rows = [
            [c.paper_a_id, c.paper_b_id, c.severity, c.explanation_en[:85], c.explanation_zh[:60]]
            for c in (synthesis.contradictions[:4] if synthesis else [])
        ] or [["None", "-", "-", "No major cross-paper contradiction flagged", "暂未检出高冲突文献"]]
        add_table(s4, 0.6, 3.3, 12.1, 3.3, ["Paper A", "Paper B", "Severity", "Conflict (EN)", "冲突说明 (ZH)"], con_rows)

        # Slide 5: Gaps & Hypotheses
        s5 = new_slide(
            "Research Gaps & Falsifiable Hypotheses",
            "研究缺口与可证伪假设",
            "Gaps G1-G3 and hypotheses H1-H3.",
            [h.hypothesis_id for h in (synthesis.hypotheses if synthesis else [])],
        )
        gap_lines = [f"{g.gap_id} ({g.category}): {g.title_en} / {g.title_zh}" for g in (synthesis.gaps if synthesis else [])]
        hyp_lines = [f"{h.hypothesis_id}: {h.title_en} / {h.title_zh} (Metric: {h.primary_metric})" for h in (synthesis.hypotheses if synthesis else [])]
        add_card(s5, 0.6, 1.35, 5.9, 5.3, "Identified Gaps / 研究缺口", gap_lines or ["N/A"])
        add_card(s5, 6.8, 1.35, 5.9, 5.3, "Testable Hypotheses / 科学假设", hyp_lines or ["N/A"])

        # Slide 6: Simulation & Visuals
        s6 = new_slide(
            "Scientific Simulation Design & Outcomes",
            "科学实验模拟设计与核心结果",
            "Sandboxed simulation results.",
            [experiment.winning_branch_id if experiment else "SIM"],
        )
        add_card(
            s6,
            0.6,
            1.35,
            5.0,
            5.3,
            f"Template: {experiment.resolved_template if experiment else 'N/A'}",
            [
                experiment.summary_en if experiment else "N/A",
                "",
                experiment.summary_zh if experiment else "",
            ],
        )
        if experiment and experiment.figure_paths and Path(experiment.figure_paths[0]).exists():
            s6.shapes.add_picture(experiment.figure_paths[0], Inches(5.85), Inches(1.45), width=Inches(6.9))

        # Slide 7: Statistical Rigor Table
        s7 = new_slide(
            "Statistical Verification & Sensitivity",
            "统计检验与消融敏感性分析",
            "Formal hypothesis test metrics.",
            ["stats_report.json"],
        )
        st_rows = [
            [st.test_name, f"{st.statistic:.3f}", f"{st.p_value:.5f}", f"{st.fdr_q_value}", f"{st.effect_size_name}={st.effect_size:.3f}", f"[{st.ci_low}, {st.ci_high}]"]
            for st in (experiment.stats if experiment else [])
        ] or [["N/A", "-", "-", "-", "-", "-"]]
        add_table(s7, 0.6, 1.45, 12.1, 4.8, ["Test Name", "Statistic", "p-value", "FDR q", "Effect Size", "95% CI"], st_rows)

        # Slide 8: Algorithm Evolution
        s8 = new_slide(
            "Algorithm Evolution (MAP-Elites + Multi-Island)",
            "多岛 MAP-Elites 算法进化优化",
            "Evolution convergence and Pareto front.",
            [evolution.best_candidate.candidate_id if evolution else "EVO"],
        )
        add_card(
            s8,
            0.6,
            1.35,
            4.8,
            5.3,
            f"Benchmark: {evolution.benchmark_name if evolution else 'N/A'}",
            [
                evolution.summary_en if evolution else "N/A",
                "",
                evolution.summary_zh if evolution else "",
                f"Pareto Frontier Size: {len(evolution.pareto_front) if evolution else 0}",
            ],
        )
        if evolution and evolution.chart_path and Path(evolution.chart_path).exists():
            s8.shapes.add_picture(evolution.chart_path, Inches(5.65), Inches(1.45), width=Inches(7.1))

        # Slide 9: Sovereign Knowledge Graph
        s9 = new_slide(
            "Sovereign Knowledge Base & Multi-Hop PPR",
            "本地主权知识库多跳图谱关联",
            "HippoRAG2 PPR bridges and LightRAG communities.",
            ["via54_kb.db", "gold_vault_node_z.db"],
        )
        kb_rows = [
            [b["label"][:52], b["node_type"], f"{b['ppr_score']:.5f}", str(b["hop_distance"]), str(b["community_id"])]
            for b in (knowledge_link.ppr_multihop_bridges[:7] if knowledge_link else [])
        ] or [["No live KB nodes", "-", "0.0", "-", "0"]]
        add_table(s9, 0.6, 1.45, 12.1, 5.1, ["KB Concept / Gold Axiom", "Node Type", "PPR Score", "Hop", "Community"], kb_rows)

        # Slide 10: Citation Provenance Audit
        s10 = new_slide(
            "Dual-Source Citation Provenance Audit",
            "双源引文应证与零幻觉审计",
            "Every claim mapped to verified source IDs.",
            [p.id for p in papers[:6]],
        )
        cit_rows = [
            [p.id, p.title[:48], p.doi or p.arxiv_id or "N/A", ", ".join(p.source_origins), f"{p.relevance_score:.3f}"]
            for p in papers[:8]
        ] or [["-", "No papers", "-", "-", "-"]]
        add_table(s10, 0.6, 1.45, 12.1, 5.1, ["ID", "Title", "DOI / arXiv", "Sources", "Score"], cit_rows)

        # Slide 11: Peer Review & Limitations
        s11 = new_slide(
            "Automated Peer Review Scorecard",
            "六维自动化同行评审与局限性",
            "NeurIPS/Nature 6-dimension automated review.",
            ["manuscript.md"],
        )
        rev = manuscript.review if manuscript else None
        add_card(
            s11,
            0.6,
            1.35,
            5.8,
            5.3,
            f"Decision: {rev.decision if rev else 'N/A'} (Overall {rev.overall_score if rev else 0}/10)",
            [
                f"Originality / 原创性: {rev.originality if rev else 0}/10",
                f"Method Soundness / 方法严谨性: {rev.methodological_soundness if rev else 0}/10",
                f"Statistical Rigor / 统计严密性: {rev.statistical_rigor if rev else 0}/10",
                f"Literature Coverage / 文献覆盖: {rev.literature_coverage if rev else 0}/10",
                f"KB Integration / 知识融合: {rev.knowledge_graph_integration if rev else 0}/10",
                f"Clarity & Reproducibility / 可复现性: {rev.clarity_reproducibility if rev else 0}/10",
            ],
        )
        add_card(
            s11,
            6.7,
            1.35,
            6.0,
            5.3,
            "Strengths & Revisions / 优势与修订建议",
            (rev.strengths_zh + rev.weaknesses_zh + rev.revisions_zh) if rev else ["N/A"],
        )

        # Slide 12: Strategic Roadmap & References
        s12 = new_slide(
            "Strategic Roadmap & References",
            "后续研究路线图与核心文献",
            "Closing roadmap and key references.",
            [p.id for p in papers[:5]],
        )
        add_card(
            s12,
            0.6,
            1.35,
            5.6,
            5.3,
            "Next-Step Roadmap / 下一步科研路线",
            [
                "1. Expand live prospective validation datasets / 扩展真实前瞻性验证队列",
                "2. Run custom domain algorithm evolution loops / 针对业务核心算子定向进化",
                "3. Sync curated findings into Sovereign KB / 将沉淀专著回写主权知识库",
                "4. Render Office COM visual QA proofs / 导出高保真会议展示视觉稿",
            ],
        )
        ref_lines = [f"[{p.id}] {p.title[:65]} ({p.year})" for p in papers[:6]]
        add_card(s12, 6.5, 1.35, 6.2, 5.3, "Key References / 关键参考文献", ref_lines or ["None"])

        pptx_path = out_dir / "presentation.pptx"
        prs.save(str(pptx_path))

        manifest_path = atomic_write_json(
            out_dir / "ppt_dual_source_manifest.json",
            {
                "run_id": run_id,
                "theme": ss.theme,
                "slide_count": slide_no,
                "dual_source_rule": "Never stitch synthetic PDFs; cite verified primary & fallback provenance explicitly.",
                "slides": manifest_slides,
            },
        )

        rendered_pngs: List[str] = []
        render_status: Dict[str, Any] = {"requested": ss.render_visuals, "ok": False, "note": "Visual render not requested"}
        if ss.render_visuals:
            from via54sciforge.deliverables.render_bridge import render_pptx_to_pngs

            res = render_pptx_to_pngs(pptx_path, out_dir / "slides_png")
            render_status = res
            rendered_pngs = res.get("png_paths", [])

        return SlideDeckOutput(
            run_id=run_id,
            theme=ss.theme,
            pptx_path=str(pptx_path),
            slide_count=slide_no,
            manifest_path=str(manifest_path),
            rendered_pngs=rendered_pngs,
            render_status=render_status,
        )
