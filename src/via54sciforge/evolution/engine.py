"""Main MAP-Elites + multi-island + UCB1 bandit evolution engine."""

from __future__ import annotations

import random
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from via54sciforge.core.llm import LLMRouter
from via54sciforge.core.models import EvolutionCandidate, EvolutionRunResult
from via54sciforge.core.storage import atomic_write_json, atomic_write_text
from via54sciforge.evolution.archive import (
    MAPElitesIslandArchive,
    compute_code_hash,
)
from via54sciforge.evolution.benchmarks import get_benchmark
from via54sciforge.evolution.mutators import (
    UCB1OperatorBandit,
    ast_complexity,
    mutate_basis_expansion,
    mutate_crossover_blend,
    mutate_llm_diff,
    mutate_numeric_perturbation,
    mutate_structural_expansion,
)
from via54sciforge.simulation.sandbox import run_in_sandbox
from via54sciforge.simulation.visualizer import plot_evolution_trajectory


class EvolutionEngine:
    """Orchestrates multi-island evolutionary algorithm discovery with sandbox verification."""

    def __init__(self, timeout_s: int = 15, dpi: int = 300):
        self.timeout_s = timeout_s
        self.dpi = dpi

    def evolve(
        self,
        run_id: str,
        evo_dir: Path,
        benchmark_name: str = "symbolic_discovery",
        generations: int = 10,
        population_per_gen: int = 4,
        num_islands: int = 3,
        migration_interval: int = 3,
        novelty_threshold: float = 0.04,
        seed: int = 42,
        llm_router: Optional[LLMRouter] = None,
        seed_file: Optional[Path] = None,
        eval_file: Optional[Path] = None,
    ) -> EvolutionRunResult:
        evo_dir.mkdir(parents=True, exist_ok=True)
        bench = get_benchmark(benchmark_name, seed_file=seed_file, eval_file=eval_file)
        rng = random.Random(seed)
        archive = MAPElitesIslandArchive(
            db_path=evo_dir / "evolution_archive.db",
            num_islands=num_islands,
            novelty_threshold=novelty_threshold,
        )

        operators = ["numeric_perturb", "basis_expansion", "structural_tune", "crossover_blend", "llm_diff"]
        bandit = UCB1OperatorBandit(operators)

        total_evals = 0
        rejected_novelty = 0
        history: List[Dict[str, Any]] = []

        # Evaluate Gen 0 seed baseline across all islands
        seed_eval = self._evaluate_code(
            code=bench.seed_code,
            eval_suffix=bench.eval_suffix,
            work_dir=evo_dir / "eval_sandbox",
            cand_id=f"cand_gen0_{uuid.uuid4().hex[:6]}",
            generation=0,
            island_id=0,
            parent_id=None,
            operator="seed",
            novelty=1.0,
            archive=archive,
            seed=seed,
        )
        total_evals += 1
        for isl in range(num_islands):
            clone = seed_eval.model_copy(
                update={"candidate_id": f"cand_gen0_i{isl}", "island_id": isl}
            )
            archive.add(clone)

        seed_fitness = seed_eval.fitness
        history.append({"generation": 0, "best_fitness": seed_fitness, "mean_fitness": seed_fitness, "archive_size": num_islands})

        for gen in range(1, generations + 1):
            for isl in range(num_islands):
                for slot in range(population_per_gen):
                    parent = archive.sample_parent(isl, rng)
                    if parent is None:
                        continue
                    op = bandit.select(rng)
                    inspirations = archive.sample_inspirations(isl, k=2)

                    if op == "numeric_perturb":
                        new_code = mutate_numeric_perturbation(parent.code, rng)
                        used_op = op
                    elif op == "basis_expansion":
                        new_code = mutate_basis_expansion(parent.code, rng)
                        used_op = op
                    elif op == "structural_tune":
                        new_code = mutate_structural_expansion(parent.code, rng)
                        used_op = op
                    elif op == "crossover_blend":
                        new_code = mutate_crossover_blend(parent, inspirations, rng)
                        used_op = op
                    else:
                        new_code, used_op = mutate_llm_diff(parent, inspirations, bench.objective_en, llm_router, rng)

                    novelty = archive.min_novelty_to_island(new_code, isl)
                    if novelty < novelty_threshold:
                        # Force structural variation if stuck
                        new_code = mutate_numeric_perturbation(new_code, rng, scale=0.65)
                        novelty = archive.min_novelty_to_island(new_code, isl)
                        if novelty < novelty_threshold:
                            rejected_novelty += 1
                            bandit.update(op, parent.fitness, parent.fitness, valid=False)
                            continue

                    cand = self._evaluate_code(
                        code=new_code,
                        eval_suffix=bench.eval_suffix,
                        work_dir=evo_dir / "eval_sandbox",
                        cand_id=f"cand_g{gen}_i{isl}_{slot}_{uuid.uuid4().hex[:5]}",
                        generation=gen,
                        island_id=isl,
                        parent_id=parent.candidate_id,
                        operator=used_op,
                        novelty=round(novelty, 4),
                        archive=archive,
                        seed=seed + total_evals,
                    )
                    total_evals += 1
                    archive.add(cand)
                    bandit.update(op, parent.fitness, cand.fitness, valid=cand.valid)

            if migration_interval > 0 and gen % migration_interval == 0:
                archive.migrate_ring(gen)

            all_elites = [c for g in archive.islands for c in g.values()]
            best_now = max((c.fitness for c in all_elites), default=seed_fitness)
            mean_now = sum(c.fitness for c in all_elites) / max(len(all_elites), 1)
            history.append(
                {
                    "generation": gen,
                    "best_fitness": round(best_now, 6),
                    "mean_fitness": round(mean_now, 6),
                    "archive_size": len(all_elites),
                }
            )

        best = archive.best_overall() or seed_eval
        pareto = archive.pareto_front()
        improvement_pct = (
            round(((best.fitness - seed_fitness) / max(abs(seed_fitness), 1e-9)) * 100.0, 2)
            if seed_fitness != 0
            else round(best.fitness * 100.0, 2)
        )

        best_code_path = atomic_write_text(evo_dir / "best_algorithm.py", best.code)
        chart_path = plot_evolution_trajectory(
            history, pareto, evo_dir / "fig_evolution_trajectory.png", bench.name, dpi=self.dpi
        )

        summary_en = (
            f"Completed {generations} generations across {num_islands} islands on '{bench.name}' "
            f"({total_evals} sandbox evaluations, {rejected_novelty} novelty-rejected). "
            f"Fitness evolved from {seed_fitness:.4f} -> {best.fitness:.4f} ({improvement_pct:+.2f}%)."
        )
        summary_zh = (
            f"在基准 `{bench.name}` 上完成 {num_islands} 岛 {generations} 代进化（共沙箱评测 {total_evals} 次，"
            f"新颖性过滤 {rejected_novelty} 次），最优适应度由 {seed_fitness:.4f} 提升至 {best.fitness:.4f}（{improvement_pct:+.2f}%）。"
        )

        result = EvolutionRunResult(
            run_id=run_id,
            benchmark_name=bench.name,
            generations=generations,
            num_islands=num_islands,
            total_evaluations=total_evals,
            rejected_novelty=rejected_novelty,
            seed_fitness=round(seed_fitness, 6),
            best_candidate=best,
            improvement_pct=improvement_pct,
            pareto_front=pareto,
            island_stats=archive.island_stats(),
            history=history,
            best_code_path=str(best_code_path),
            archive_db_path=str(archive.db_path),
            chart_path=chart_path,
            summary_en=summary_en,
            summary_zh=summary_zh,
        )
        atomic_write_json(evo_dir / "evolution_summary.json", result)
        return result

    def _evaluate_code(
        self,
        code: str,
        eval_suffix: str,
        work_dir: Path,
        cand_id: str,
        generation: int,
        island_id: int,
        parent_id: Optional[str],
        operator: str,
        novelty: float,
        archive: MAPElitesIslandArchive,
        seed: int,
    ) -> EvolutionCandidate:
        full_script = f"{code}\n\n{eval_suffix}\n"
        res = run_in_sandbox(full_script, work_dir, script_name="eval_cand.py", timeout_s=self.timeout_s, seed=seed)
        comp = ast_complexity(code)
        runtime_ms = round(res.elapsed_s * 1000.0, 2)
        bx, by = archive.compute_bins(comp, runtime_ms)
        fitness = float(res.metrics.get("fitness", 0.0)) if res.ok else 0.0
        return EvolutionCandidate(
            candidate_id=cand_id,
            generation=generation,
            island_id=island_id,
            parent_id=parent_id,
            operator=operator,
            code=code,
            fitness=round(fitness, 6),
            behavioral_coords=[bx, by],
            complexity=comp,
            runtime_ms=runtime_ms,
            novelty_score=novelty,
            code_hash=compute_code_hash(code),
            metrics=res.metrics,
            valid=res.ok,
            error=(res.stderr[:240] if not res.ok else ""),
        )
