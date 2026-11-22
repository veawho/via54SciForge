# Honest Architecture Status / 诚实架构能力状态表

> Following `via54Medit`'s honest-status principle: strictly distinguish **Implemented & Verified** vs **Optional / Environment-Dependent**.  
> 遵循 `via54Medit` 诚实声明铁律：严格区分「已实装并实测通过」与「可选环境依赖」。

| Layer / 层级 | Capability / 能力 | Status / 状态 | Verification / 实测情况 | Notes / 真实说明 |
|---|---|---|---|---|
| **L0 PDF Audit** | Producer whitelist/blacklist (`reportlab`, `chrome`, `real_pdf`) + Crossref L0 | ✅ Implemented | Tested on synthetic real/wrapper PDFs | Live Crossref requires outbound internet |
| **L1 Literature Retrieval** | Concurrent OpenAlex, PubMed, arXiv, S2, EuropePMC + ClinicalTrials APIv2 + `via54Medit` bridge | ✅ Implemented | Live + `--offline` tested | Zero-key public APIs; offline seed triggers strictly when `--offline` or 0 network hits |
| **L1+ Claim Verification** | Semantic numerical equivalence (`14.4%` ↔ `14.4`) + 5-step chain + bbox PNG highlight | ✅ Implemented | PyMuPDF bbox PNG verified | Pure local PDF parsing, no OCR bloat unless scanned |
| **L2 Deep Research** | ASReview TF-IDF active prioritization + PaperQA2 RCS + Contradiction Matrix + Gaps/Hypotheses | ✅ Implemented | Deterministic + optional LLM enrichment | Works offline or enhanced via `LLMRouter` |
| **L3 Simulation Sandbox** | AST safety validator + 4 parameterized templates + SciPy stats (Welch/MW/ANOVA/KM Log-Rank/BH-FDR) + 300-DPI charts | ✅ Implemented | All 4 templates + stats verified | Isolated subprocess execution with timeout & deterministic seed |
| **L4 Algorithm Evolution** | SQLite MAP-Elites multi-island archive + UCB1 bandit + Jaccard novelty filter + Pareto frontier + AST/LLM diff mutators | ✅ Implemented | `symbolic_discovery` & `circle_packing` verified improving over seed | Deterministic AST mutators work offline; semantic diff uses `LLMRouter` when configured |
| **L5 Sovereign KB Link** | Read-only `via54_kb.db` (`kb_fts`, `concepts`, `triples`, `kb_cross_references`) + `gold_vault_node_z.db` + HippoRAG2 PPR + LightRAG communities | ✅ Implemented | Verified on mock DB + live `via54_kb.db` read-only | Never mutates live `via54_kb.db`; `kb sync` defaults to `dry-run` |
| **L6 Academic Writing & Review** | Bilingual IMRaD/Review/Monograph (`.md`/`.tex`/`.bib`/`.docx`) + De-AI stylometry + Citation Grounding + 6-dim Peer Review | ✅ Implemented | Verified 100% grounding & valid DOCX/TeX/BibTeX | Compiling `.tex` to `.pdf` requires optional `xelatex` if PDF output is desired |
| **L7 Deliverables & Interfaces** | Bilingual MD/HTML/DOCX reports + 4-theme 12-slide `.pptx` + `ppt_dual_source_manifest.json` + Typer CLI + FastAPI + 13-tool MCP 2.x | ✅ Implemented | FastAPI `TestClient` + 13-tool MCP + `.pptx` verified | Visual slide PNG render via PowerPoint COM is opt-in (`--render`) on Windows Desktop Office |
