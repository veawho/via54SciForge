# Changelog / 变更日志

## [1.0.0] - 2026-11-23
### Added / 新增
- **Pillar 1 (Literature Analysis & Dual-Source Audit)**: 5-source async literature search (OpenAlex, PubMed, arXiv, Semantic Scholar, EuropePMC) + ClinicalTrials APIv2 + `via54Medit` bridge + 32-keyword PDF Producer authenticity classifier + 5-step numerical-equivalence bounding-box verification + PRISMA & GRADE scoring.
- **Pillar 2 (Deep Research Synthesis)**: ASReview TF-IDF active prioritization, PaperQA2 RCS passage extraction, Contradiction Matrix detector, and Research Gap / Hypothesis mining.
- **Pillar 3 (Scientific Experiment Simulation)**: AST safety sandbox, 4 parameterized templates (`clinical_rct_monte_carlo`, `ode_dynamical_system`, `ml_ablation_benchmark`, `network_diffusion_abm`), SciPy statistical tests + Benjamini-Hochberg FDR, 300-DPI PNG/SVG charts.
- **Pillar 4 (Algorithm Evolution)**: SQLite-backed multi-island MAP-Elites archive, UCB1 operator bandit, Jaccard novelty filtering, ring migration, Pareto frontier, AST + LLM Search/Replace diff mutators.
- **Pillar 5 (Sovereign KB Linking)**: Strictly read-only `?mode=ro` connector to `via54_kb.db` & `gold_vault_node_z.db`, HippoRAG 2 Personalized PageRank multi-hop bridges, LightRAG community detection, Mermaid + `[[WikiLinks]]`, dry-run 3-way sync.
- **Pillar 6 (Academic Authoring & Review)**: Bilingual IMRaD/Review/Monograph generation in `.md`, `.tex`, `.bib`, `.docx` with De-AI stylometry, 100% citation grounding audit, and 6-dimension peer review.
- **Pillar 7 & Interfaces**: Interactive HTML dashboard + MD + DOCX derivative reports, 4-theme 12-slide bilingual `.pptx` with speaker notes & `ppt_dual_source_manifest.json`, Typer CLI (`--json`), FastAPI + subpath-ready Web Workbench (`/sciforge/`), and 13-tool MCP 2.x stdio server.
