"""Configuration loader for via54SciForge with dynamic repo-root resolution and env overrides."""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

import yaml
from pydantic import BaseModel, Field

HOTCACHE_MAX_BYTES = 5 * 1024 * 1024


def get_repo_root() -> Path:
    """Resolve repository root dynamically without assuming current working directory."""
    return Path(__file__).resolve().parents[3]


class PathsConfig(BaseModel):
    """Filesystem and external asset paths."""

    runs_dir: str = "runs"
    state_db: str = "runs/sciforge_state.db"
    kb_root: str = "D:/KnowledgeBase"
    kb_restructured: str = "D:/KnowledgeBase/Restructured"
    kb_db: str = "C:/KnowledgeBase_FastRuntime/VectorDB/via54_kb.db"
    gold_db: str = "Z:/KnowledgeBase_HotCache/gold_vault_node_z.db"
    hotcache_dir: str = "Z:/KnowledgeBase_HotCache"
    okf_catalog: str = "D:/KnowledgeBase/.kb_system/okf_dcat3_catalog.json"
    medit_bin: str = "F:/agent/ai/projects/via54Medit/bin/medit.exe"

    def resolve_path(self, raw: str) -> Path:
        p = Path(raw)
        if p.is_absolute():
            return p
        return get_repo_root() / p

    @property
    def runs_path(self) -> Path:
        return self.resolve_path(self.runs_dir)

    @property
    def state_db_path(self) -> Path:
        return self.resolve_path(self.state_db)


class LLMConfig(BaseModel):
    """LLM routing configuration."""

    provider: str = "auto"
    model: str = ""
    endpoint: str = ""
    timeout_s: float = 60.0
    temperature: float = 0.2
    max_tokens: int = 4096


class LiteratureConfig(BaseModel):
    """Multi-source literature retrieval configuration."""

    enabled_sources: List[str] = Field(
        default_factory=lambda: ["openalex", "pubmed", "arxiv", "semanticscholar", "europepmc"]
    )
    max_results_per_source: int = 10
    timeout_per_source_s: float = 15.0
    mailto: str = "via54sciforge@localhost"


class SimulationConfig(BaseModel):
    """Scientific simulation sandbox configuration."""

    sandbox_timeout_s: int = 30
    default_seed: int = 42
    default_bootstrap_n: int = 1500
    dpi: int = 300


class EvolutionConfig(BaseModel):
    """MAP-Elites + multi-island algorithm evolution configuration."""

    default_generations: int = 10
    population_per_gen: int = 4
    num_islands: int = 3
    migration_interval: int = 3
    novelty_threshold: float = 0.08
    bins_x: int = 6
    bins_y: int = 6


class DeliverablesConfig(BaseModel):
    """Deliverable reports & PPTX rendering configuration."""

    default_report_type: str = "deep_research"
    default_ppt_theme: str = "academic_navy"
    render_engine: str = "powerpoint"
    render_timeout_s: int = 45
    render_dpi: int = 150


class SciForgeConfig(BaseModel):
    """Top-level configuration object for via54SciForge."""

    paths: PathsConfig = Field(default_factory=PathsConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    literature: LiteratureConfig = Field(default_factory=LiteratureConfig)
    simulation: SimulationConfig = Field(default_factory=SimulationConfig)
    evolution: EvolutionConfig = Field(default_factory=EvolutionConfig)
    deliverables: DeliverablesConfig = Field(default_factory=DeliverablesConfig)

    @classmethod
    def load(cls, config_path: Optional[Path] = None) -> "SciForgeConfig":
        """Load configuration from YAML file and apply environment variable overrides."""
        target = config_path or (get_repo_root() / "configs" / "default.yaml")
        raw: dict = {}
        if target.exists():
            data = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
            if isinstance(data, dict):
                raw = data

        cfg = cls.model_validate(
            {
                "paths": raw.get("paths", {}),
                "llm": raw.get("llm", {}),
                "literature": raw.get("literature", {}),
                "simulation": raw.get("simulation", {}),
                "evolution": raw.get("evolution", {}),
                "deliverables": raw.get("deliverables", {}),
            }
        )

        env_paths = {
            "VIA54_RUNS_DIR": "runs_dir",
            "VIA54_STATE_DB": "state_db",
            "VIA54_KB_ROOT": "kb_root",
            "VIA54_KB_RESTRUCTURED": "kb_restructured",
            "VIA54_KB_DB": "kb_db",
            "VIA54_GOLD_DB": "gold_db",
            "VIA54_HOTCACHE_DIR": "hotcache_dir",
            "VIA54_OKF_CATALOG": "okf_catalog",
            "VIA54_MEDIT_BIN": "medit_bin",
        }
        for env_key, attr in env_paths.items():
            val = os.environ.get(env_key)
            if val:
                setattr(cfg.paths, attr, val)

        if os.environ.get("VIA54_LLM_PROVIDER"):
            cfg.llm.provider = os.environ["VIA54_LLM_PROVIDER"]
        if os.environ.get("VIA54_LLM_MODEL"):
            cfg.llm.model = os.environ["VIA54_LLM_MODEL"]
        if os.environ.get("VIA54_LLM_ENDPOINT"):
            cfg.llm.endpoint = os.environ["VIA54_LLM_ENDPOINT"]

        return cfg
