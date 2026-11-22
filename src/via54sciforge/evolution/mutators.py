"""UCB1 operator bandit, deterministic AST/structural code mutators & LLM semantic diff patcher."""

from __future__ import annotations

import ast
import math
import random
import re
from typing import Dict, List, Optional

from via54sciforge.core.llm import LLMRouter
from via54sciforge.core.models import EvolutionCandidate

START_MARKER = "# EVOLVE-BLOCK-START"
END_MARKER = "# EVOLVE-BLOCK-END"


class UCB1OperatorBandit:
    """Tracks per-operator fitness deltas and picks the next operator via UCB1."""

    def __init__(self, operators: List[str], c: float = 1.2):
        self.operators = operators
        self.c = c
        self.counts: Dict[str, int] = {op: 0 for op in operators}
        self.rewards: Dict[str, float] = {op: 0.0 for op in operators}

    def select(self, rng: random.Random) -> str:
        unpulled = [op for op in self.operators if self.counts[op] == 0]
        if unpulled:
            return rng.choice(unpulled)
        total = sum(self.counts.values())
        scores: Dict[str, float] = {}
        for op in self.operators:
            mean = self.rewards[op] / self.counts[op]
            bonus = self.c * math.sqrt(math.log(max(total, 1)) / self.counts[op])
            scores[op] = mean + bonus
        return max(self.operators, key=lambda op: scores[op])

    def update(self, operator: str, parent_fitness: float, child_fitness: float, valid: bool) -> None:
        if operator not in self.counts:
            self.counts[operator] = 0
            self.rewards[operator] = 0.0
        self.counts[operator] += 1
        if not valid:
            reward = 0.0
        else:
            delta = max(0.0, child_fitness - parent_fitness)
            reward = min(1.0, delta / max(abs(parent_fitness), 1.0) * 4.0 + 0.05)
        self.rewards[operator] += reward


def _split_evolve_region(code: str) -> tuple[str, str, str]:
    if START_MARKER in code and END_MARKER in code:
        pre, rest = code.split(START_MARKER, 1)
        body, post = rest.split(END_MARKER, 1)
        return pre + START_MARKER, body, END_MARKER + post
    return "", code, ""


def ast_complexity(code: str) -> int:
    try:
        tree = ast.parse(code)
        return sum(1 for _ in ast.walk(tree))
    except SyntaxError:
        return len(code.splitlines()) * 5


def mutate_numeric_perturbation(code: str, rng: random.Random, scale: float = 0.35) -> str:
    """Perturb numeric constants inside the evolvable region using Python AST."""
    pre, body, post = _split_evolve_region(code)
    nums = list(re.finditer(r"(?<![A-Za-z_])(-?\d+\.\d+)(?![A-Za-z_0-9])", body))
    if not nums:
        return mutate_structural_expansion(code, rng)

    chosen = rng.sample(nums, k=min(len(nums), rng.choice([1, 2, 3])))
    chars = list(body)
    # Apply edits from right to left so offsets stay valid
    for m in sorted(chosen, key=lambda x: x.start(), reverse=True):
        val = float(m.group(1))
        if abs(val) < 1e-6:
            new_val = round(rng.uniform(-0.8, 0.8), 4)
        else:
            factor = 1.0 + rng.uniform(-scale, scale)
            shift = rng.uniform(-0.25, 0.25)
            new_val = round(val * factor + shift, 4)
        chars[m.start():m.end()] = list(str(new_val))
    mutated = pre + "".join(chars) + post
    return _ensure_valid_python(mutated, code)


def mutate_basis_expansion(code: str, rng: random.Random) -> str:
    """Inject or swap nonlinear mathematical / heuristic terms in evolvable blocks."""
    pre, body, post = _split_evolve_region(code)
    lines = body.splitlines()
    new_lines = list(lines)

    # Symbolic discovery pattern: enhance return expression
    for idx, line in enumerate(new_lines):
        stripped = line.strip()
        if stripped.startswith("return ") and "math.sin" not in body and "x" in stripped:
            indent = line[: len(line) - len(line.lstrip())]
            c1 = round(rng.uniform(0.5, 2.5), 3)
            c2 = round(rng.uniform(0.8, 2.0), 3)
            c3 = round(rng.uniform(-0.8, 0.8), 3)
            c4 = round(rng.uniform(-1.0, 1.5), 3)
            expr = stripped[len("return "):]
            cand_terms = [
                f"{indent}return ({expr}) + {c1} * math.sin({c2} * x) + {c3} * (x ** 2) + {c4}",
                f"{indent}return {c1} * math.sin({c2} * x) + {c3} * (x ** 2) + {c4} * x + 0.5",
                f"{indent}return ({expr}) + {c1} * math.cos({c2} * x)",
            ]
            new_lines[idx] = rng.choice(cand_terms)
            return _ensure_valid_python(pre + "\n".join(new_lines) + post, code)

    # Swap sin/cos/tanh/exp or arithmetic operators safely
    replacements = [
        ("math.cos(", "math.sin("),
        ("math.sin(", "math.cos("),
        (" + ", " - "),
        (" - ", " + "),
        ("0.5 *", "0.65 *"),
    ]
    rng.shuffle(replacements)
    for old, new in replacements:
        if old in body:
            mutated = pre + body.replace(old, new, 1) + post
            if mutated != code:
                return _ensure_valid_python(mutated, code)

    return mutate_numeric_perturbation(code, rng, scale=0.45)


