"""LLM structural pass — reconstruct the video's argument (not a summary)."""

from __future__ import annotations

from ..llm import prompts
from ..llm.ollama_client import chat_json
from ..schema import VideoStructure


def analyze_structure(transcript_block: str) -> VideoStructure:
    return chat_json(
        prompts.STRUCTURE_SYS,
        prompts.STRUCTURE_USER.format(transcript=transcript_block),
        VideoStructure,
        temperature=0.2,
    )
