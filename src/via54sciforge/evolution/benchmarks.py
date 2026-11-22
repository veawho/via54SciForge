"""Self-contained scientific optimization benchmarks + custom file benchmark loader."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from textwrap import dedent


@dataclass
class EvolutionBenchmark:
    """Defines seed algorithm, evaluator wrapper, and optimization objective."""

    name: str
    objective_en: str
    objective_zh: str
    seed_code: str
    eval_suffix: str


SYMBOLIC_BENCHMARK = EvolutionBenchmark(
    name="symbolic_discovery",
    objective_en="Discover a compact symbolic/nonlinear law predict(x) minimizing RMSE on physical observations.",
    objective_zh="进化发现紧凑的非线性符号表达式 predict(x)，最小化观测曲线拟合误差 RMSE 并最大化 R²。",
    seed_code=dedent(
        """
        import math

        # EVOLVE-BLOCK-START
        def predict(x: float) -> float:
            return 0.45 * x + 0.25
        # EVOLVE-BLOCK-END
        """
    ).strip(),
    eval_suffix=dedent(
        """
        import json
        xs = [-2.0 + 4.0 * i / 59.0 for i in range(60)]
        ys = [1.85 * math.sin(1.4 * x) + 0.62 * (x ** 2) - 0.35 * x + 0.9 for x in xs]
        preds = [float(predict(x)) for x in xs]
        mse = sum((p - y) ** 2 for p, y in zip(preds, ys)) / len(ys)
        rmse = math.sqrt(mse)
        mean_y = sum(ys) / len(ys)
        sst = sum((y - mean_y) ** 2 for y in ys) or 1e-9
        r2 = 1.0 - sum((p - y) ** 2 for p, y in zip(preds, ys)) / sst
        # Higher fitness is better; max 10.0 at RMSE=0
        fitness = 10.0 / (1.0 + rmse)
        with open("metrics.json", "w", encoding="utf-8") as f:
            json.dump({"fitness": round(fitness, 6), "rmse": round(rmse, 6), "r2": round(r2, 6)}, f)
        """
    ).strip(),
)

CIRCLE_PACKING_BENCHMARK = EvolutionBenchmark(
    name="circle_packing",
    objective_en="Maximize sum of radii for N=10 non-overlapping circles inside the unit square [0,1]^2.",
    objective_zh="优化单位正方形 [0,1]^2 内 N=10 个互不重叠圆的填充策略，最大化半径总和。",
    seed_code=dedent(
        """
        import math

        # EVOLVE-BLOCK-START
        def pack_circles(n: int = 10):
            # Initial conservative grid placement + iterative growth/repulsion relaxation
            cols = 4
            centers = []
            for i in range(n):
                r_idx = i // cols
                c_idx = i % cols
                centers.append([0.16 + c_idx * 0.22, 0.18 + r_idx * 0.28])
            radii = [0.065 for _ in range(n)]
            grow = 1.012
            step = 0.012
            for _it in range(35):
                for i in range(n):
                    x, y = centers[i]
                    cand_r = min(radii[i] * grow, x, 1.0 - x, y, 1.0 - y)
                    ok = True
                    for j in range(n):
                        if i == j:
                            continue
                        dx = x - centers[j][0]
                        dy = y - centers[j][1]
                        dist = math.hypot(dx, dy)
                        if dist < cand_r + radii[j] + 1e-4:
                            ok = False
                            if dist > 1e-6:
                                centers[i][0] = min(0.95, max(0.05, x + step * dx / dist))
                                centers[i][1] = min(0.95, max(0.05, y + step * dy / dist))
                    if ok:
                        radii[i] = cand_r
            return centers, radii
        # EVOLVE-BLOCK-END
        """
    ).strip(),
    eval_suffix=dedent(
        """
        import json
        centers, radii = pack_circles(10)
        assert len(centers) == 10 and len(radii) == 10
        valid = True
        for i in range(10):
            x, y = centers[i]
            r = radii[i]
            if r <= 0 or x - r < -1e-6 or x + r > 1.0 + 1e-6 or y - r < -1e-6 or y + r > 1.0 + 1e-6:
                valid = False
            for j in range(i + 1, 10):
                d = math.hypot(x - centers[j][0], y - centers[j][1])
                if d + 1e-6 < r + radii[j]:
                    valid = False
        sum_r = sum(radii) if valid else 0.0
        with open("metrics.json", "w", encoding="utf-8") as f:
            json.dump({"fitness": round(sum_r, 6), "valid_packing": valid, "sum_radii": round(sum_r, 6)}, f)
        """
    ).strip(),
)

EVIDENCE_SCORING_BENCHMARK = EvolutionBenchmark(
    name="evidence_scoring",
    objective_en="Evolve a multi-feature evidence ranking formula score_paper(feat) maximizing NDCG@5.",
    objective_zh="进化多特征循证文献排序函数 score_paper(feat)，最大化权威证据基准上的 NDCG@5。",
    seed_code=dedent(
        """
        import math

        # EVOLVE-BLOCK-START
        def score_paper(feat: dict) -> float:
            # feat keys: rct (0/1), meta (0/1), multi_source (int), recency (0..1), cites_norm (0..1), conflict (0/1)
            return 0.25 * feat["rct"] + 0.15 * feat["cites_norm"] + 0.10 * feat["recency"]
        # EVOLVE-BLOCK-END
        """
    ).strip(),
    eval_suffix=dedent(
        """
        import json
        dataset = [
            ({"rct": 1, "meta": 1, "multi_source": 3, "recency": 0.95, "cites_norm": 0.85, "conflict": 0}, 3),
            ({"rct": 1, "meta": 0, "multi_source": 2, "recency": 0.90, "cites_norm": 0.72, "conflict": 0}, 2),
            ({"rct": 0, "meta": 1, "multi_source": 2, "recency": 0.80, "cites_norm": 0.90, "conflict": 0}, 3),
            ({"rct": 0, "meta": 0, "multi_source": 1, "recency": 0.95, "cites_norm": 0.20, "conflict": 1}, 0),
            ({"rct": 1, "meta": 0, "multi_source": 1, "recency": 0.40, "cites_norm": 0.30, "conflict": 1}, 1),
            ({"rct": 0, "meta": 0, "multi_source": 3, "recency": 0.85, "cites_norm": 0.65, "conflict": 0}, 2),
            ({"rct": 0, "meta": 0, "multi_source": 1, "recency": 0.20, "cites_norm": 0.15, "conflict": 0}, 0),
            ({"rct": 1, "meta": 1, "multi_source": 2, "recency": 0.70, "cites_norm": 0.55, "conflict": 0}, 3),
        ]
        scored = sorted([(float(score_paper(f)), rel) for f, rel in dataset], key=lambda x: -x[0])
        ideal = sorted([rel for _, rel in dataset], reverse=True)
        def dcg(rels):
            return sum((2 ** r - 1) / math.log2(idx + 2) for idx, r in enumerate(rels[:5]))
        ndcg = dcg([r for _, r in scored]) / max(dcg(ideal), 1e-9)
        with open("metrics.json", "w", encoding="utf-8") as f:
            json.dump({"fitness": round(ndcg, 6), "ndcg_at_5": round(ndcg, 6)}, f)
        """
    ).strip(),
)

BUILTIN_BENCHMARKS = {
    "symbolic_discovery": SYMBOLIC_BENCHMARK,
    "circle_packing": CIRCLE_PACKING_BENCHMARK,
    "evidence_scoring": EVIDENCE_SCORING_BENCHMARK,
}


def get_benchmark(name: str, seed_file: Optional[Path] = None, eval_file: Optional[Path] = None) -> EvolutionBenchmark:
    if seed_file and eval_file and seed_file.exists() and eval_file.exists():
        return EvolutionBenchmark(
            name=name or seed_file.stem,
            objective_en=f"Custom algorithm evolution over {seed_file.name}",
            objective_zh=f"自定义算法进化任务：{seed_file.name}",
            seed_code=seed_file.read_text(encoding="utf-8"),
            eval_suffix=eval_file.read_text(encoding="utf-8"),
        )
    if name not in BUILTIN_BENCHMARKS:
        raise ValueError(f"Unknown benchmark '{name}'. Choose from: {list(BUILTIN_BENCHMARKS.keys())}")
    return BUILTIN_BENCHMARKS[name]
