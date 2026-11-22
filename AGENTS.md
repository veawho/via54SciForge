# AGENTS.md — via54SciForge Cross-Agent Protocol / 跨智能体协作规约

## 1. Identity / 项目身份
- **Project**: `via54SciForge`
- **Role**: Unified autonomous scientific discovery, simulation, evolution, Sovereign KB linking, academic writing, and derivative reporting/PPTX engine.
- **Root**: Dynamically resolved from `src/via54sciforge/core/config.py` (never hardcode machine paths).

## 2. Non-Negotiable Engineering Rules / 核心铁律
1. **Bilingual Outputs (中英双语)**: All generated papers, derivative reports, slides, docs, and summaries MUST include Chinese + English sections.
2. **Read-Only Sovereign KB (只读主权知识库)**: Always open `C:\KnowledgeBase_FastRuntime\VectorDB\via54_kb.db` and `Z:\KnowledgeBase_HotCache\gold_vault_node_z.db` with `?mode=ro`. Never write to `via54_kb.db` directly during search/linking; never place files >5MB or `.pptx`/`.pdf`/video inside `Z:\KnowledgeBase_HotCache`.
3. **Dual-Source Provenance (双源不拼合)**: Inherit `via54Medit`'s iron rule — never stitch synthetic PDFs; keep `main_pdf` and `fallback_pdfs` separate in `DualSourceManifest` and `ppt_dual_source_manifest.json`.
4. **Zero-Hallucination Citation Grounding (零幻觉引文)**: Every inline `[P#]` or `\cite{P#}` must pass `audit_citations()` against verified `PaperRecord` IDs.
5. **AST Sandbox Enforcement (沙箱安全)**: All simulation and evolved candidate scripts MUST pass `validate_ast_safety()` before execution.
6. **Honest Status Reporting (诚实架构声明)**: Maintain [HONEST_STATUS.md](docs/HONEST_STATUS.md) — never claim unverified external services or Office COM renders without real execution.
7. **PyMuPDF Import Standard**: Always use `import pymupdf as fitz` (never bare `import fitz`).
