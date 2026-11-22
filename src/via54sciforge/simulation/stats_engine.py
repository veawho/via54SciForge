"""SciPy/NumPy statistical hypothesis testing, bootstrap CIs, FDR correction & Kaplan-Meier log-rank."""

from __future__ import annotations

from typing import Any, Dict, List, Sequence, Tuple

import numpy as np
from scipy import stats

from via54sciforge.core.models import StatTestResult


def cohens_d(a: Sequence[float], b: Sequence[float]) -> float:
    arr_a = np.asarray(a, dtype=float)
    arr_b = np.asarray(b, dtype=float)
    if len(arr_a) < 2 or len(arr_b) < 2:
        return 0.0
    var_a = np.var(arr_a, ddof=1)
    var_b = np.var(arr_b, ddof=1)
    pooled = np.sqrt(((len(arr_a) - 1) * var_a + (len(arr_b) - 1) * var_b) / (len(arr_a) + len(arr_b) - 2))
    if pooled <= 1e-12:
        return 0.0
    return float((np.mean(arr_a) - np.mean(arr_b)) / pooled)


def bootstrap_mean_diff_ci(
    a: Sequence[float], b: Sequence[float], n_boot: int = 1500, alpha: float = 0.05, seed: int = 42
) -> Tuple[float, float]:
    rng = np.random.default_rng(seed)
    arr_a = np.asarray(a, dtype=float)
    arr_b = np.asarray(b, dtype=float)
    idx_a = rng.integers(0, len(arr_a), size=(n_boot, len(arr_a)))
    idx_b = rng.integers(0, len(arr_b), size=(n_boot, len(arr_b)))
    diffs = arr_a[idx_a].mean(axis=1) - arr_b[idx_b].mean(axis=1)
    low, high = np.percentile(diffs, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return float(round(low, 4)), float(round(high, 4))


def welch_t_test(treatment: Sequence[float], baseline: Sequence[float], seed: int = 42) -> StatTestResult:
    arr_t = np.asarray(treatment, dtype=float)
    arr_b = np.asarray(baseline, dtype=float)
    t_stat, p_val = stats.ttest_ind(arr_t, arr_b, equal_var=False)
    d = cohens_d(arr_t, arr_b)
    ci_low, ci_high = bootstrap_mean_diff_ci(arr_t, arr_b, seed=seed)
    sig = bool(p_val < 0.05)
    return StatTestResult(
        test_name="Welch t-test + Bootstrap 95% CI",
        statistic=round(float(t_stat), 4),
        p_value=round(float(p_val), 6),
        effect_size=round(d, 4),
        effect_size_name="cohens_d",
        ci_low=ci_low,
        ci_high=ci_high,
        significant_at_05=sig,
        interpretation_en=(
            f"Mean delta={np.mean(arr_t) - np.mean(arr_b):.4f} (95% CI [{ci_low}, {ci_high}]), "
            f"t={t_stat:.3f}, p={p_val:.5f}, Cohen's d={d:.3f} ({'significant' if sig else 'non-significant'})."
        ),
        interpretation_zh=(
            f"均值差={np.mean(arr_t) - np.mean(arr_b):.4f}（95% CI [{ci_low}, {ci_high}]），"
            f"t={t_stat:.3f}，p={p_val:.5f}，Cohen's d={d:.3f}（{'统计学显著' if sig else '未达显著'}）。"
        ),
    )


def mann_whitney_u(treatment: Sequence[float], baseline: Sequence[float]) -> StatTestResult:
    arr_t = np.asarray(treatment, dtype=float)
    arr_b = np.asarray(baseline, dtype=float)
    u_stat, p_val = stats.mannwhitneyu(arr_t, arr_b, alternative="two-sided")
    # Rank-biserial correlation effect size
    n1, n2 = len(arr_t), len(arr_b)
    rb = float((2.0 * u_stat) / (n1 * n2) - 1.0)
    sig = bool(p_val < 0.05)
    return StatTestResult(
        test_name="Mann-Whitney U (non-parametric)",
        statistic=round(float(u_stat), 4),
        p_value=round(float(p_val), 6),
        effect_size=round(rb, 4),
        effect_size_name="rank_biserial_r",
        significant_at_05=sig,
        interpretation_en=f"U={u_stat:.2f}, p={p_val:.5f}, rank-biserial r={rb:.3f}.",
        interpretation_zh=f"U={u_stat:.2f}，p={p_val:.5f}，秩双列相关 r={rb:.3f}。",
    )


def one_way_anova(*groups: Sequence[float]) -> StatTestResult:
    f_stat, p_val = stats.f_oneway(*groups)
    all_vals = np.concatenate([np.asarray(g, dtype=float) for g in groups])
    grand_mean = np.mean(all_vals)
    ss_between = sum(len(g) * (np.mean(g) - grand_mean) ** 2 for g in groups)
    ss_total = np.sum((all_vals - grand_mean) ** 2) or 1e-12
    eta_sq = float(ss_between / ss_total)
    sig = bool(p_val < 0.05)
    return StatTestResult(
        test_name="One-way ANOVA",
        statistic=round(float(f_stat), 4),
        p_value=round(float(p_val), 6),
        effect_size=round(eta_sq, 4),
        effect_size_name="eta_squared",
        significant_at_05=sig,
        interpretation_en=f"F={f_stat:.3f}, p={p_val:.5f}, eta^2={eta_sq:.3f}.",
        interpretation_zh=f"F={f_stat:.3f}，p={p_val:.5f}，偏 Eta 方={eta_sq:.3f}。",
    )


def benjamini_hochberg_fdr(results: List[StatTestResult]) -> List[StatTestResult]:
    """Apply Benjamini-Hochberg FDR adjustment across multiple hypothesis tests in place."""
    if not results:
        return results
    m = len(results)
    indexed = sorted(enumerate(results), key=lambda x: x[1].p_value)
    q_vals = [0.0] * m
    running_min = 1.0
    for rank_rev in range(m - 1, -1, -1):
        orig_idx, res = indexed[rank_rev]
        rank = rank_rev + 1
        raw_q = res.p_value * m / rank
        running_min = min(running_min, raw_q)
        q_vals[orig_idx] = round(min(1.0, running_min), 6)
    for idx, q in enumerate(q_vals):
        results[idx].fdr_q_value = q
    return results


def kaplan_meier_curve(times: Sequence[float], events: Sequence[int]) -> Tuple[List[float], List[float], float]:
    """Compute step-wise Kaplan-Meier survival curve (t, S(t)) and median survival."""
    t_arr = np.asarray(times, dtype=float)
    e_arr = np.asarray(events, dtype=int)
    order = np.argsort(t_arr)
    t_arr, e_arr = t_arr[order], e_arr[order]

    unique_times = np.unique(t_arr[e_arr == 1])
    xs = [0.0]
    ys = [1.0]
    surv = 1.0
    median = float(np.max(t_arr))
    median_found = False

    for t in unique_times:
        at_risk = int(np.sum(t_arr >= t))
        died = int(np.sum((t_arr == t) & (e_arr == 1)))
        if at_risk > 0:
            surv *= (1.0 - died / at_risk)
        xs.extend([float(t), float(t)])
        ys.extend([ys[-1], float(surv)])
        if not median_found and surv <= 0.5:
            median = float(t)
            median_found = True

    xs.append(float(np.max(t_arr)))
    ys.append(ys[-1])
    return xs, ys, round(median, 3)


def kaplan_meier_and_logrank(
    times_treat: Sequence[float],
    events_treat: Sequence[int],
    times_ctrl: Sequence[float],
    events_ctrl: Sequence[int],
) -> Tuple[StatTestResult, Dict[str, Any]]:
    """Compute Kaplan-Meier curves and exact Mantel-Haenszel log-rank test."""
    t1 = np.asarray(times_treat, dtype=float)
    e1 = np.asarray(events_treat, dtype=int)
    t0 = np.asarray(times_ctrl, dtype=float)
    e0 = np.asarray(events_ctrl, dtype=int)

    all_event_times = np.unique(np.concatenate([t1[e1 == 1], t0[e0 == 1]]))
    obs_1 = 0.0
    exp_1 = 0.0
    var_sum = 0.0

    for t in all_event_times:
        n1 = float(np.sum(t1 >= t))
        n0 = float(np.sum(t0 >= t))
        n = n1 + n0
        if n <= 1.0:
            continue
        d1 = float(np.sum((t1 == t) & (e1 == 1)))
        d0 = float(np.sum((t0 == t) & (e0 == 1)))
        d = d1 + d0
        expected = d * (n1 / n)
        variance = (n1 * n0 * d * (n - d)) / (n * n * (n - 1.0))
        obs_1 += d1
        exp_1 += expected
        var_sum += variance

    chi2 = ((obs_1 - exp_1) ** 2) / max(var_sum, 1e-12)
    p_val = float(stats.chi2.sf(chi2, df=1))
    obs_0 = float(np.sum(e0))
    exp_0 = obs_0 + obs_1 - exp_1
    hr = (obs_1 / max(exp_1, 1e-9)) / max(obs_0 / max(exp_0, 1e-9), 1e-9)

    xs_t, ys_t, med_t = kaplan_meier_curve(t1, e1)
    xs_c, ys_c, med_c = kaplan_meier_curve(t0, e0)

    stat_res = StatTestResult(
        test_name="Mantel-Haenszel Log-Rank Test",
        statistic=round(float(chi2), 4),
        p_value=round(p_val, 6),
        effect_size=round(float(hr), 4),
        effect_size_name="hazard_ratio",
        significant_at_05=bool(p_val < 0.05),
        interpretation_en=f"Log-rank chi2={chi2:.3f}, p={p_val:.5f}, HR={hr:.3f}, median survival {med_t} vs {med_c} mo.",
        interpretation_zh=f"Log-rank 卡方={chi2:.3f}，p={p_val:.5f}，风险比 HR={hr:.3f}，中位生存 {med_t} vs {med_c} 月。",
    )
    curves = {
        "treatment": {"t": xs_t, "s": ys_t, "median": med_t},
        "control": {"t": xs_c, "s": ys_c, "median": med_c},
        "hazard_ratio": round(float(hr), 4),
        "logrank_p": round(p_val, 6),
    }
    return stat_res, curves


def monte_carlo_power_analysis(
    effect_size: float, n_per_arm: int, alpha: float = 0.05, n_sim: int = 500, seed: int = 42
) -> float:
    """Estimate statistical power via Monte Carlo simulation."""
    rng = np.random.default_rng(seed)
    hits = 0
    for _ in range(n_sim):
        ctrl = rng.normal(0.0, 1.0, size=n_per_arm)
        trt = rng.normal(effect_size, 1.0, size=n_per_arm)
        _, p = stats.ttest_ind(trt, ctrl, equal_var=False)
        if p < alpha:
            hits += 1
    return round(hits / n_sim, 4)


def linear_regression_summary(x: Sequence[float], y: Sequence[float]) -> Dict[str, float]:
    res = stats.linregress(np.asarray(x, dtype=float), np.asarray(y, dtype=float))
    spear_r, spear_p = stats.spearmanr(x, y)
    return {
        "slope": round(float(res.slope), 5),
        "intercept": round(float(res.intercept), 5),
        "r_squared": round(float(res.rvalue ** 2), 5),
        "p_value": round(float(res.pvalue), 6),
        "spearman_rho": round(float(spear_r), 5),
        "spearman_p": round(float(spear_p), 6),
    }
