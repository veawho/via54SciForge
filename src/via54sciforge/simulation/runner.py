"""Progressive multi-branch experiment manager executing hypothesis-driven simulations."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from via54sciforge.core.models import (
    ExperimentBranch,
    ExperimentRun,
    ExperimentSpec,
    Hypothesis,
)
from via54sciforge.simulation.sandbox import run_in_sandbox
from via54sciforge.simulation.stats_engine import (
    benjamini_hochberg_fdr,
    kaplan_meier_and_logrank,
    mann_whitney_u,
    welch_t_test,
)
from via54sciforge.simulation.templates import build_template_script
from via54sciforge.simulation.visualizer import (
    plot_ablation_comparison,
    plot_kaplan_meier,
    plot_ode_trajectories,
)


def resolve_template_name(spec: ExperimentSpec, hypothesis: Optional[Hypothesis] = None, topic: str = "") -> str:
    if spec.template != "auto":
        return spec.template
    if hypothesis and hypothesis.recommended_sim_template:
        return hypothesis.recommended_sim_template
    q = topic.lower()
    if any(k in q for k in ("clinical", "trial", "survival", "cancer", "hcc", "rct", "临床", "生存")):
        return "clinical_rct_monte_carlo"
    if any(k in q for k in ("ode", "kinetic", "epidemic", "differential")):
        return "ode_dynamical_system"
    if any(k in q for k in ("network", "graph", "diffusion", "cascade", "knowledge graph")):
        return "network_diffusion_abm"
    return "ml_ablation_benchmark"


class ExperimentManager:
    """Runs baseline + controlled ablation/sensitivity branches in AST-validated sandbox."""

    def __init__(self, timeout_s: int = 30, dpi: int = 300):
        self.timeout_s = timeout_s
        self.dpi = dpi

    def run_experiment(
        self,
        run_id: str,
        sim_dir: Path,
        spec: ExperimentSpec,
        hypothesis: Optional[Hypothesis] = None,
        topic: str = "",
    ) -> ExperimentRun:
        sim_dir.mkdir(parents=True, exist_ok=True)
        template_name = resolve_template_name(spec, hypothesis, topic)

        branch_configs = self._build_branch_configs(template_name, spec.params)
        branches: List[ExperimentBranch] = []
        raw_by_branch: Dict[str, Dict[str, Any]] = {}
        repro_script_path = ""

        for idx, (b_id, label, b_params) in enumerate(branch_configs):
            code = spec.custom_code if (spec.custom_code and idx == 0) else build_template_script(template_name, seed=spec.seed + idx, params=b_params)
            b_dir = sim_dir / b_id
            res = run_in_sandbox(code, b_dir, script_name=f"{b_id}.py", timeout_s=self.timeout_s, seed=spec.seed + idx)
            trt_vals = res.metrics.get("treatment_values", [])
            base_vals = res.metrics.get("baseline_values", [])
            prim_val = float(res.metrics.get("primary_metric", np.mean(trt_vals) if trt_vals else 0.0))
            prim_std = float(np.std(trt_vals, ddof=1)) if len(trt_vals) > 1 else 0.0
            base_val = float(res.metrics.get("baseline_metric", np.mean(base_vals) if base_vals else 0.0))

            branches.append(
                ExperimentBranch(
                    branch_id=b_id,
                    label=label,
                    params=b_params,
                    metrics={
                        "primary_metric": round(prim_val, 4),
                        "primary_std": round(prim_std, 4),
                        "baseline_metric": round(base_val, 4),
                        "delta": round(prim_val - base_val, 4),
                    },
                    elapsed_s=res.elapsed_s,
                    returncode=res.returncode,
                    stdout_tail=(res.stdout or res.stderr)[-300:],
                    script_path=res.script_path,
                )
            )
            raw_by_branch[b_id] = res.metrics
            if idx == 0:
                repro_script_path = res.script_path

        # Pick winning branch
        valid_branches = [b for b in branches if b.returncode == 0]
        winner = max(valid_branches or branches, key=lambda b: b.metrics.get("primary_metric", -1e9))
        win_raw = raw_by_branch.get(winner.branch_id, {})

        # Statistical verification against baseline
        stats_list = []
        figure_paths: List[str] = []
        trt_arr = win_raw.get("treatment_values", [])
        base_arr = win_raw.get("baseline_values", [])
        if len(trt_arr) >= 3 and len(base_arr) >= 3:
            stats_list.append(welch_t_test(trt_arr, base_arr, seed=spec.seed))
            stats_list.append(mann_whitney_u(trt_arr, base_arr))

        raw_series: Dict[str, Any] = {}
        if template_name == "clinical_rct_monte_carlo" and win_raw.get("times_treat"):
            lr_stat, km_curves = kaplan_meier_and_logrank(
                win_raw["times_treat"], win_raw["events_treat"], win_raw["times_ctrl"], win_raw["events_ctrl"]
            )
            stats_list.append(lr_stat)
            raw_series["kaplan_meier"] = km_curves
            figure_paths.append(plot_kaplan_meier(km_curves, sim_dir / "fig_kaplan_meier.png", dpi=self.dpi))
        elif template_name == "ode_dynamical_system" and win_raw.get("t"):
            raw_series["ode"] = {"t": win_raw["t"], "I_base": win_raw["I_base"], "I_trt": win_raw["I_trt"]}
            figure_paths.append(
                plot_ode_trajectories(win_raw["t"], win_raw["I_base"], win_raw["I_trt"], sim_dir / "fig_ode_dynamics.png", dpi=self.dpi)
            )

        benjamini_hochberg_fdr(stats_list)
        figure_paths.append(plot_ablation_comparison(branches, stats_list, sim_dir / "fig_ablation_comparison.png", dpi=self.dpi))

        (sim_dir / "stats_report.json").write_text(
            json.dumps([s.model_dump() for s in stats_list], ensure_ascii=False, indent=2), encoding="utf-8"
        )

        s0 = stats_list[0] if stats_list else None
        summary_en = (
            f"Executed {len(branches)} sandboxed branches using template '{template_name}'. "
            f"Winner '{winner.label}' achieved primary={winner.metrics['primary_metric']:.4f} vs baseline="
            f"{winner.metrics['baseline_metric']:.4f} (delta={winner.metrics['delta']:+.4f}"
            + (f", {s0.test_name}: p={s0.p_value:.5f}, q={s0.fdr_q_value}" if s0 else "")
            + ")."
        )
        summary_zh = (
            f"基于沙箱模板 `{template_name}` 完成 {len(branches)} 个对照/消融分支实验。"
            f"最优分支“{winner.label}”主指标达 {winner.metrics['primary_metric']:.4f}（基线 {winner.metrics['baseline_metric']:.4f}，"
            f"净增益 {winner.metrics['delta']:+.4f}"
            + (f"，{s0.test_name} p={s0.p_value:.5f}，FDR q={s0.fdr_q_value}" if s0 else "")
            + "）。"
        )

        return ExperimentRun(
            run_id=run_id,
            spec=spec,
            resolved_template=template_name,
            branches=branches,
            winning_branch_id=winner.branch_id,
            stats=stats_list,
            figure_paths=figure_paths,
            reproducible_script_path=repro_script_path,
            raw_series=raw_series,
            summary_en=summary_en,
            summary_zh=summary_zh,
        )

    @staticmethod
    def _build_branch_configs(template: str, base_params: Dict[str, Any]) -> List[tuple[str, str, Dict[str, Any]]]:
        if template == "clinical_rct_monte_carlo":
            return [
                ("branch_main", "Primary Hybrid Regimen / 主方案", {**base_params, "true_hr": 0.64}),
                ("branch_ablation", "Reduced Intensity / 减量消融", {**base_params, "true_hr": 0.78}),
                ("branch_high_n", "Expanded Cohort (N=240) / 扩样本敏感性", {**base_params, "true_hr": 0.66, "n_per_arm": 240}),
            ]
        if template == "ode_dynamical_system":
            return [
                ("branch_main", "Targeted Intervention (38%) / 目标干预", {**base_params, "intervention_suppression": 0.38}),
                ("branch_ablation", "Partial Intervention (18%) / 部分消融", {**base_params, "intervention_suppression": 0.18}),
                ("branch_strong", "Intensive Intervention (52%) / 强化敏感性", {**base_params, "intervention_suppression": 0.52}),
            ]
        if template == "network_diffusion_abm":
            return [
                ("branch_main", "PPR Hub Suppression (45%) / PPR 枢纽干预", {**base_params, "hub_mitigation": 0.45}),
                ("branch_ablation", "Weak Suppression (20%) / 弱干预消融", {**base_params, "hub_mitigation": 0.20}),
                ("branch_strong", "Strict Hub Shielding (70%) / 强屏蔽敏感性", {**base_params, "hub_mitigation": 0.70}),
            ]
        return [
            ("branch_main", "Hybrid Prior-Guided / 混合先验主方案", {**base_params, "prior_weight": 0.45, "noise_scale": 0.22}),
            ("branch_ablation", "Weak Prior Ablation / 弱先验消融", {**base_params, "prior_weight": 0.10, "noise_scale": 0.22}),
            ("branch_noisy", "High-Noise Stress / 高噪鲁棒性测试", {**base_params, "prior_weight": 0.45, "noise_scale": 0.35}),
        ]
