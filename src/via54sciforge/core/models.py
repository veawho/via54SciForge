"""Canonical Pydantic data models for all seven pillars of via54SciForge."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


def utc_now_iso() -> str:
    """Return current UTC timestamp in ISO-8601 format."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class PICO(BaseModel):
    """Structured Population / Intervention / Comparator / Outcome clinical framing."""

    population: str = ""
    intervention: str = ""
    comparator: str = ""
    outcome: str = ""


class ResearchQuestion(BaseModel):
    """Normalized research query across scientific and biomedical domains."""

    query: str
    pico: Optional[PICO] = None
    language: str = "bilingual"
    sources: List[str] = Field(default_factory=list)
    max_results: int = 15


class PaperRecord(BaseModel):
    """Unified deduplicated bibliographic & evidence record."""

    id: str
    title: str
    authors: List[str] = Field(default_factory=list)
    journal: str = ""
    year: int = 0
    doi: str = ""
    pmid: str = ""
    arxiv_id: str = ""
    abstract: str = ""
    fulltext_excerpt: str = ""
    cited_by: int = 0
    fwci: float = 0.0
    study_type: str = "observational"  # meta_analysis | rct | benchmark | cohort | preprint | guideline
    oa_pdf_url: str = ""
    source_origins: List[str] = Field(default_factory=list)
    relevance_score: float = 0.0
    key_findings: List[str] = Field(default_factory=list)
    raw_meta: Dict[str, Any] = Field(default_factory=dict)


class GradeAssessment(BaseModel):
    """Transparent GRADE evidence rating with diagnostic breakdown."""

    grade: Literal["A", "B", "C", "D"] = "B"
    score: float = 0.0
    max_score: float = 10.0
    rct_ratio: float = 0.0
    meta_analysis_count: int = 0
    multi_source_count: int = 0
    recency_ratio: float = 0.0
    contradiction_penalty: float = 0.0
    reasoning_en: str = ""
    reasoning_zh: str = ""


class PrismaCounts(BaseModel):
    """PRISMA-style literature screening flow counts."""

    identified: int = 0
    deduplicated: int = 0
    screened: int = 0
    included: int = 0
    excluded_reasons: Dict[str, int] = Field(default_factory=dict)


class EvidencePackage(BaseModel):
    """Output bundle from Pillar 1 multi-source literature search & screening."""

    run_id: str
    question: ResearchQuestion
    papers: List[PaperRecord] = Field(default_factory=list)
    prisma_counts: PrismaCounts = Field(default_factory=PrismaCounts)
    grade: GradeAssessment = Field(default_factory=GradeAssessment)
    sources_used: Dict[str, int] = Field(default_factory=dict)
    summary_zh: str = ""
    summary_en: str = ""
    created_at: str = Field(default_factory=utc_now_iso)


class ProducerAuditResult(BaseModel):
    """PDF authenticity classification & L0 Crossref verification (inherited from via54Medit)."""

    pdf_path: str
    pdf_type: Literal["real_pdf", "reportlab_wrap", "chrome_screenshot", "meeting_abstract", "unknown"] = "unknown"
    producer: str = ""
    creator: str = ""
    page_count: int = 0
    text_char_count: int = 0
    extracted_doi: str = ""
    extracted_ncts: List[str] = Field(default_factory=list)
    repair_strategy: str = "inspect_manually"
    l0_crossref_verified: bool = False
    crossref_title: str = ""
    issues: List[str] = Field(default_factory=list)


class DualSourceManifest(BaseModel):
    """Dual-source provenance manifest tracking main + fallback evidence without PDF merging."""

    item_id: str
    main_pdf: str
    fallback_pdfs: List[str] = Field(default_factory=list)
    fallback_triggered: bool = False
    trigger_reason: str = ""
    evidence_sources: List[Dict[str, Any]] = Field(default_factory=list)
    step2_score: Optional[float] = None
    equivalent_matches: List[str] = Field(default_factory=list)
    found_locations: List[Dict[str, Any]] = Field(default_factory=list)
    verification_chain_5step: List[str] = Field(default_factory=list)
    highlight_image_path: str = ""


class ClaimContradiction(BaseModel):
    """Detected empirical or directional conflict between two literature records."""

    topic_metric: str
    paper_a_id: str
    paper_a_claim: str
    paper_b_id: str
    paper_b_claim: str
    severity: Literal["high", "medium", "low"] = "medium"
    explanation_en: str = ""
    explanation_zh: str = ""


class ResearchGap(BaseModel):
    """Identified scientific gap mined from multi-paper synthesis."""

    gap_id: str
    category: str  # methodological | population | temporal | mechanistic | translational
    title_en: str
    title_zh: str
    description_en: str
    description_zh: str
    supporting_paper_ids: List[str] = Field(default_factory=list)


class Hypothesis(BaseModel):
    """Structured falsifiable scientific hypothesis with testable experiment blueprint."""

    hypothesis_id: str
    title_en: str
    title_zh: str
    statement_en: str
    statement_zh: str
    null_hypothesis: str
    primary_metric: str
    recommended_sim_template: str
    grounding_paper_ids: List[str] = Field(default_factory=list)
    confidence: float = 0.7


