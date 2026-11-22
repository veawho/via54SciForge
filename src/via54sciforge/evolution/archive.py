"""MAP-Elites multi-island program archive backed by SQLite with novelty rejection & Pareto extraction."""

from __future__ import annotations

import hashlib
import json
import random
import re
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from via54sciforge.core.models import EvolutionCandidate, EvolutionIslandStats


def code_tokens(code: str) -> set[str]:
    return set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*|\d+(?:\.\d+)?|[+\-*/=<>]+", code))


def jaccard_novelty(code_a: str, code_b: str) -> float:
    ta, tb = code_tokens(code_a), code_tokens(code_b)
    if not ta and not tb:
        return 0.0
    union = len(ta | tb)
    inter = len(ta & tb)
    return 1.0 - (inter / max(union, 1))


def compute_code_hash(code: str) -> str:
    normalized = re.sub(r"\s+", " ", code).strip()
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:16]


class MAPElitesIslandArchive:
    """Multi-island MAP-Elites archive persisted in SQLite."""

    def __init__(
        self,
        db_path: Path,
        num_islands: int = 3,
        bins_x: int = 6,
        bins_y: int = 6,
        novelty_threshold: float = 0.05,
    ):
        self.db_path = db_path
        self.num_islands = max(1, num_islands)
        self.bins_x = bins_x
        self.bins_y = bins_y
        self.novelty_threshold = novelty_threshold
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.islands: List[Dict[Tuple[int, int], EvolutionCandidate]] = [{} for _ in range(self.num_islands)]
        self.all_candidates: List[EvolutionCandidate] = []
        self.seen_hashes: set[str] = set()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.execute("PRAGMA journal_mode=WAL;")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS evolution_candidates (
                    candidate_id TEXT PRIMARY KEY,
                    generation INTEGER,
                    island_id INTEGER,
                    parent_id TEXT,
                    operator TEXT,
                    fitness REAL,
                    bin_x INTEGER,
                    bin_y INTEGER,
                    complexity INTEGER,
                    runtime_ms REAL,
                    novelty_score REAL,
                    code_hash TEXT,
                    valid INTEGER,
                    code TEXT,
                    metrics_json TEXT
                )
                """
            )

    def min_novelty_to_island(self, code: str, island_id: int) -> float:
        h = compute_code_hash(code)
        if h in self.seen_hashes:
            return 0.0
        elites = list(self.islands[island_id].values())
        if not elites:
            return 1.0
        return min(jaccard_novelty(code, e.code) for e in elites)

    def compute_bins(self, complexity: int, runtime_ms: float) -> Tuple[int, int]:
        bx = min(self.bins_x - 1, max(0, complexity // 25))
        by = min(self.bins_y - 1, max(0, int(runtime_ms // 15)))
        return bx, by

    def add(self, cand: EvolutionCandidate) -> bool:
        """Insert candidate into SQLite ledger and update island MAP-Elites grid if better."""
        self.all_candidates.append(cand)
        if cand.code_hash:
            self.seen_hashes.add(cand.code_hash)

        bx, by = (cand.behavioral_coords[0], cand.behavioral_coords[1]) if len(cand.behavioral_coords) >= 2 else (0, 0)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO evolution_candidates
                    (candidate_id, generation, island_id, parent_id, operator, fitness, bin_x, bin_y,
                     complexity, runtime_ms, novelty_score, code_hash, valid, code, metrics_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    cand.candidate_id,
                    cand.generation,
                    cand.island_id,
                    cand.parent_id,
                    cand.operator,
                    cand.fitness,
                    bx,
                    by,
                    cand.complexity,
                    cand.runtime_ms,
                    cand.novelty_score,
                    cand.code_hash,
                    1 if cand.valid else 0,
                    cand.code,
                    json.dumps(cand.metrics, ensure_ascii=False),
                ),
            )

        if not cand.valid:
            return False

        grid = self.islands[cand.island_id]
        existing = grid.get((bx, by))
        if existing is None or cand.fitness > existing.fitness:
            grid[(bx, by)] = cand
            return True
        return False

    def sample_parent(self, island_id: int, rng: random.Random) -> Optional[EvolutionCandidate]:
        grid = self.islands[island_id]
        if not grid:
            valid = [c for c in self.all_candidates if c.valid]
            return rng.choice(valid) if valid else None
        elites = sorted(grid.values(), key=lambda c: -c.fitness)
        # Rank-weighted selection balancing top exploitation & grid exploration
        weights = [1.0 / (idx + 1.5) for idx in range(len(elites))]
        return rng.choices(elites, weights=weights, k=1)[0]

    def sample_inspirations(self, island_id: int, k: int = 2) -> List[EvolutionCandidate]:
        pool = [c for idx, g in enumerate(self.islands) for c in g.values() if idx != island_id]
        if not pool:
            pool = list(self.islands[island_id].values())
        pool.sort(key=lambda c: -c.fitness)
        return pool[:k]

    def migrate_ring(self, generation: int) -> int:
        """Copy top elite from each island to the next island in a ring."""
        if self.num_islands < 2:
            return 0
        migrated = 0
        tops: List[Optional[EvolutionCandidate]] = []
        for g in self.islands:
            tops.append(max(g.values(), key=lambda c: c.fitness) if g else None)
        for idx, top in enumerate(tops):
            if top is None:
                continue
            target_island = (idx + 1) % self.num_islands
            bx, by = (top.behavioral_coords[0], top.behavioral_coords[1]) if len(top.behavioral_coords) >= 2 else (0, 0)
            target_grid = self.islands[target_island]
            existing = target_grid.get((bx, by))
            if existing is None or top.fitness > existing.fitness:
                clone = top.model_copy(
                    update={
                        "candidate_id": f"{top.candidate_id}_mig{generation}_i{target_island}",
                        "island_id": target_island,
                        "operator": "island_migration",
                    }
                )
                target_grid[(bx, by)] = clone
                migrated += 1
        return migrated

    def best_overall(self) -> Optional[EvolutionCandidate]:
        valid = [c for c in self.all_candidates if c.valid]
        if not valid:
            return None
        return max(valid, key=lambda c: (c.fitness, -c.complexity))

    def island_stats(self) -> List[EvolutionIslandStats]:
        stats_list: List[EvolutionIslandStats] = []
        for idx, g in enumerate(self.islands):
            vals = [c.fitness for c in g.values()]
            stats_list.append(
                EvolutionIslandStats(
                    island_id=idx,
                    archive_size=len(g),
                    best_fitness=round(max(vals), 5) if vals else 0.0,
                    mean_fitness=round(sum(vals) / len(vals), 5) if vals else 0.0,
                )
            )
        return stats_list

    def pareto_front(self) -> List[EvolutionCandidate]:
        """Extract non-dominated Pareto front maximizing fitness while minimizing AST complexity."""
        valid = [c for c in self.all_candidates if c.valid]
        if not valid:
            return []
        # Deduplicate by hash
        unique: Dict[str, EvolutionCandidate] = {}
        for c in valid:
            if c.code_hash not in unique or c.fitness > unique[c.code_hash].fitness:
                unique[c.code_hash] = c
        cands = sorted(unique.values(), key=lambda c: (c.complexity, -c.fitness))
        front: List[EvolutionCandidate] = []
        best_f = -1e18
        for c in cands:
            if c.fitness > best_f:
                front.append(c)
                best_f = c.fitness
        return front
