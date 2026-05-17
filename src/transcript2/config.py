"""Runtime configuration. Everything overridable via environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env(key: str, default: str) -> str:
    return os.environ.get(key, default)


@dataclass
class Config:
    # LLM (local Ollama only — no external API keys)
    ollama_host: str = field(default_factory=lambda: _env("OLLAMA_HOST", "http://localhost:11434"))
    llm_model: str = field(default_factory=lambda: _env("T2_LLM_MODEL", "qwen2.5:7b"))
    embed_model: str = field(default_factory=lambda: _env("T2_EMBED_MODEL", "nomic-embed-text:latest"))
    llm_timeout: int = field(default_factory=lambda: int(_env("T2_LLM_TIMEOUT", "300")))

    # Paths
    output_dir: Path = field(default_factory=lambda: Path(_env("T2_OUTPUT", "output")))

    # Pipeline knobs
    target_slides: int = field(default_factory=lambda: int(_env("T2_TARGET_SLIDES", "12")))
    max_bullets: int = 5
    max_bullet_chars: int = 60  # hard cap; runaway bullets get trimmed with …
    extract_frames: bool = field(default_factory=lambda: _env("T2_FRAMES", "1") == "1")
    frame_count: int = field(default_factory=lambda: int(_env("T2_FRAME_COUNT", "8")))
    whisper_model: str = field(default_factory=lambda: _env("T2_WHISPER_MODEL", "base"))

    def run_dir(self, video_id: str) -> Path:
        d = self.output_dir / video_id
        d.mkdir(parents=True, exist_ok=True)
        (d / "frames").mkdir(exist_ok=True)
        return d


CONFIG = Config()
