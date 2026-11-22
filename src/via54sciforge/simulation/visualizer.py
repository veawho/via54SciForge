"""300-DPI bilingual publication chart generator using Matplotlib Agg backend."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from via54sciforge.core.models import EvidencePackage, ExperimentBranch, StatTestResult

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans", "Arial"]
plt.rcParams["axes.unicode_minus"] = False

PALETTE = ["#1B365D", "#008080", "#E07A5F", "#3D405B", "#81B29A", "#F2CC8F"]


def _save_fig(fig: plt.Figure, out_png: Path, dpi: int = 300) -> str:
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(out_png), dpi=dpi, bbox_inches="tight")
    fig.savefig(str(out_png.with_suffix(".svg")), bbox_inches="tight")
    plt.close(fig)
    return str(out_png)


def plot_ablation_comparison(
    branches: List[ExperimentBranch],
    stats_list: List[StatTestResult],
    out_png: Path,
    title: str = "Experiment Branch Ablation & 95% CI / 实验分支消融对比",
    dpi: int = 300,
) -> str:
    fig, ax = plt.subplots(figsize=(8.2, 4.8))
    labels = [b.label for b in branches]
    means = [float(b.metrics.get("primary_metric", 0.0)) for b in branches]
    stds = [float(b.metrics.get("primary_std", 0.0)) for b in branches]
    colors = [PALETTE[i % len(PALETTE)] for i in range(len(branches))]

    bars = ax.bar(range(len(labels)), means, yerr=stds, capsize=5, color=colors, edgecolor="#222222", alpha=0.9)
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=12, ha="right", fontsize=9.5)
    ax.set_ylabel("Primary Outcome Score / 核心评价指标", fontsize=10.5)
    ax.set_title(title, fontsize=12, fontweight="bold", pad=12)
    ax.grid(axis="y", linestyle="--", alpha=0.35)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    for bar, val in zip(bars, means):
        ax.text(bar.get_x() + bar.get_width() / 2, val + (max(stds) * 0.25 + 0.015), f"{val:.3f}", ha="center", va="bottom", fontsize=9, fontweight="bold")

    if stats_list:
        s0 = stats_list[0]
        note = f"{s0.test_name}: p={s0.p_value:.4g}, {s0.effect_size_name}={s0.effect_size:.3f}"
        ax.text(0.02, 0.94, note, transform=ax.transAxes, fontsize=8.8, bbox=dict(boxstyle="round,pad=0.35", facecolor="#F4F6F9", edgecolor="#CCCCCC"))

    return _save_fig(fig, out_png, dpi=dpi)


def plot_kaplan_meier(curves: Dict[str, Any], out_png: Path, dpi: int = 300) -> str:
    fig, ax = plt.subplots(figsize=(8.0, 4.8))
    trt = curves["treatment"]
    ctrl = curves["control"]
    ax.step(trt["t"], trt["s"], where="post", color=PALETTE[1], linewidth=2.3, label=f"Proposed Arm (median={trt['median']} mo)")
    ax.step(ctrl["t"], ctrl["s"], where="post", color=PALETTE[2], linewidth=2.3, linestyle="--", label=f"Control Arm (median={ctrl['median']} mo)")
    ax.set_xlabel("Time (Months) / 随访时间（月）", fontsize=10.5)
    ax.set_ylabel("Survival Probability / 生存概率", fontsize=10.5)
    ax.set_title(
        f"Kaplan-Meier Survival Analysis (HR={curves['hazard_ratio']}, p={curves['logrank_p']})",
        fontsize=11.5,
        fontweight="bold",
    )
    ax.set_ylim(0, 1.05)
    ax.grid(True, linestyle="--", alpha=0.35)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.legend(frameon=True, fontsize=9.5)
    return _save_fig(fig, out_png, dpi=dpi)


def plot_ode_trajectories(t: Sequence[float], base: Sequence[float], trt: Sequence[float], out_png: Path, dpi: int = 300) -> str:
    fig, ax = plt.subplots(figsize=(8.0, 4.6))
    ax.plot(t, base, color=PALETTE[2], linewidth=2.2, linestyle="--", label="Baseline Dynamics / 基线动力学")
    ax.plot(t, trt, color=PALETTE[1], linewidth=2.4, label="Intervention Dynamics / 干预后动力学")
    ax.fill_between(t, trt, base, color=PALETTE[4], alpha=0.22)
    ax.set_xlabel("Time Step / 时间步", fontsize=10.5)
    ax.set_ylabel("Infected / Active Fraction / 活跃比例", fontsize=10.5)
    ax.set_title("ODE Dynamical System Trajectory / 微分方程动力学对比轨迹", fontsize=11.5, fontweight="bold")
    ax.grid(True, linestyle="--", alpha=0.35)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.legend(fontsize=9.5)
    return _save_fig(fig, out_png, dpi=dpi)


def plot_evolution_trajectory(
    history: List[Dict[str, Any]],
    pareto: List[Any],
    out_png: Path,
    benchmark_name: str,
    dpi: int = 300,
) -> str:
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10.5, 4.3))
    gens = [h["generation"] for h in history]
    best_f = [h["best_fitness"] for h in history]
    mean_f = [h["mean_fitness"] for h in history]

    ax1.plot(gens, best_f, marker="o", color=PALETTE[0], linewidth=2.3, label="Global Best Fitness / 全局最优适应度")
    ax1.plot(gens, mean_f, marker="s", color=PALETTE[1], linewidth=1.8, linestyle="--", label="Archive Mean / 种群均值")
    ax1.set_xlabel("Generation / 进化代数", fontsize=10)
    ax1.set_ylabel("Fitness / 适应度", fontsize=10)
    ax1.set_title(f"Evolution Convergence ({benchmark_name})", fontsize=11, fontweight="bold")
    ax1.grid(True, linestyle="--", alpha=0.35)
    ax1.spines["top"].set_visible(False)
    ax1.spines["right"].set_visible(False)
    ax1.legend(fontsize=8.5)

    if pareto:
        xs = [getattr(c, "complexity", c.get("complexity", 0) if isinstance(c, dict) else 0) for c in pareto]
        ys = [getattr(c, "fitness", c.get("fitness", 0.0) if isinstance(c, dict) else 0.0) for c in pareto]
        ax2.scatter(xs, ys, color=PALETTE[2], s=70, edgecolor="#111111", zorder=3, label="Pareto Frontier / 帕累托前沿")
        order = np.argsort(xs)
        ax2.plot([xs[i] for i in order], [ys[i] for i in order], color=PALETTE[2], linestyle=":", linewidth=1.5)
    ax2.set_xlabel("AST Complexity / AST 复杂度", fontsize=10)
    ax2.set_ylabel("Fitness / 适应度", fontsize=10)
    ax2.set_title("Pareto Simplicity vs Accuracy / 复杂度-精度帕累托前沿", fontsize=11, fontweight="bold")
    ax2.grid(True, linestyle="--", alpha=0.35)
    ax2.spines["top"].set_visible(False)
    ax2.spines["right"].set_visible(False)
    if pareto:
        ax2.legend(fontsize=8.5)

    return _save_fig(fig, out_png, dpi=dpi)


def plot_literature_landscape(evidence: EvidencePackage, out_png: Path, dpi: int = 300) -> str:
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10.2, 4.2))
    years = [p.year for p in evidence.papers if p.year > 1990]
    if years:
        uniq_y, counts_y = np.unique(years, return_counts=True)
        ax1.bar([str(y) for y in uniq_y], counts_y, color=PALETTE[0], alpha=0.88)
    ax1.set_title("Publication Year Distribution / 纳入文献年份分布", fontsize=10.5, fontweight="bold")
    ax1.set_ylabel("Paper Count / 文献数量", fontsize=9.5)
    ax1.grid(axis="y", linestyle="--", alpha=0.35)
    ax1.spines["top"].set_visible(False)
    ax1.spines["right"].set_visible(False)

    srcs = evidence.sources_used or {"corpus": len(evidence.papers)}
    names = list(srcs.keys())
    vals = [srcs[k] for k in names]
    ax2.barh(names, vals, color=PALETTE[1], alpha=0.88)
    ax2.set_title("Multi-Source Retrieval Yield / 多源检索命中分布", fontsize=10.5, fontweight="bold")
    ax2.set_xlabel("Hits / 命中数", fontsize=9.5)
    ax2.grid(axis="x", linestyle="--", alpha=0.35)
    ax2.spines["top"].set_visible(False)
    ax2.spines["right"].set_visible(False)

    return _save_fig(fig, out_png, dpi=dpi)
