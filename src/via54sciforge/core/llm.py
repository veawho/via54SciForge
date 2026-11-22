"""Unified LLM router supporting mmx-cli, Zhipu GLM, OpenAI-compatible APIs, and offline fallback."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Any, Dict, Optional

import httpx

from via54sciforge.core.config import LLMConfig

BELOW_NORMAL_PRIORITY_CLASS = 0x00004000


@dataclass
class LLMResponse:
    """Standardized response envelope from LLMRouter."""

    ok: bool
    provider: str
    model: str
    text: str
    fallback_used: bool = False
    error: str = ""


class LLMRouter:
    """Multi-provider LLM router with automatic deterministic offline fallback."""

    def __init__(self, config: Optional[LLMConfig] = None):
        self.config = config or LLMConfig()

    def available_providers(self) -> Dict[str, bool]:
        """Report which external LLM providers appear configured without making network calls."""
        return {
            "mmx": bool(shutil.which("mmx") or PathChecker.exists(r"C:\Users\via54\.tools\nodejs\mmx.cmd")),
            "glm": bool(os.environ.get("GLM_API_KEY") or os.environ.get("ZHIPUAI_API_KEY")),
            "openai": bool(os.environ.get("OPENAI_API_KEY")),
            "deepseek": bool(os.environ.get("DEEPSEEK_API_KEY")),
            "sensenova": bool(os.environ.get("SENSENOVA_API_KEY")),
            "custom_openai": bool(self.config.endpoint and os.environ.get("VIA54_LLM_API_KEY")),
            "offline": True,
        }

    def resolve_provider(self) -> str:
        """Select active provider based on configuration and available credentials."""
        pref = (self.config.provider or "auto").lower()
        if pref == "offline":
            return "offline"
        avail = self.available_providers()
        if pref != "auto" and avail.get(pref):
            return pref
        for candidate in ("deepseek", "openai", "glm", "sensenova", "custom_openai", "mmx"):
            if avail.get(candidate):
                return candidate
        return "offline"

    def complete(
        self,
        prompt: str,
        system_prompt: str = "You are a rigorous bilingual scientific research assistant.",
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        offline_fallback_text: str = "",
    ) -> LLMResponse:
        """Execute completion using configured provider, gracefully falling back to deterministic output."""
        provider = self.resolve_provider()
        if provider == "offline":
            return LLMResponse(
                ok=bool(offline_fallback_text),
                provider="offline",
                model="deterministic-engine",
                text=offline_fallback_text,
                fallback_used=True,
            )

        toks = max_tokens or self.config.max_tokens
        temp = self.config.temperature if temperature is None else temperature

        if provider == "mmx":
            res = self._call_mmx(prompt, system_prompt, toks)
            if res.ok:
                return res
        else:
            res = self._call_openai_compat(provider, prompt, system_prompt, toks, temp)
            if res.ok:
                return res

        return LLMResponse(
            ok=bool(offline_fallback_text),
            provider="offline",
            model="deterministic-engine",
            text=offline_fallback_text,
            fallback_used=True,
            error=res.error,
        )

    def _call_mmx(self, prompt: str, system_prompt: str, max_tokens: int) -> LLMResponse:
        mmx_bin = shutil.which("mmx") or r"C:\Users\via54\.tools\nodejs\mmx.cmd"
        model = self.config.model or "MiniMax-M3.1-Pro-Preview"
        tmp_path: Optional[str] = None
        try:
            with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tf:
                json.dump([{"role": "user", "content": prompt}], tf, ensure_ascii=False)
                tmp_path = tf.name
            cmd = [
                mmx_bin,
                "text",
                "chat",
                "--model",
                model,
                "--messages-file",
                tmp_path,
                "--max-tokens",
                str(max_tokens),
                "--output",
                "text",
            ]
            if system_prompt:
                cmd.extend(["--system", system_prompt])
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="ignore",
                timeout=int(self.config.timeout_s),
                creationflags=BELOW_NORMAL_PRIORITY_CLASS if os.name == "nt" else 0,
            )
            out = (proc.stdout or "").strip()
            if proc.returncode == 0 and out:
                return LLMResponse(ok=True, provider="mmx", model=model, text=out)
            return LLMResponse(
                ok=False,
                provider="mmx",
                model=model,
                text="",
                error=f"rc={proc.returncode}: {(proc.stderr or out)[:240]}",
            )
        except Exception as exc:
            return LLMResponse(ok=False, provider="mmx", model=model, text="", error=str(exc))
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass

    def _call_openai_compat(
        self, provider: str, prompt: str, system_prompt: str, max_tokens: int, temperature: float
    ) -> LLMResponse:
        endpoint_map = {
            "glm": ("https://open.bigmodel.cn/api/paas/v4/chat/completions", "glm-4.5-flash", "GLM_API_KEY"),
            "openai": ("https://api.openai.com/v1/chat/completions", "gpt-4o-mini", "OPENAI_API_KEY"),
            "deepseek": ("https://api.deepseek.com/chat/completions", "deepseek-chat", "DEEPSEEK_API_KEY"),
            "sensenova": ("https://token.sensenova.cn/v1/chat/completions", "sensenova-6.7-flash-lite", "SENSENOVA_API_KEY"),
            "custom_openai": (self.config.endpoint, self.config.model or "default", "VIA54_LLM_API_KEY"),
        }
        url, default_model, key_env = endpoint_map[provider]
        api_key = os.environ.get(key_env) or (
            os.environ.get("ZHIPUAI_API_KEY") if provider == "glm" else ""
        )
        if not api_key or not url:
            return LLMResponse(ok=False, provider=provider, model=default_model, text="", error="missing key/url")

        model = self.config.model or default_model
        payload: Dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if provider == "glm" and model.startswith("glm-4.5"):
            payload["thinking"] = {"type": "disabled"}

        try:
            with httpx.Client(timeout=self.config.timeout_s) as client:
                resp = client.post(
                    url,
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json=payload,
                )
                resp.raise_for_status()
                body = resp.json()
                text = (body.get("choices", [{}])[0].get("message", {}).get("content") or "").strip()
                text = re.sub(r"<think>.*?(?:</think>|$)", "", text, flags=re.DOTALL).strip()
                if text:
                    return LLMResponse(ok=True, provider=provider, model=model, text=text)
                return LLMResponse(ok=False, provider=provider, model=model, text="", error="empty completion")
        except Exception as exc:
            return LLMResponse(ok=False, provider=provider, model=model, text="", error=str(exc))


class PathChecker:
    """Small path utility avoiding circular imports."""

    @staticmethod
    def exists(raw: str) -> bool:
        return os.path.exists(raw)
