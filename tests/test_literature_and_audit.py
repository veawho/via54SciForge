"""Tests for Pillar 1 & 2: literature fusion, GRADE, PDF audit, 5-step claim verification & deep synthesis."""

from pathlib import Path

import pymupdf as fitz

from via54sciforge.core.models import EvidencePackage, PaperRecord, ResearchQuestion
from via54sciforge.literature.grader import compute_prisma_counts, grade_evidence_package
from via54sciforge.literature.pdf_audit import build_dual_source_manifest, classify_pdf_producer, extract_pdf_structure
from via54sciforge.literature.researcher import active_learning_prioritize, detect_contradictions, synthesize_research
from via54sciforge.literature.sources import LiteratureRouter
from via54sciforge.literature.verifier import numerical_equivalence_variants, verify_claim_against_pdf


def _make_sample_pdf(path: Path, text: str, producer: str = "Adobe PDF Library 17.0") -> Path:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text, fontsize=11)
    doc.set_metadata({"producer": producer, "creator": "LaTeX with hyperref"})
    doc.save(str(path))
    doc.close()
    return path


def test_offline_literature_search_and_grade():
    router = LiteratureRouter()
    q = ResearchQuestion(query="Graph-Augmented Multi-Agent Scientific Discovery", max_results=6)
    papers, used, raw_cnt = router.search(q, offline=True)
    assert len(papers) == 6
    assert used.get("offline_seed") == 6
    prisma = compute_prisma_counts(raw_cnt, papers)
    assert prisma.included == 6
    grade = grade_evidence_package(papers)
    assert grade.grade in ("A", "B")
    assert grade.score > 5.0


def test_pdf_producer_classification_and_5step_verification(tmp_path: Path):
    real_pdf = _make_sample_pdf(
        tmp_path / "real_trial.pdf",
        "Randomized Clinical Trial NCT03298451.\n"
        "Results: Median OS was 23.7 months vs 20.6 months; objective response rate 14.4 in Table 2.\n"
        "DOI: 10.1056/NEJMoa2024020. Additional detailed trial outcomes across cohorts." * 25,
        producer="Adobe InDesign CC 18.0",
    )
    fake_pdf = _make_sample_pdf(
        tmp_path / "reportlab_wrap.pdf",
        "Image: fig2.png\nShort capture.",
        producer="ReportLab PDF Library - www.reportlab.com",
    )

    audit_real = classify_pdf_producer(real_pdf)
    assert audit_real.pdf_type == "real_pdf"
    assert "NCT03298451" in audit_real.extracted_ncts
    assert audit_real.extracted_doi == "10.1056/NEJMoa2024020"

    audit_fake = classify_pdf_producer(fake_pdf)
    assert audit_fake.pdf_type == "reportlab_wrap"
    assert audit_fake.repair_strategy == "replace_with_real_pdf"

    struct = extract_pdf_structure(real_pdf)
    assert struct["pages_parsed"] == 1
    assert len(struct["pages"][0]["blocks"]) >= 1

    # Numerical equivalence: 14.4% should match "14.4" in PDF
    variants = numerical_equivalence_variants("14.4%")
    assert "14.4" in variants

    hl_png = tmp_path / "highlight_proof.png"
    manifest = verify_claim_against_pdf(
        "mOS 23.7 months and ORR 14.4% in NCT03298451",
        real_pdf,
        item_id="P5-15",
        highlight_out_path=hl_png,
    )
    assert manifest.step2_score is not None and manifest.step2_score >= 0.75
    assert any("14.4%" in eq for eq in manifest.equivalent_matches)
    assert len(manifest.verification_chain_5step) == 5
    assert hl_png.exists() and hl_png.stat().st_size > 1000

    ds = build_dual_source_manifest("P30-1", str(fake_pdf), fallback_pdfs=[str(real_pdf)], step2_score=0.45)
    assert ds.fallback_triggered is True


def test_deep_research_synthesis_contradictions_and_hypotheses():
    papers = [
        PaperRecord(
            id="P1",
            title="Tree Search Gains in Automated Discovery",
            year=2026,
            study_type="rct",
            abstract="Our randomized study improved accuracy by 18.4% (p=0.002) with significant gains.",
            source_origins=["pubmed", "openalex"],
            relevance_score=0.9,
        ),
        PaperRecord(
            id="P2",
            title="Replication Variance in Automated Discovery",
            year=2025,
            study_type="cohort",
            abstract="Contrary to earlier claims, replication showed non-significant gain (p=0.19) and limited robustness.",
            source_origins=["arxiv"],
            relevance_score=0.8,
        ),
    ]
    prioritized = active_learning_prioritize(papers, "Tree Search Gains", positive_ids=["P1"])
    assert prioritized[0].id == "P1"
    cons = detect_contradictions(papers)
    assert len(cons) >= 1

    pkg = EvidencePackage(
        run_id="test_res",
        question=ResearchQuestion(query="Automated Discovery"),
        papers=papers,
        grade=grade_evidence_package(papers, cons),
        sources_used={"pubmed": 1, "arxiv": 1},
    )
    syn = synthesize_research(pkg)
    assert len(syn.gaps) >= 3
    assert len(syn.hypotheses) >= 3
    assert syn.synthesis_en and syn.synthesis_zh
