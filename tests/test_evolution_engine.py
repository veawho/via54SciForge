"""Tests for Pillar 4: MAP-Elites multi-island algorithm evolution, UCB1 bandit & diff mutator."""

from pathlib import Path

from via54sciforge.evolution.engine import EvolutionEngine
from via54sciforge.evolution.mutators import UCB1OperatorBandit, apply_search_replace_diff


def test_search_replace_diff_patcher():
    orig = "def f(x):\n    return 0.5 * x\n"
    llm_resp = """
Here is the patch:
<<<<<<< SEARCH
    return 0.5 * x
=======
    return 1.2 * x + 0.3
>>>>>>> REPLACE
"""
    patched = apply_search_replace_diff(orig, llm_resp)
    assert patched is not None
    assert "1.2 * x + 0.3" in patched


def test_ucb1_bandit_updates():
    import random

    b = UCB1OperatorBandit(["op_a", "op_b"])
    rng = random.Random(42)
    picked = {b.select(rng) for _ in range(4)}
    assert "op_a" in picked or "op_b" in picked
    b.update("op_a", 1.0, 2.5, valid=True)
    b.update("op_b", 1.0, 0.8, valid=False)
    assert b.rewards["op_a"] > b.rewards["op_b"]


def test_evolution_improves_symbolic_discovery_and_circle_packing(tmp_path: Path):
    eng = EvolutionEngine(timeout_s=12, dpi=150)

    res_sym = eng.evolve(
        run_id="evo_sym",
        evo_dir=tmp_path / "sym",
        benchmark_name="symbolic_discovery",
        generations=6,
        population_per_gen=4,
        num_islands=3,
        seed=42,
    )
    assert res_sym.best_candidate.fitness > res_sym.seed_fitness
    assert res_sym.improvement_pct > 0.0
    assert Path(res_sym.best_code_path).exists()
    assert Path(res_sym.archive_db_path).exists()
    assert Path(res_sym.chart_path).exists()
    assert len(res_sym.pareto_front) >= 1

    res_cp = eng.evolve(
        run_id="evo_cp",
        evo_dir=tmp_path / "cp",
        benchmark_name="circle_packing",
        generations=4,
        population_per_gen=3,
        num_islands=2,
        seed=42,
    )
    assert res_cp.best_candidate.fitness >= res_cp.seed_fitness
    assert res_cp.best_candidate.valid is True
