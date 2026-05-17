"""Narrative planning — map the video's structure onto an executive arc.

Output is a slide *plan* (skeleton). The heavy Japanese writing happens later,
per slide, in compose/slides.py.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..llm import prompts
from ..llm.ollama_client import chat_json
from ..schema import VideoStructure


class SlidePlan(BaseModel):
    purpose: str = "content"
    working_title: str = ""
    intent: str = Field("", description="The So-What this slide must land")
    source_timestamps: list[float] = Field(default_factory=list)


class DeckPlan(BaseModel):
    deck_title: str = ""
    deck_subtitle: str = ""
    slides: list[SlidePlan] = Field(default_factory=list)


def plan_deck(structure: VideoStructure, target_slides: int) -> DeckPlan:
    plan = chat_json(
        prompts.NARRATIVE_SYS,
        prompts.NARRATIVE_USER.format(
            structure=structure.model_dump_json(indent=2),
            target=target_slides,
        ),
        DeckPlan,
        temperature=0.3,
    )
    if not plan.slides:
        raise ValueError("Narrative planning returned no slides")
    return plan


def evidence_for(structure: VideoStructure, timestamps: list[float]) -> str:
    """Pull the source sections/insights nearest the planned timestamps."""
    if not timestamps:
        # No anchors → give the model the thesis + section titles.
        return "; ".join(s.title for s in structure.sections)[:1500]
    lo, hi = min(timestamps), max(timestamps)
    parts: list[str] = []
    for sec in structure.sections:
        if sec.end >= lo - 30 and sec.start <= hi + 30:
            ins = " / ".join(i.text for i in sec.insights[:6])
            parts.append(f"■ {sec.title} [{sec.start:.0f}-{sec.end:.0f}s]\n  {sec.summary}\n  {ins}")
    return ("\n".join(parts) or structure.thesis)[:2200]
