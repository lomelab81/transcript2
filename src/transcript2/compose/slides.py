"""Per-slide executive Japanese writing."""

from __future__ import annotations

from ..config import CONFIG
from ..llm import prompts
from ..llm.ollama_client import chat_json
from ..schema import Deck, Slide, VideoMeta, VideoStructure
from .narrative import DeckPlan, evidence_for


# Slide layout is derived from the planned ROLE, not the LLM — a 7B model
# tends to echo the example skeleton's first enum value for every slide.
_PURPOSE_LAYOUT = {
    "title": "title",
    "agenda": "agenda",
    "background": "content",
    "issue": "content",
    "analysis": "content",
    "recommendation": "content",
    "outlook": "content",
    "closing": "closing",
    "section": "section",
}


def _derive_layout(purpose: str, idx: int) -> str:
    if idx == 0:
        return "title"
    return _PURPOSE_LAYOUT.get((purpose or "").strip().lower(), "content")


def _write_slide(plan, structure: VideoStructure, idx: int) -> Slide:
    evidence = evidence_for(structure, plan.source_timestamps)
    slide = chat_json(
        prompts.SLIDE_SYS,
        prompts.SLIDE_USER.format(
            purpose=plan.purpose,
            intent=plan.intent,
            working_title=plan.working_title,
            evidence=evidence,
            thesis=structure.thesis,
        ),
        Slide,
        temperature=0.4,
        exclude={"source_timestamps", "image_path", "layout"},
    )
    slide.source_timestamps = plan.source_timestamps
    slide.layout = _derive_layout(plan.purpose, idx)
    # Enforce executive concision.
    slide.bullets = [b.strip() for b in slide.bullets if b.strip()][: CONFIG.max_bullets]
    return slide


def compose_deck(
    plan: DeckPlan, structure: VideoStructure, meta: VideoMeta
) -> Deck:
    slides: list[Slide] = []
    for i, sp in enumerate(plan.slides):
        print(f"[slides] writing {i + 1}/{len(plan.slides)}: {sp.purpose} — {sp.working_title}")
        try:
            slides.append(_write_slide(sp, structure, i))
        except Exception as e:
            print(f"[slides]   failed ({e}); inserting skeleton")
            slides.append(
                Slide(
                    title=sp.working_title or "（生成失敗）",
                    message=sp.intent,
                    layout=_derive_layout(sp.purpose, i),
                    source_timestamps=sp.source_timestamps,
                )
            )
    return Deck(
        title=plan.deck_title or meta.title,
        subtitle=plan.deck_subtitle,
        language="ja",
        slides=slides,
        meta=meta,
    )
