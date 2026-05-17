"""Per-slide executive Japanese writing."""

from __future__ import annotations

from ..config import CONFIG
from ..llm import prompts
from ..llm.ollama_client import chat_json
from ..schema import Deck, Slide, VideoMeta, VideoStructure
from .narrative import DeckPlan, evidence_for


def _write_slide(plan, structure: VideoStructure) -> Slide:
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
        exclude={"source_timestamps", "image_path"},
    )
    slide.source_timestamps = plan.source_timestamps
    # Enforce executive concision.
    slide.bullets = [b.strip() for b in slide.bullets if b.strip()][: CONFIG.max_bullets]
    return slide


def compose_deck(
    plan: DeckPlan, structure: VideoStructure, meta: VideoMeta
) -> Deck:
    slides: list[Slide] = []
    for i, sp in enumerate(plan.slides, 1):
        print(f"[slides] writing {i}/{len(plan.slides)}: {sp.purpose} — {sp.working_title}")
        try:
            slides.append(_write_slide(sp, structure))
        except Exception as e:
            print(f"[slides]   failed ({e}); inserting skeleton")
            slides.append(
                Slide(
                    title=sp.working_title or "（生成失敗）",
                    message=sp.intent,
                    layout="content",
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