class ResearchSynthesis(BaseModel):
    """Output bundle from Pillar 2 deep research, conflict analysis & hypothesis mining."""

    run_id: str
    query: str
    rcs_passages: List[Dict[str, Any]] = Field(default_factory=list)
    contradictions: List[ClaimContradiction] = Field(default_factory=list)
    gaps: List[ResearchGap] = Field(default_factory=list)
    hypotheses: List[Hypothesis] = Field(default_factory=list)
    synthesis_en: str = ""
    synthesis_zh: str = ""
    created_at: str = Field(default_factory=utc_now_iso)


class StatTestResult(BaseModel):
    """Result of a formal statistical hypothesis test."""

    test_name: str
    statistic: float
    p_value: float
    fdr_q_value: Optional[float] = None
    effect_size: float = 0.0
    effect_size_name: str = "cohens_d"
    ci_low: Optional[float] = None
    ci_high: Optional[float] = None
    significant_at_05: bool = False
    interpretation_en: str = ""
    interpretation_zh: str = ""


class ExperimentBranch(BaseModel):
    """Single simulation branch (baseline, ablation, or sensitivity perturbation)."""

    branch_id: str
    label: str
    params: Dict[str, Any] = Field(default_factory=dict)
    metrics: Dict[str, float] = Field(default_factory=dict)
    elapsed_s: float = 0.0
    returncode: int = 0
    stdout_tail: str = ""
    script_path: str = ""


class ExperimentSpec(BaseModel):
    """Specification for a reproducible sandboxed simulation experiment."""

    hypothesis_id: str = "H1"
    template: str = "auto"  # clinical_rct_monte_carlo | ode_dynamical_system | ml_ablation_benchmark | network_diffusion_abm | custom
    seed: int = 42
    params: Dict[str, Any] = Field(default_factory=dict)
    custom_code: Optional[str] = None


class ExperimentRun(BaseModel):
    """Output bundle from Pillar 3 scientific experiment simulation & statistical testing."""

    run_id: str
    spec: ExperimentSpec
    resolved_template: str
    branches: List[ExperimentBranch] = Field(default_factory=list)
    winning_branch_id: str = ""
    stats: List[StatTestResult] = Field(default_factory=list)
    figure_paths: List[str] = Field(default_factory=list)
    reproducible_script_path: str = ""
    raw_series: Dict[str, Any] = Field(default_factory=dict)
    summary_en: str = ""
    summary_zh: str = ""
    created_at: str = Field(default_factory=utc_now_iso)


class EvolutionCandidate(BaseModel):
    """Individual candidate algorithm stored in the MAP-Elites multi-island archive."""

    candidate_id: str
    generation: int
    island_id: int
    parent_id: Optional[str] = None
    operator: str = "seed"
    code: str
    fitness: float
    behavioral_coords: List[int] = Field(default_factory=list)
    complexity: int = 0
    runtime_ms: float = 0.0
    novelty_score: float = 1.0
    code_hash: str = ""
    metrics: Dict[str, Any] = Field(default_factory=dict)
    valid: bool = True
    error: str = ""


class EvolutionIslandStats(BaseModel):
    """Per-island summary metrics."""

    island_id: int
    archive_size: int = 0
    best_fitness: float = 0.0
    mean_fitness: float = 0.0


class EvolutionRunResult(BaseModel):
    """Output bundle from Pillar 4 algorithm evolution."""

    run_id: str
    benchmark_name: str
    generations: int
    num_islands: int
    total_evaluations: int
    rejected_novelty: int = 0
    seed_fitness: float
    best_candidate: EvolutionCandidate
    improvement_pct: float = 0.0
    pareto_front: List[EvolutionCandidate] = Field(default_factory=list)
    island_stats: List[EvolutionIslandStats] = Field(default_factory=list)
    history: List[Dict[str, Any]] = Field(default_factory=list)
    best_code_path: str = ""
    archive_db_path: str = ""
    chart_path: str = ""
    summary_en: str = ""
    summary_zh: str = ""
    created_at: str = Field(default_factory=utc_now_iso)


class KBSearchHit(BaseModel):
    """Read-only search hit from the local Sovereign Knowledge Base (via54_kb.db)."""

    concept_id: int
    title: str
    rel_path: str = ""
    source_path: str = ""
    snippet: str = ""
    score: float = 0.0
    tags: List[str] = Field(default_factory=list)


class KnowledgeNode(BaseModel):
    """Node in the hybrid research + Sovereign KB graph."""

    node_id: str
    label: str
    node_type: str  # Query | Paper | Hypothesis | Experiment | Algorithm | KBConcept | KBTriple | GoldAxiom
    community_id: int = 0
    ppr_score: float = 0.0
    metadata: Dict[str, Any] = Field(default_factory=dict)


