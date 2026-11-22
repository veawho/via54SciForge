"""Tests for Pillar 3: AST sandbox safety, SciPy stats engine & multi-branch ExperimentManager."""

from pathlib import Path

from via54sciforge.core.models import ExperimentSpec
from via54sciforge.simulation.runner import ExperimentManager
from via54sciforge.simulation.sandbox import run_in_sandbox, validate_ast_safety
from via54sciforge.simulation.stats_engine import (
    benjamini_hochberg_fdr,
    kaplan_meier_and_logrank,
    monte_carlo_power_analysis,
    one_way_anova,
    welch_t_test,
)


def test_ast_sandbox_blocks_dangerous_code_and_allows_math(tmp_path: Path):
    unsafe_codes = [
        "import subprocess\nsubprocess.run(['dir'])",
        "import os\nos.system('echo hi')",
        "eval('1+1')",
        "x = ().__class__.__subclasses__()",
    ]
    for code in unsafe_codes:
        viols = validate_ast_safety(code)
        assert len(viols) >= 1
        res = run_in_sandbox(code, tmp_path / "bad")
        assert res.ok is False

    safe_code = """
import json, math
import numpy as np
vals = np.linspace(0, 1, 10)
with open("metrics.json", "w", encoding="utf-8") as f:
    json.dump({"mean": float(np.mean(vals)), "sqrt2": math.sqrt(2)}, f)
"""
    res = run_in_sandbox(safe_code, tmp_path / "good")
    assert res.ok is True
    assert abs(res.metrics["mean"] - 0.5) < 1e-6


def test_stats_engine_accuracy():
    a = [0.75, 0.78, 0.80, 0.77, 0.82, 0.79, 0.81, 0.76]
    b = [0.55, 0.58, 0.52, 0.60, 0.57, 0.54, 0.59, 0.56]
    wt = welch_t_test(a, b)
    assert wt.significant_at_05 is True
    assert wt.effect_size > 2.0
    assert wt.ci_low is not None and wt.ci_low > 0.1

    anova = one_way_anova(a, b, [0.65, 0.66, 0.64, 0.67, 0.65, 0.63])
    assert anova.significant_at_05 is True
    fdr = benjamini_hochberg_fdr([wt, anova])
    assert all(r.fdr_q_value is not None and r.fdr_q_value < 0.05 for r in fdr)

    lr, curves = kaplan_meier_and_logrank(
        [12, 18, 24, 30, 32, 28], [1, 0, 1, 0, 0, 1],
        [4, 6, 8, 10, 11, 12], [1, 1, 1, 1, 1, 1],
    )
    assert lr.p_value < 0.05
    assert curves["hazard_ratio"] < 1.0

    pwr = monte_carlo_power_analysis(effect_size=0.8, n_per_arm=30, n_sim=200)
    assert pwr >= 0.7


def test_experiment_manager_all_templates(tmp_path: Path):
    mgr = ExperimentManager(timeout_s=25, dpi=150)
    for tmpl in ("clinical_rct_monte_carlo", "ode_dynamical_system", "ml_ablation_benchmark", "network_diffusion_abm"):
        exp = mgr.run_experiment(
            run_id=f"test_{tmpl}",
            sim_dir=tmp_path / tmpl,
            spec=ExperimentSpec(template=tmpl, seed=42),
            topic="Biomedical Test",
        )
        assert exp.resolved_template == tmpl
        assert len(exp.branches) == 3
        assert all(b.returncode == 0 for b in exp.branches)
        assert len(exp.stats) >= 2
        assert len(exp.figure_paths) >= 1
        assert all(Path(fp).exists() for fp in exp.figure_paths)
