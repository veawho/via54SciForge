"""Tests for Pillar 6 & 7: Academic manuscript, stylometry, citation audit, peer review, HTML/DOCX reports & 12-slide PPTX."""

from pathlib import Path

from docx import Document
from pptx import Presentation

from via54sciforge.core.models import (
    EvidencePackage,
    ExperimentRun,
    ExperimentSpec,
    ManuscriptSpec,
    PaperRecord,
    ResearchQuestion,
    SlideSpec,
)
from via54sciforge.deliverables.pptx_builder import AcademicPPTXBuilder
from via54sciforge.deliverables.reports import DerivativeReportGenerator
from via54sciforge.literature.grader import grade_evidence_package
from via54sciforge.literature.researcher import synthesize_research
from via54sciforge.simulation.runner import ExperimentManager
from via54sciforge.writing.composer import ManuscriptComposer
from via54sciforge.writing.reviewer import audit_citations
from via54sciforge.writing.stylometry import audit_and_clean_stylometry


def test_stylometry_and_citation_auditor():
    dirty = "Let us delve into the rich tapestry of [P1] and [P999]. 值得注意的是，这不仅赋能了科研。"
    cleaned, rep = audit_and_clean_stylometry(dirty, apply_cleanup=True)
    assert rep["ai_tells_detected"] >= 3
    assert "delve into" not in cleaned.lower()

    ca = audit_citations(cleaned, ["P1", "P2"])
    assert ca.total_inline_citations == 2
    assert ca.verified_citations == 1
    assert ca.unverified_keys == ["P999"]
    assert ca.grounding_rate == 0.5


def test_manuscript_reports_and_pptx_generation(tmp_path: Path):
    papers = [
        PaperRecord(
            id="P1",
            title="Autonomous Tree Search in Computational Oncology",
            authors=["L. Chen", "A. Yamada"],
            journal="Nature Computational Science",
            year=2026,
            doi="10.1038/s43588-026-00912-x",
            study_type="rct",
            cited_by=120,
            abstract="Improved primary accuracy by 18.4% (p=0.002).",
            source_origins=["openalex", "pubmed"],
        ),
        PaperRecord(
            id="P2",
            title="GraphRAG and Multi-Hop Verification",
            authors=["Z. Guo"],
            journal="ACL",
            year=2025,
            doi="10.18653/v1/2025.acl-long.412",
            study_type="benchmark",
            cited_by=200,
            abstract="Achieved 91.2% recall@10.",
            source_origins=["arxiv"],
        ),
    ]
    ev = EvidencePackage(
        run_id="w_test",
        question=ResearchQuestion(query="Computational Oncology Discovery"),
        papers=papers,
        grade=grade_evidence_package(papers),
        sources_used={"openalex": 1, "pubmed": 1, "arxiv": 1},
    )
    syn = synthesize_research(ev)
    exp = ExperimentManager(dpi=150).run_experiment(
        "w_test", tmp_path / "sim", ExperimentSpec(template="ml_ablation_benchmark", seed=42)
    )

    composer = ManuscriptComposer()
    ms = composer.compose(
        run_id="w_test",
        out_dir=tmp_path / "manuscript",
        topic="Computational Oncology Discovery",
        spec=ManuscriptSpec(latex_style="nature"),
        evidence=ev,
        synthesis=syn,
        experiment=exp,
    )
    assert Path(ms.md_path).exists()
    assert Path(ms.tex_path).exists()
    assert Path(ms.bib_path).exists()
    assert Path(ms.docx_path).exists()
    assert ms.citation_audit.grounding_rate == 1.0
    assert ms.review.overall_score >= 7.0
    doc = Document(ms.docx_path)
    assert len(doc.paragraphs) > 10

    rep = DerivativeReportGenerator().generate(
        run_id="w_test",
        out_dir=tmp_path / "deliverables",
        topic="Computational Oncology Discovery",
        report_type="deep_research",
        evidence=ev,
        synthesis=syn,
        experiment=exp,
        manuscript=ms,
    )
    assert Path(rep.md_path).exists()
    html_txt = Path(rep.html_path).read_text(encoding="utf-8")
    assert "data:image/png;base64," in html_txt
    assert Path(rep.docx_path).exists()

    deck = AcademicPPTXBuilder().build(
        run_id="w_test",
        out_dir=tmp_path / "deliverables",
        topic="Computational Oncology Discovery",
        spec=SlideSpec(theme="academic_navy", render_visuals=False),
        evidence=ev,
        synthesis=syn,
        experiment=exp,
        manuscript=ms,
    )
    assert deck.slide_count == 12
    prs = Presentation(deck.pptx_path)
    assert len(prs.slides) == 12
    assert prs.slides[0].notes_slide.notes_text_frame.text.strip() != ""
    assert Path(deck.manifest_path).exists()
