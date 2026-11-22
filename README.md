# via54SciForge · 全能自主科研引擎

> **Bilingual Documentation · 中英双语文档**  
> **Unified Autonomous Scientific Research, Sandbox Experiment Simulation, MAP-Elites Algorithm Evolution, Sovereign KB Multi-Hop Linking, Academic Writing & Derivative Report/PPTX Suite.**  
> **集多源文献分析、深度研究合成、AST 沙箱科学实验模拟、多岛 MAP-Elites 算法进化、本地主权知识库多跳链接、学术论文撰写与同行评审、衍生交互报告与 12 页 PPTX 生成于一体的全新科研引擎。**

---

## 1. Architecture Overview · 七柱闭环架构

`via54SciForge` synthesizes the proven engineering strengths of **`via54Medit` (v5.4.52)** with state-of-the-art 2025–2026 open-source scientific agents across GitHub, Reddit, and HuggingFace:

| Pillar / 能力柱 | Open-Source & `via54Medit` Lineage / 技术渊源 | Implemented Engine / 本项目实装引擎 |
|---|---|---|
| **1. Literature Analysis & Audit**<br>多源文献分析与应证核查 | `via54Medit` (`anno2ppt`, Producer Classifier, L0 Crossref, Dual-Source) + `ClinicalTrials` APIv2 | `literature/sources.py`, `pdf_audit.py`, `verifier.py`, `grader.py` — OpenAlex, PubMed, arXiv, S2, EuropePMC concurrent fusion + 32+ keyword PDF Producer audit + 5-step numerical-equivalence bbox verification |
| **2. Deep Research Synthesis**<br>深度文献研究与假设挖掘 | `PaperQA2` (RCS), `ASReview` (Active Learning), `STORM` / `OpenScholar` | `literature/researcher.py` — TF-IDF active screening, RCS quantitative passage extraction, Contradiction Matrix, Research Gaps & falsifiable Hypotheses |
| **3. Scientific Simulation**<br>科学实验模拟与统计检验 | `AI-Scientist-v2` (Experiment Manager tree branches) + SciPy/NumPy/NetworkX | `simulation/sandbox.py`, `stats_engine.py`, `templates.py`, `visualizer.py`, `runner.py` — AST safety sandbox, 4 parameterized simulation templates, Welch t / Mann-Whitney / ANOVA / Log-Rank KM / BH-FDR, 300-DPI PNG+SVG charts |
| **4. Algorithm Evolution**<br>多岛算法进化引擎 | `AlphaEvolve` / `OpenEvolve` (MAP-Elites + islands) + `ShinkaEvolve` (novelty filter + bandit) | `evolution/archive.py`, `mutators.py`, `benchmarks.py`, `engine.py` — SQLite MAP-Elites multi-island grid, UCB1 operator bandit, Jaccard novelty rejection, Pareto front, AST + LLM diff mutators |
| **5. Sovereign KB Linking**<br>本地主权知识库全能力关联 | `LightRAG` (dual-level communities) + `HippoRAG 2` (Personalized PageRank) + `via54_kb.db` | `kb_bridge/local_kb.py`, `graph_engine.py`, `sync.py` — Strictly read-only queries to `via54_kb.db` (`kb_fts`, `concepts`, `triples`, `kb_cross_references`) & `gold_vault_node_z.db`, PPR multi-hop bridges, Mermaid + `[[WikiLinks]]`, dry-run 3-way sync |
| **6. Academic Writing & Review**<br>学术论文撰写与自动审稿 | `AI-Scientist` LaTeX/Review + `via54` Stylometry De-AI | `writing/composer.py`, `stylometry.py`, `reviewer.py` — Bilingual IMRaD/Review/Monograph in `.md` + `.tex` + `.bib` + `.docx`, zero-hallucination citation grounding audit, 6-dimension automated peer review |
| **7. Derivative Reports & PPTX**<br>衍生报告与学术 PPT 引擎 | `Paper2Slides` + `PPTAgent` + `via54Medit` Dual-Source Manifest + Office COM | `deliverables/reports.py`, `pptx_builder.py`, `render_bridge.py` — Interactive HTML dashboard + MD + DOCX reports, 4-theme 12-slide bilingual `.pptx` with speaker notes & `ppt_dual_source_manifest.json`, optional PowerPoint COM visual render |

---

## 2. Quick Start · 快速上手

```powershell
# 1. Activate environment / 激活虚拟环境
cd C:\Users\via54\.gemini\antigravity\scratch\via54SciForge
.\.venv\Scripts\Activate.ps1

# 2. Honest system diagnostics / 系统能力诚实自检
via54-sciforge doctor

# 3. Inspect live Sovereign Knowledge Base / 检查本地主权知识库
via54-sciforge kb stats

# 4. Run full 7-pillar end-to-end pipeline / 运行全七柱科研流水线
via54-sciforge run "Graph-Augmented Multi-Agent Scientific Discovery" --benchmark symbolic_discovery --generations 8 --islands 3

# 5. Start Web Workbench & FastAPI Swagger (/docs) / 启动 Web 工作台与 REST 服务
via54-sciforge serve --host 127.0.0.1 --port 8540

# 6. Start stdio MCP Server (13 tools) / 启动 MCP 服务端
via54-sciforge-mcp
```

---

## 3. CLI Reference · 命令速查

- `via54-sciforge doctor [--render-canary] [--json]`
- `via54-sciforge lit search "<query>" [--sources openalex,pubmed,arxiv,semanticscholar,europepmc] [--max 12] [--offline] [--json]`
- `via54-sciforge lit audit <pdf_path> [--doi <doi>] [--crossref] [--json]`
- `via54-sciforge lit verify <pdf_path> --claim "<text>" [--highlight out.png] [--json]`
- `via54-sciforge research "<query>" [--offline] [--json]`
- `via54-sciforge simulate --topic "<topic>" [--template auto|clinical_rct_monte_carlo|ode_dynamical_system|ml_ablation_benchmark|network_diffusion_abm] [--seed 42] [--json]`
- `via54-sciforge evolve --benchmark <symbolic_discovery|circle_packing|evidence_scoring> [--generations 10] [--islands 3] [--json]`
- `via54-sciforge kb stats [--json]`
- `via54-sciforge kb search "<query>" [--limit 10] [--json]`
- `via54-sciforge kb link "<query_or_evidence_json>" [--json]`
- `via54-sciforge kb sync <artifact.md> [--apply] [--json]` *(dry-run by default; enforces `Z:\KnowledgeBase_HotCache` <=5MB & no `.pptx`/`.pdf`/video)*
- `via54-sciforge write paper --run-dir <dir> [--style academic|ieee|nature|neurips] [--json]`
- `via54-sciforge write review <manuscript.md> [--evidence <evidence_package.json>] [--json]`
- `via54-sciforge deliver report --run-dir <dir> [--type executive_brief|deep_research|evidence_matrix|translation_brief] [--json]`
- `via54-sciforge deliver ppt --run-dir <dir> [--theme academic_navy|clinical_clean|executive_slate|dark_keynote] [--render] [--json]`
- `via54-sciforge run "<topic>" [--offline] [--benchmark ...] [--theme ...] [--render] [--json]`

---

## 4. Testing · 测试验证

```powershell
.venv\Scripts\pytest.exe -v
```