class KnowledgeEdge(BaseModel):
    """Typed directed edge in the hybrid knowledge graph."""

    source: str
    target: str
    relation: str  # SUPPORTS | CONTRADICTS | EXTENDS | VALIDATES | OPTIMIZES | CITES | KB_BRIDGES | GOLD_AXIOM
    weight: float = 1.0
    is_gold: bool = False
    evidence: str = ""


class KnowledgeLinkReport(BaseModel):
    """Output bundle from Pillar 5 Sovereign KB linking & LightRAG/HippoRAG2 graph analysis."""

    run_id: str
    query: str
    kb_available: bool = False
    kb_stats: Dict[str, Any] = Field(default_factory=dict)
    matched_kb_concepts: List[KBSearchHit] = Field(default_factory=list)
    matched_triples: List[Dict[str, Any]] = Field(default_factory=list)
    gold_edges: List[Dict[str, Any]] = Field(default_factory=list)
    ppr_multihop_bridges: List[Dict[str, Any]] = Field(default_factory=list)
    communities: List[Dict[str, Any]] = Field(default_factory=list)
    nodes: List[KnowledgeNode] = Field(default_factory=list)
    edges: List[KnowledgeEdge] = Field(default_factory=list)
    wiki_links: List[str] = Field(default_factory=list)
    mermaid_diagram: str = ""
    graph_json_path: str = ""
    sync_preview: Dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=utc_now_iso)


class CitationAuditResult(BaseModel):
    """Zero-hallucination citation grounding check over generated text."""

    total_inline_citations: int = 0
    verified_citations: int = 0
    unverified_keys: List[str] = Field(default_factory=list)
    grounding_rate: float = 1.0
    details: List[Dict[str, Any]] = Field(default_factory=list)


class PeerReviewReport(BaseModel):
    """Automated 6-dimension NeurIPS/Nature-style manuscript review."""

    originality: float = 7.5
    methodological_soundness: float = 8.0
    statistical_rigor: float = 8.0
    literature_coverage: float = 8.0
    knowledge_graph_integration: float = 8.0
    clarity_reproducibility: float = 8.0
    overall_score: float = 7.9
    decision: Literal["Accept", "Minor Revision", "Major Revision"] = "Minor Revision"
    strengths_en: List[str] = Field(default_factory=list)
    strengths_zh: List[str] = Field(default_factory=list)
    weaknesses_en: List[str] = Field(default_factory=list)
    weaknesses_zh: List[str] = Field(default_factory=list)
    revisions_en: List[str] = Field(default_factory=list)
    revisions_zh: List[str] = Field(default_factory=list)


class ManuscriptSpec(BaseModel):
    """Configuration for generating an academic manuscript."""

    paper_type: Literal["imrad", "systematic_review", "technical_monograph"] = "imrad"
    latex_style: Literal["ieee", "nature", "neurips", "academic"] = "academic"
    bilingual: bool = True
    apply_deai: bool = True


class ManuscriptOutput(BaseModel):
    """Output bundle from Pillar 6 academic literature writing & peer review."""

    run_id: str
    title_en: str
    title_zh: str
    md_path: str
    tex_path: str
    bib_path: str
    docx_path: str
    word_count: int = 0
    stylometry: Dict[str, Any] = Field(default_factory=dict)
    citation_audit: CitationAuditResult = Field(default_factory=CitationAuditResult)
    review: PeerReviewReport = Field(default_factory=PeerReviewReport)
    created_at: str = Field(default_factory=utc_now_iso)


class DerivativeReportOutput(BaseModel):
    """Output bundle from Pillar 7 derivative report generation."""

    run_id: str
    report_type: Literal["executive_brief", "deep_research", "evidence_matrix", "translation_brief"]
    md_path: str
    html_path: str
    docx_path: str
    created_at: str = Field(default_factory=utc_now_iso)


class SlideSpec(BaseModel):
    """Configuration for academic presentation deck generation."""

    theme: Literal["academic_navy", "clinical_clean", "executive_slate", "dark_keynote"] = "academic_navy"
    render_visuals: bool = False


class SlideDeckOutput(BaseModel):
    """Output bundle from Pillar 7 academic PPTX generation & dual-source manifest."""

    run_id: str
    theme: str
    pptx_path: str
    slide_count: int = 0
    manifest_path: str = ""
    rendered_pngs: List[str] = Field(default_factory=list)
    render_status: Dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=utc_now_iso)


class PipelineRunResult(BaseModel):
    """Unified output returned by the 7-pillar end-to-end orchestrator."""

    run_id: str
    topic: str
    workspace_dir: str
    offline_mode: bool = False
    stage_statuses: Dict[str, str] = Field(default_factory=dict)
    evidence: Optional[EvidencePackage] = None
    synthesis: Optional[ResearchSynthesis] = None
    experiment: Optional[ExperimentRun] = None
    evolution: Optional[EvolutionRunResult] = None
    knowledge_link: Optional[KnowledgeLinkReport] = None
    manuscript: Optional[ManuscriptOutput] = None
    report: Optional[DerivativeReportOutput] = None
    slides: Optional[SlideDeckOutput] = None
    summary_md_path: str = ""
    summary_json_path: str = ""
    created_at: str = Field(default_factory=utc_now_iso)
