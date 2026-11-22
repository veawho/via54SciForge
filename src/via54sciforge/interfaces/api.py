"""FastAPI REST API & interactive bilingual Web Workbench UI for via54SciForge."""

from __future__ import annotations

import os
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from via54sciforge import __version__
from via54sciforge.core.config import SciForgeConfig
from via54sciforge.core.doctor import run_doctor
from via54sciforge.core.llm import LLMRouter
from via54sciforge.core.models import EvidencePackage, ExperimentSpec, ResearchQuestion
from via54sciforge.core.storage import WorkspaceStore
from via54sciforge.evolution.engine import EvolutionEngine
from via54sciforge.kb_bridge.graph_engine import HybridKnowledgeGraph
from via54sciforge.kb_bridge.local_kb import LocalKBFederation
from via54sciforge.literature.grader import compute_prisma_counts, grade_evidence_package
from via54sciforge.literature.researcher import synthesize_research
from via54sciforge.literature.sources import LiteratureRouter
from via54sciforge.orchestrator.pipeline import SciForgePipeline
from via54sciforge.simulation.runner import ExperimentManager


class LitSearchRequest(BaseModel):
    query: str
    max_results: int = 10
    sources: List[str] = []
    offline: bool = False


class SimulateRequest(BaseModel):
    topic: str
    template: str = "auto"
    seed: int = 42


class EvolveRequest(BaseModel):
    benchmark: str = "symbolic_discovery"
    generations: int = 6
    islands: int = 3
    seed: int = 42


class KBSearchRequest(BaseModel):
    query: str
    limit: int = 10


class PipelineRequest(BaseModel):
    topic: str
    offline: bool = False
    benchmark: str = "symbolic_discovery"
    generations: int = 6
    islands: int = 3
    theme: str = "academic_navy"
    report_type: str = "deep_research"


