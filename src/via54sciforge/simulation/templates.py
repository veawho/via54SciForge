"""Parameterized scientific simulation templates generating reproducible Python experiments."""

from __future__ import annotations

from textwrap import dedent
from typing import Any, Dict


def build_template_script(template: str, seed: int = 42, params: Dict[str, Any] | None = None) -> str:
    """Return a self-contained deterministic Python script writing metrics.json."""
    p = params or {}
    if template == "clinical_rct_monte_carlo":
        n_arm = int(p.get("n_per_arm", 160))
        hr_true = float(p.get("true_hr", 0.68))
        med_ctrl = float(p.get("median_control_mo", 14.5))
        return dedent(
            f"""
            import json, math
            import numpy as np

            rng = np.random.default_rng({seed})
            n_arm = {n_arm}
            med_ctrl = {med_ctrl}
            lam_ctrl = math.log(2.0) / med_ctrl
            lam_trt = lam_ctrl * {hr_true}

            t_ctrl_raw = rng.exponential(1.0 / lam_ctrl, size=n_arm)
            t_trt_raw = rng.exponential(1.0 / lam_trt, size=n_arm)
            censor_t = rng.uniform(18.0, 42.0, size=n_arm)
            censor_c = rng.uniform(18.0, 42.0, size=n_arm)

            times_trt = np.minimum(t_trt_raw, censor_t)
            events_trt = (t_trt_raw <= censor_t).astype(int)
            times_ctrl = np.minimum(t_ctrl_raw, censor_c)
            events_ctrl = (t_ctrl_raw <= censor_c).astype(int)

            # Continuous biomarker response score per arm
            biomarker_ctrl = rng.normal(0.42, 0.14, size=n_arm)
            biomarker_trt = rng.normal(0.58, 0.14, size=n_arm)

            out = {{
                "primary_metric": round(float(np.mean(biomarker_trt)), 4),
                "baseline_metric": round(float(np.mean(biomarker_ctrl)), 4),
                "treatment_values": [round(float(v), 5) for v in biomarker_trt.tolist()],
                "baseline_values": [round(float(v), 5) for v in biomarker_ctrl.tolist()],
                "times_treat": [round(float(v), 4) for v in times_trt.tolist()],
                "events_treat": events_trt.tolist(),
                "times_ctrl": [round(float(v), 4) for v in times_ctrl.tolist()],
                "events_ctrl": events_ctrl.tolist(),
                "n_per_arm": n_arm,
            }}
            with open("metrics.json", "w", encoding="utf-8") as f:
                json.dump(out, f)
            print("RCT simulation completed:", out["primary_metric"])
            """
        ).strip()

    if template == "ode_dynamical_system":
        beta = float(p.get("beta", 0.36))
        gamma = float(p.get("gamma", 0.12))
        intervention = float(p.get("intervention_suppression", 0.38))
        return dedent(
            f"""
            import json
            import numpy as np
            from scipy.integrate import solve_ivp

            def seir(t, y, beta, sigma, gamma):
                S, E, I, R = y
                dS = -beta * S * I
                dE = beta * S * I - sigma * E
                dI = sigma * E - gamma * I
                dR = gamma * I
                return [dS, dE, dI, dR]

            t_eval = np.linspace(0, 120, 121)
            y0 = [0.99, 0.005, 0.005, 0.0]
            sol_base = solve_ivp(seir, [0, 120], y0, args=({beta}, 0.25, {gamma}), t_eval=t_eval)
            sol_trt = solve_ivp(seir, [0, 120], y0, args=({beta} * (1.0 - {intervention}), 0.25, {gamma}), t_eval=t_eval)

            rng = np.random.default_rng({seed})
            # Replicated Monte Carlo trajectories under beta noise
            base_peaks = []
            trt_peaks = []
            for _ in range(24):
                b_n = max(0.05, {beta} + rng.normal(0.0, 0.025))
                sb = solve_ivp(seir, [0, 120], y0, args=(b_n, 0.25, {gamma}), t_eval=t_eval)
                st = solve_ivp(seir, [0, 120], y0, args=(b_n * (1.0 - {intervention}), 0.25, {gamma}), t_eval=t_eval)
                base_peaks.append(float(1.0 - np.max(sb.y[2])))
                trt_peaks.append(float(1.0 - np.max(st.y[2])))

            out = {{
                "primary_metric": round(float(np.mean(trt_peaks)), 4),
                "baseline_metric": round(float(np.mean(base_peaks)), 4),
                "peak_infected_base": round(float(np.max(sol_base.y[2])), 4),
                "peak_infected_trt": round(float(np.max(sol_trt.y[2])), 4),
                "treatment_values": [round(v, 5) for v in trt_peaks],
                "baseline_values": [round(v, 5) for v in base_peaks],
                "t": t_eval.tolist(),
                "I_base": [round(float(v), 5) for v in sol_base.y[2].tolist()],
                "I_trt": [round(float(v), 5) for v in sol_trt.y[2].tolist()],
            }}
            with open("metrics.json", "w", encoding="utf-8") as f:
                json.dump(out, f)
            print("ODE simulation completed:", out["primary_metric"])
            """
        ).strip()

    if template == "network_diffusion_abm":
        n_nodes = int(p.get("n_nodes", 90))
        mitigation = float(p.get("hub_mitigation", 0.45))
        return dedent(
            f"""
            import json
            import numpy as np
            import networkx as nx

            rng = np.random.default_rng({seed})
            G = nx.barabasi_albert_graph({n_nodes}, 3, seed={seed})
            pr = nx.pagerank(G, alpha=0.85)
            hubs = {{n for n, _ in sorted(pr.items(), key=lambda x: -x[1])[:max(3, {n_nodes} // 10)]}}

            def run_cascade(suppress_hubs: bool, runs: int = 24):
                scores = []
                for r in range(runs):
                    local_rng = np.random.default_rng({seed} + r * 17)
                    active = {{int(local_rng.integers(0, {n_nodes}))}}
                    for _step in range(8):
                        nxt = set(active)
                        for u in active:
                            for v in G.neighbors(u):
                                prob = 0.24 * (1.0 - {mitigation}) if (suppress_hubs and (u in hubs or v in hubs)) else 0.24
                                if local_rng.random() < prob:
                                    nxt.add(v)
                        active = nxt
                    scores.append(1.0 - len(active) / {n_nodes})
                return scores

            base_scores = run_cascade(False)
            trt_scores = run_cascade(True)
            out = {{
                "primary_metric": round(float(np.mean(trt_scores)), 4),
                "baseline_metric": round(float(np.mean(base_scores)), 4),
                "treatment_values": [round(float(v), 5) for v in trt_scores],
                "baseline_values": [round(float(v), 5) for v in base_scores],
                "hub_count": len(hubs),
            }}
            with open("metrics.json", "w", encoding="utf-8") as f:
                json.dump(out, f)
            print("Network diffusion ABM completed:", out["primary_metric"])
            """
        ).strip()

    # Default: ml_ablation_benchmark
    noise_scale = float(p.get("noise_scale", 0.22))
    prior_weight = float(p.get("prior_weight", 0.35))
    return dedent(
        f"""
        import json
        import numpy as np

        rng = np.random.default_rng({seed})
        n_trials = 30
        baseline_scores = []
        hybrid_scores = []

        for _ in range(n_trials):
            X = rng.normal(0.0, 1.0, size=(120, 6))
            true_w = np.array([1.2, -0.8, 0.6, 0.35, 0.0, 0.0])
            y = X @ true_w + rng.normal(0.0, {noise_scale}, size=120)
            X_tr, y_tr = X[:80], y[:80]
            X_te, y_te = X[80:], y[80:]

            # Baseline: unregularized OLS
            w_ols, *_ = np.linalg.lstsq(X_tr, y_tr, rcond=None)
            pred_ols = X_te @ w_ols
            r2_ols = 1.0 - np.sum((y_te - pred_ols) ** 2) / (np.sum((y_te - np.mean(y_te)) ** 2) + 1e-9)

            # Hybrid prior-guided ridge regularization
            lam = 6.0
            prior = np.array([1.0, -0.7, 0.5, 0.3, 0.0, 0.0]) * {prior_weight}
            A = X_tr.T @ X_tr + lam * np.eye(6)
            b = X_tr.T @ y_tr + lam * prior
            w_hyb = np.linalg.solve(A, b)
            pred_hyb = X_te @ w_hyb
            r2_hyb = 1.0 - np.sum((y_te - pred_hyb) ** 2) / (np.sum((y_te - np.mean(y_te)) ** 2) + 1e-9)

            baseline_scores.append(float(r2_ols))
            hybrid_scores.append(float(r2_hyb))

        out = {{
            "primary_metric": round(float(np.mean(hybrid_scores)), 4),
            "baseline_metric": round(float(np.mean(baseline_scores)), 4),
            "treatment_values": [round(v, 5) for v in hybrid_scores],
            "baseline_values": [round(v, 5) for v in baseline_scores],
        }}
        with open("metrics.json", "w", encoding="utf-8") as f:
            json.dump(out, f)
        print("ML ablation completed:", out["primary_metric"])
        """
    ).strip()