def mutate_structural_expansion(code: str, rng: random.Random) -> str:
    """Refine heuristic parameters, weights, or relaxation multipliers inside evolvable code."""
    pre, body, post = _split_evolve_region(code)
    # Circle packing or iterative algorithm tuning
    if "radii" in body and "step" in body:
        c_step = round(rng.uniform(0.005, 0.035), 4)
        c_grow = round(rng.uniform(1.008, 1.06), 4)
        new_body = re.sub(r"grow\s*=\s*[-+]?\d*\.\d+", f"grow = {c_grow}", body)
        new_body = re.sub(r"step\s*=\s*[-+]?\d*\.\d+", f"step = {c_step}", new_body)
        if new_body != body:
            return _ensure_valid_python(pre + new_body + post, code)
    return mutate_numeric_perturbation(code, rng, scale=0.5)


def mutate_crossover_blend(
    parent: EvolutionCandidate, inspirations: List[EvolutionCandidate], rng: random.Random
) -> str:
    """Blend numeric coefficients between parent and a higher/diverse island inspiration."""
    if not inspirations:
        return mutate_numeric_perturbation(parent.code, rng)
    mate = rng.choice(inspirations)
    pre_a, body_a, post_a = _split_evolve_region(parent.code)
    _, body_b, _ = _split_evolve_region(mate.code)

    nums_a = list(re.finditer(r"(?<![A-Za-z_])(-?\d+\.\d+)(?![A-Za-z_0-9])", body_a))
    nums_b = [float(m.group(1)) for m in re.finditer(r"(?<![A-Za-z_])(-?\d+\.\d+)(?![A-Za-z_0-9])", body_b)]
    if not nums_a or not nums_b:
        return mutate_basis_expansion(parent.code, rng)

    alpha = rng.uniform(0.3, 0.7)
    chars = list(body_a)
    for idx, m in sorted(enumerate(nums_a), key=lambda x: x[1].start(), reverse=True):
        va = float(m.group(1))
        vb = nums_b[idx % len(nums_b)]
        blended = round(alpha * va + (1.0 - alpha) * vb, 4)
        chars[m.start():m.end()] = list(str(blended))
    return _ensure_valid_python(pre_a + "".join(chars) + post_a, parent.code)


def apply_search_replace_diff(code: str, llm_text: str) -> Optional[str]:
    """Parse AlphaEvolve-style SEARCH/REPLACE patch blocks from LLM output."""
    pattern = re.compile(r"<<<<<<< SEARCH\s*\n(.*?)\n=======\s*\n(.*?)\n>>>>>>> REPLACE", re.DOTALL)
    matches = pattern.findall(llm_text)
    if not matches:
        return None
    updated = code
    for search_blk, replace_blk in matches:
        if search_blk in updated:
            updated = updated.replace(search_blk, replace_blk, 1)
    try:
        ast.parse(updated)
        return updated if updated != code else None
    except SyntaxError:
        return None


def mutate_llm_diff(
    parent: EvolutionCandidate,
    inspirations: List[EvolutionCandidate],
    objective_desc: str,
    llm_router: Optional[LLMRouter],
    rng: random.Random,
) -> tuple[str, str]:
    """Attempt semantic LLM diff mutation; fall back cleanly to deterministic structural mutation."""
    if llm_router and llm_router.resolve_provider() != "offline":
        insp_txt = "\n\n".join(
            f"# Inspiration (fitness={c.fitness:.4f}):\n{c.code}" for c in inspirations[:2]
        )
        prompt = (
            f"Objective: {objective_desc}\n"
            f"Parent fitness: {parent.fitness:.5f}\nParent code:\n```python\n{parent.code}\n```\n\n"
            f"{insp_txt}\n\n"
            "Propose ONE targeted improvement ONLY inside `# EVOLVE-BLOCK-START` .. `# EVOLVE-BLOCK-END` using:\n"
            "<<<<<<< SEARCH\n<exact existing lines>\n=======\n<improved python lines>\n>>>>>>> REPLACE"
        )
        resp = llm_router.complete(prompt, max_tokens=1000, temperature=0.35, offline_fallback_text="")
        if resp.ok:
            patched = apply_search_replace_diff(parent.code, resp.text)
            if patched:
                return patched, "llm_diff"

    return mutate_basis_expansion(parent.code, rng), "basis_expansion"


def _ensure_valid_python(candidate_code: str, fallback_code: str) -> str:
    try:
        ast.parse(candidate_code)
        return candidate_code
    except SyntaxError:
        return fallback_code