WORKBENCH_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>via54SciForge Workbench / 七柱自主科研全能工作台</title>
<style>
  :root { --bg: #070b14; --card: rgba(15, 23, 42, 0.88); --border: #23324d; --cyan: #00f0ff; --teal: #10b981; --text: #e2e8f0; --muted: #94a3b8; }
  * { box-sizing: border-box; }
  body { font-family: 'Microsoft YaHei', 'Segoe UI', system-ui, sans-serif; background: radial-gradient(circle at top right, #0f1f3a, var(--bg) 55%); color: var(--text); margin: 0; padding: 24px; min-height: 100vh; }
  .wrap { max-width: 1220px; margin: auto; }
  .header { background: linear-gradient(135deg, rgba(30,58,138,0.85), rgba(15,118,110,0.85)); border: 1px solid rgba(56,189,248,0.35); padding: 24px 28px; border-radius: 16px; margin-bottom: 20px; backdrop-filter: blur(12px); }
  .header h1 { margin: 0 0 6px 0; font-size: 24px; color: #fff; }
  .subtitle { color: #cbd5e1; font-size: 13.5px; line-height: 1.5; }
  .nav-links { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 14px; }
  .nav-links a { text-decoration: none; font-size: 12.5px; font-weight: 600; color: #e2e8f0; background: rgba(2,6,23,0.45); border: 1px solid rgba(148,163,184,0.35); padding: 6px 12px; border-radius: 8px; }
  .nav-links a:hover { border-color: var(--cyan); color: var(--cyan); }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(290px, 1fr)); gap: 16px; }
  .card { background: var(--card); border: 1px solid var(--border); border-radius: 14px; padding: 18px; backdrop-filter: blur(10px); }
  .card h3 { margin: 0 0 6px 0; font-size: 15.5px; color: #38bdf8; }
  .card p { margin: 0 0 8px 0; font-size: 12px; color: var(--muted); }
  label { display: block; font-size: 11.5px; color: var(--muted); margin-top: 8px; }
  input, select, button { width: 100%; padding: 9px 11px; margin-top: 5px; border-radius: 8px; border: 1px solid #334155; background: #020617; color: #f8fafc; font-size: 13px; }
  button { background: linear-gradient(90deg, #0d9488, #0284c7); border: none; font-weight: 700; cursor: pointer; margin-top: 12px; }
  button.sec { background: #1e293b; border: 1px solid #475569; margin-top: 8px; }
  button:hover { opacity: 0.92; }
  .out-card { margin-top: 18px; }
  .out-hdr { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
  pre { background: #020617; border: 1px solid #334155; border-radius: 10px; padding: 14px; overflow: auto; max-height: 430px; font-size: 12.5px; color: #a7f3d0; margin: 0; }
</style>
</head>
<body>
<div class="wrap">
  <div class="header">
    <h1>via54SciForge · Autonomous Scientific Research Workbench / 七柱自主科研全能工作台</h1>
    <div class="subtitle">
      1. Multi-Source Literature &amp; Dual-Source Audit · 2. Active Synthesis &amp; Hypotheses · 3. AST Sandbox Simulation · 4. Multi-Island MAP-Elites Evolution · 5. Sovereign KB HippoRAG2 PPR · 6. Bilingual Paper &amp; Peer Review · 7. Interactive HTML / DOCX / 12-Slide PPTX
    </div>
    <div class="nav-links">
      <a href="docs" target="_blank">OpenAPI Swagger (/docs)</a>
      <a href="https://github.com/veawho/via54SciForge" target="_blank">GitHub: veawho/via54SciForge</a>
      <a href="https://via54.net/index/" target="_blank">via54Lab Portfolio (via54.net)</a>
    </div>
  </div>

  <div class="grid">
    <div class="card">
      <h3>1. 7-Pillar Full Pipeline / 全七柱端到端流水线</h3>
      <p>Run literature → synthesis → simulation → evolution → KB linking → paper → HTML &amp; PPTX.</p>
      <label>Research Topic / 研究主题</label>
      <input id="topic" value="Graph-Augmented Multi-Agent Scientific Discovery"/>
      <label>Evolution Benchmark / 进化基准</label>
      <select id="bench">
        <option value="symbolic_discovery">symbolic_discovery</option>
        <option value="circle_packing">circle_packing</option>
        <option value="evidence_scoring">evidence_scoring</option>
      </select>
      <label>Literature Mode / 检索模式</label>
      <select id="offline">
        <option value="true">Offline Seed (Fast Demo)</option>
        <option value="false">Live Multi-Source APIs</option>
      </select>
      <button onclick="runPipeline()">Execute Full Pipeline / 启动全流程</button>
    </div>

    <div class="card">
      <h3>2. Literature Search / 多源文献检索与 GRADE</h3>
      <p>Concurrent OpenAlex, PubMed, arXiv, Semantic Scholar &amp; EuropePMC fusion.</p>
      <label>Query / 检索问题</label>
      <input id="litq" value="MAP-Elites evolutionary code discovery LLM"/>
      <label>Mode / 模式</label>
      <select id="lit_off">
        <option value="false">Live APIs (auto-fallback)</option>
        <option value="true">Offline Seed</option>
      </select>
      <button onclick="runLitSearch()">Search &amp; Grade / 文献检索评级</button>
    </div>

    <div class="card">
      <h3>3. Sandboxed Simulation / AST 沙箱科学模拟</h3>
      <p>Run controlled ablations with Welch t, Mann-Whitney, KM Log-Rank &amp; BH-FDR.</p>
      <label>Template / 仿真模板</label>
      <select id="sim_tmpl">
        <option value="clinical_rct_monte_carlo">clinical_rct_monte_carlo (RCT + KM)</option>
        <option value="ode_dynamical_system">ode_dynamical_system (SEIR ODE)</option>
        <option value="ml_ablation_benchmark">ml_ablation_benchmark (Ridge vs OLS)</option>
        <option value="network_diffusion_abm">network_diffusion_abm (Scale-Free ABM)</option>
      </select>
      <label>Seed / 随机种子</label>
      <input id="sim_seed" type="number" value="42"/>
      <button onclick="runSimulate()">Run Sandbox Simulation / 运行仿真实验</button>
    </div>

    <div class="card">
      <h3>4. Algorithm Evolution / 多岛算法进化</h3>
      <p>SQLite MAP-Elites grid + UCB1 operator bandit + Jaccard novelty filter.</p>
      <label>Benchmark / 算法基准</label>
      <select id="evo_bench">
        <option value="symbolic_discovery">symbolic_discovery</option>
        <option value="circle_packing">circle_packing</option>
        <option value="evidence_scoring">evidence_scoring</option>
      </select>
      <label>Generations / 进化代数</label>
      <input id="evo_gens" type="number" value="6" min="2" max="20"/>
      <button onclick="runEvolve()">Evolve Algorithm / 启动算法进化</button>
    </div>

    <div class="card">
      <h3>5. Doctor &amp; Sovereign KB / 诊断、主权库与历史</h3>
      <p>Inspect capability health, query Sovereign KB (if attached), or list completed runs.</p>
      <label>KB Query / 知识库检索词</label>
      <input id="kbq" value="Knowledge Graph"/>
      <button onclick="searchKB()">Search Sovereign KB / 检索主权库</button>
      <button class="sec" onclick="checkDoctor()">System Doctor / 系统能力自检</button>
      <button class="sec" onclick="listRuns()">List Recent Runs / 查看历史运行</button>
    </div>
  </div>

  <div class="card out-card">
    <div class="out-hdr">
      <h3 style="margin:0;">Live JSON Output / 实时结构化输出</h3>
      <span id="status" style="font-size:12px;color:#94a3b8;">Ready</span>
    </div>
    <pre id="out">Ready. Click any action card above or visit OpenAPI Swagger (/docs).</pre>
  </div>
</div>
<script>
async function callApi(url, method='GET', body=null) {
  const statusEl = document.getElementById('status');
  const outEl = document.getElementById('out');
  statusEl.textContent = 'Running ' + url + '...';
  outEl.textContent = 'Executing...';
  try {
    const opts = { method, headers: {'Content-Type': 'application/json'} };
    if (body) opts.body = JSON.stringify(body);
    const res = await fetch(url, opts);
    const data = await res.json();
    statusEl.textContent = 'HTTP ' + res.status;
    outEl.textContent = JSON.stringify(data, null, 2);
  } catch (err) {
    statusEl.textContent = 'Error';
    outEl.textContent = String(err);
  }
}
function checkDoctor() { callApi('api/v1/doctor'); }
function listRuns() { callApi('api/v1/runs'); }
function searchKB() { callApi('api/v1/kb/search', 'POST', { query: document.getElementById('kbq').value, limit: 8 }); }
function runLitSearch() {
  callApi('api/v1/lit/search', 'POST', {
    query: document.getElementById('litq').value,
    max_results: 6,
    offline: document.getElementById('lit_off').value === 'true'
  });
}
function runSimulate() {
  callApi('api/v1/simulate', 'POST', {
    topic: document.getElementById('topic').value,
    template: document.getElementById('sim_tmpl').value,
    seed: parseInt(document.getElementById('sim_seed').value || '42', 10)
  });
}
function runEvolve() {
  callApi('api/v1/evolve', 'POST', {
    benchmark: document.getElementById('evo_bench').value,
    generations: parseInt(document.getElementById('evo_gens').value || '6', 10),
    islands: 3
  });
}
function runPipeline() {
  callApi('api/v1/pipeline/run', 'POST', {
    topic: document.getElementById('topic').value,
    benchmark: document.getElementById('bench').value,
    offline: document.getElementById('offline').value === 'true',
    generations: 6,
    islands: 3
  });
}
</script>
</body>
</html>"""


def create_app(config: Optional[SciForgeConfig] = None) -> FastAPI:
    cfg = config or SciForgeConfig.load()
    root_path = os.environ.get("VIA54_ROOT_PATH", "")
    app = FastAPI(title="via54SciForge API", version=__version__, root_path=root_path)

    @app.get("/", response_class=HTMLResponse)
    def workbench() -> str:
        return WORKBENCH_HTML

    @app.get("/api/v1/health")
    def health() -> dict:
        return {"status": "ok", "service": "via54SciForge", "version": __version__}

    @app.get("/api/v1/doctor")
    def doctor_endpoint() -> dict:
        return run_doctor(cfg, render_canary=False)

    @app.post("/api/v1/lit/search")
    async def api_lit_search(req: LitSearchRequest) -> dict:
        router = LiteratureRouter(cfg)
        q = ResearchQuestion(query=req.query, max_results=req.max_results, sources=req.sources)
        papers, used, raw_cnt = await router.search_async(q, offline=req.offline)
        grade = grade_evidence_package(papers)
        pkg = EvidencePackage(
            run_id=WorkspaceStore.new_run_id("lit"),
            question=q,
            papers=papers,
            prisma_counts=compute_prisma_counts(raw_cnt, papers),
            grade=grade,
            sources_used=used,
        )
        return pkg.model_dump()

    @app.post("/api/v1/research")
    async def api_research(req: LitSearchRequest) -> dict:
        router = LiteratureRouter(cfg)
        q = ResearchQuestion(query=req.query, max_results=req.max_results, sources=req.sources)
        papers, used, raw_cnt = await router.search_async(q, offline=req.offline)
        pkg = EvidencePackage(
            run_id=WorkspaceStore.new_run_id("res"),
            question=q,
            papers=papers,
            prisma_counts=compute_prisma_counts(raw_cnt, papers),
            grade=grade_evidence_package(papers),
            sources_used=used,
        )
        return synthesize_research(pkg, LLMRouter(cfg.llm)).model_dump()

    @app.post("/api/v1/simulate")
    def api_simulate(req: SimulateRequest) -> dict:
        store = WorkspaceStore(cfg.paths.runs_path, cfg.paths.state_db_path)
        rid = store.new_run_id("sim")
        rdir = store.prepare_run_dir(rid)
        mgr = ExperimentManager(timeout_s=cfg.simulation.sandbox_timeout_s, dpi=cfg.simulation.dpi)
        return mgr.run_experiment(rid, rdir / "simulation", ExperimentSpec(template=req.template, seed=req.seed), topic=req.topic).model_dump()

    @app.post("/api/v1/evolve")
    def api_evolve(req: EvolveRequest) -> dict:
        store = WorkspaceStore(cfg.paths.runs_path, cfg.paths.state_db_path)
        rid = store.new_run_id("evo")
        rdir = store.prepare_run_dir(rid)
        eng = EvolutionEngine(dpi=cfg.simulation.dpi)
        return eng.evolve(
            run_id=rid,
            evo_dir=rdir / "evolution",
            benchmark_name=req.benchmark,
            generations=req.generations,
            num_islands=req.islands,
            seed=req.seed,
            llm_router=LLMRouter(cfg.llm),
        ).model_dump()

    @app.get("/api/v1/kb/stats")
    def api_kb_stats() -> dict:
        return LocalKBFederation(cfg).inspect_kb_stats()

    @app.post("/api/v1/kb/search")
    def api_kb_search(req: KBSearchRequest) -> dict:
        hits = LocalKBFederation(cfg).search_fts(req.query, limit=req.limit)
        return {"query": req.query, "hits": [h.model_dump() for h in hits]}

    @app.post("/api/v1/kb/link")
    def api_kb_link(req: KBSearchRequest) -> dict:
        store = WorkspaceStore(cfg.paths.runs_path, cfg.paths.state_db_path)
        rid = store.new_run_id("kb")
        rdir = store.prepare_run_dir(rid)
        return HybridKnowledgeGraph(cfg).link_and_analyze(rid, req.query, rdir / "knowledge").model_dump()

    @app.post("/api/v1/pipeline/run")
    def api_pipeline_run(req: PipelineRequest) -> dict:
        pipe = SciForgePipeline(cfg)
        return pipe.run(
            topic=req.topic,
            offline=req.offline,
            benchmark=req.benchmark,
            generations=req.generations,
            islands=req.islands,
            ppt_theme=req.theme,
            report_type=req.report_type,
        ).model_dump()

    @app.get("/api/v1/runs")
    def api_list_runs() -> dict:
        store = WorkspaceStore(cfg.paths.runs_path, cfg.paths.state_db_path)
        return {"runs": store.list_runs(limit=30)}

    @app.get("/api/v1/runs/{run_id}")
    def api_get_run(run_id: str) -> dict:
        store = WorkspaceStore(cfg.paths.runs_path, cfg.paths.state_db_path)
        row = store.get_run(run_id)
        if not row:
            raise HTTPException(status_code=404, detail="Run not found")
        return row

    return app
