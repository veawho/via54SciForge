"""End-to-end 7-pillar orchestrator, FastAPI REST/Web UI, and MCP 2.x tool registration tests."""

from pathlib import Path

from fastapi.testclient import TestClient

from via54sciforge.core.config import SciForgeConfig
from via54sciforge.interfaces.api import create_app
from via54sciforge.interfaces.mcp_server import create_mcp_server
from via54sciforge.orchestrator.pipeline import SciForgePipeline


def test_full_7_pillar_offline_pipeline(tmp_path: Path):
    cfg = SciForgeConfig.load()
    cfg.paths.runs_dir = str(tmp_path / "runs")
    cfg.paths.state_db = str(tmp_path / "runs" / "state.db")

    pipe = SciForgePipeline(cfg)
    res = pipe.run(
        topic="Graph-Augmented Multi-Agent Scientific Discovery",
        offline=True,
        benchmark="symbolic_discovery",
        generations=5,
        islands=2,
        render_visuals=False,
    )
    assert len(res.stage_statuses) == 7
    assert all(v == "completed" for v in res.stage_statuses.values())
    assert res.evolution.improvement_pct > 0.0
    assert res.manuscript.citation_audit.grounding_rate == 1.0
    assert res.slides.slide_count == 12
    assert Path(res.summary_md_path).exists()
    assert Path(res.summary_json_path).exists()
    assert Path(res.report.html_path).exists()
    assert Path(res.slides.pptx_path).exists()


def test_fastapi_endpoints_and_workbench_ui(tmp_path: Path):
    cfg = SciForgeConfig.load()
    cfg.paths.runs_dir = str(tmp_path / "api_runs")
    cfg.paths.state_db = str(tmp_path / "api_runs" / "state.db")
    app = create_app(cfg)
    client = TestClient(app)

    r_home = client.get("/")
    assert r_home.status_code == 200
    assert "via54SciForge" in r_home.text

    r_health = client.get("/api/v1/health")
    assert r_health.status_code == 200 and r_health.json()["status"] == "ok"

    r_doc = client.get("/api/v1/doctor")
    assert r_doc.status_code == 200 and r_doc.json()["status"] == "ready"

    r_sim = client.post("/api/v1/simulate", json={"topic": "Test ODE", "template": "ode_dynamical_system", "seed": 42})
    assert r_sim.status_code == 200 and r_sim.json()["resolved_template"] == "ode_dynamical_system"

    r_evo = client.post("/api/v1/evolve", json={"benchmark": "symbolic_discovery", "generations": 4, "islands": 2})
    assert r_evo.status_code == 200 and r_evo.json()["improvement_pct"] > 0.0

    r_runs = client.get("/api/v1/runs")
    assert r_runs.status_code == 200


def test_mcp_server_registers_all_13_tools():
    server = create_mcp_server(SciForgeConfig.load())
    # Inspect registered tools via MCPServer internal tool manager
    tools = list(server._tool_manager._tools.keys())
    expected = {
        "sciforge_doctor",
        "sciforge_lit_search",
        "sciforge_pdf_audit",
        "sciforge_claim_verify",
        "sciforge_research_synthesize",
        "sciforge_simulate_experiment",
        "sciforge_evolve_algorithm",
        "sciforge_kb_stats",
        "sciforge_kb_search",
        "sciforge_kb_link_graph",
        "sciforge_write_paper",
        "sciforge_deliver_report_and_ppt",
        "sciforge_run_full_pipeline",
    }
    assert expected.issubset(set(tools))
