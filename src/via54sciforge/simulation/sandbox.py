"""AST safety validator and isolated subprocess execution sandbox for scientific simulations."""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

FORBIDDEN_MODULES = {
    "subprocess",
    "socket",
    "shutil",
    "ctypes",
    "urllib",
    "http",
    "httpx",
    "requests",
    "webbrowser",
    "ftplib",
    "smtplib",
    "telnetlib",
    "pty",
    "importlib",
    "pickle",
    "marshal",
    "os",
    "sys",
    "pathlib",
    "multiprocessing",
}

FORBIDDEN_BUILTINS = {"eval", "exec", "compile", "__import__", "breakpoint", "input"}
FORBIDDEN_ATTRS = {
    "system",
    "popen",
    "spawn",
    "fork",
    "rmtree",
    "unlink",
    "rmdir",
    "__subclasses__",
    "__globals__",
    "__builtins__",
    "__code__",
    "__closure__",
}


@dataclass
class SandboxResult:
    """Result returned by running a candidate simulation or evolution script in the sandbox."""

    ok: bool
    returncode: int
    elapsed_s: float
    metrics: Dict[str, Any] = field(default_factory=dict)
    stdout: str = ""
    stderr: str = ""
    script_path: str = ""
    violations: List[str] = field(default_factory=list)


def validate_ast_safety(code: str, allow_open_local: bool = True) -> List[str]:
    """Inspect Python AST and return a list of security/sandbox violations (empty = safe)."""
    violations: List[str] = []
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return [f"SyntaxError: {exc}"]

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root_mod = alias.name.split(".")[0]
                if root_mod in FORBIDDEN_MODULES:
                    violations.append(f"Forbidden import: {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            root_mod = (node.module or "").split(".")[0]
            if root_mod in FORBIDDEN_MODULES:
                violations.append(f"Forbidden from-import: {node.module}")
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                if node.func.id in FORBIDDEN_BUILTINS:
                    violations.append(f"Forbidden builtin call: {node.func.id}")
                if node.func.id == "open" and not allow_open_local:
                    violations.append("Forbidden open() call in strict mode")
                if node.func.id == "open" and node.args:
                    first = node.args[0]
                    if isinstance(first, ast.Constant) and isinstance(first.value, str):
                        val = first.value
                        if os.path.isabs(val) or ".." in val:
                            violations.append(f"open() path escapes sandbox: {val}")
            elif isinstance(node.func, ast.Attribute):
                if node.func.attr in FORBIDDEN_ATTRS:
                    violations.append(f"Forbidden attribute call: .{node.func.attr}")
        elif isinstance(node, ast.Attribute):
            if node.attr in FORBIDDEN_ATTRS:
                violations.append(f"Forbidden attribute access: .{node.attr}")
    return violations


def run_in_sandbox(
    code: str,
    work_dir: Path,
    script_name: str = "sim_run.py",
    timeout_s: int = 30,
    seed: int = 42,
    allow_open_local: bool = True,
) -> SandboxResult:
    """Validate AST safety and run Python script inside an isolated workspace directory."""
    violations = validate_ast_safety(code, allow_open_local=allow_open_local)
    if violations:
        return SandboxResult(
            ok=False,
            returncode=-1,
            elapsed_s=0.0,
            stderr="; ".join(violations),
            violations=violations,
        )

    work_dir.mkdir(parents=True, exist_ok=True)
    metrics_file = work_dir / "metrics.json"
    if metrics_file.exists():
        metrics_file.unlink()

    script_path = work_dir / script_name
    script_path.write_text(code, encoding="utf-8")

    env = os.environ.copy()
    env["PYTHONHASHSEED"] = str(seed)
    env["PYTHONIOENCODING"] = "utf-8"

    t0 = time.perf_counter()
    try:
        proc = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=str(work_dir),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_s,
        )
        elapsed = round(time.perf_counter() - t0, 4)
    except subprocess.TimeoutExpired:
        return SandboxResult(
            ok=False,
            returncode=-2,
            elapsed_s=float(timeout_s),
            stderr=f"Sandbox execution timed out after {timeout_s}s",
            script_path=str(script_path),
        )

    metrics: Dict[str, Any] = {}
    if metrics_file.exists():
        try:
            metrics = json.loads(metrics_file.read_text(encoding="utf-8"))
        except Exception as exc:
            metrics = {"_parse_error": str(exc)}
    elif proc.stdout.strip():
        for line in reversed(proc.stdout.strip().splitlines()):
            line = line.strip()
            if line.startswith("{") and line.endswith("}"):
                try:
                    metrics = json.loads(line)
                    break
                except Exception:
                    pass

    return SandboxResult(
        ok=(proc.returncode == 0 and bool(metrics)),
        returncode=proc.returncode,
        elapsed_s=elapsed,
        metrics=metrics,
        stdout=proc.stdout,
        stderr=proc.stderr,
        script_path=str(script_path),
    )
