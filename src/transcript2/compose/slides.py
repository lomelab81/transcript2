"""Per-slide executive Japanese writing."""

from __future__ import annotations

import re

from ..config import CONFIG
from ..llm import prompts
from ..llm.ollama_client import chat_json
from ..schema import Deck, Slide, VideoMeta, VideoStructure
from .critic import review_slide
from .grounding import scrub, unsupported
from .narrative import DeckPlan, evidence_for

# How many critic-driven rewrites to attempt per slide before accepting.
# One pass: the second rarely helped and tripled LLM cost per slide.
_MAX_REWRITES = 1


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


def _write_slide(
    plan,
    structure: VideoStructure,
    idx: int,
    *,
    feedback: str = "",
    avoid: list[str] | None = None,
) -> Slide:
    evidence = evidence_for(structure, plan.source_timestamps)
    user = prompts.SLIDE_USER.format(
        purpose=plan.purpose,
        intent=plan.intent,
        working_title=plan.working_title,
        evidence=evidence,
        thesis=structure.thesis,
    )
    if avoid:
        user += "\n\n# 既出スライドの主張(重複禁止・別の切り口にする)\n" + "\n".join(
            f"- {m}" for m in avoid if m
        )
    if feedback:
        user += f"\n\n# 前回の不合格指摘(必ず是正)\n{feedback}"
    slide = chat_json(
        prompts.SLIDE_SYS,
        user,
        Slide,
        temperature=0.4,
        exclude={"source_timestamps", "image_path", "layout"},
    )
    slide.source_timestamps = plan.source_timestamps
    slide.layout = _derive_layout(plan.purpose, idx)
    # Enforce executive concision deterministically (the LLM can't count JP
    # chars reliably, so we cap here instead of asking the critic to police it).
    cap = CONFIG.max_bullet_chars
    slide.bullets = [
        (b[: cap - 1] + "…") if len(b) > cap else b
        for b in (x.strip() for x in slide.bullets)
        if b.strip()
    ][: CONFIG.max_bullets]
    return slide


_DIGIT = re.compile(r"\d")


def _grounded_data(structure: VideoStructure, timestamps: list[float]) -> list[str]:
    """Real, source-derived figures the writer may cite (kind=data or numeric)."""
    lo = min(timestamps) - 30 if timestamps else float("-inf")
    hi = max(timestamps) + 30 if timestamps else float("inf")
    near, anywhere = [], []
    for sec in structure.sections:
        for ins in sec.insights:
            if ins.kind == "data" or _DIGIT.search(ins.text):
                anywhere.append(ins.text)
                if sec.end >= lo and sec.start <= hi:
                    near.append(ins.text)
    picked = near or anywhere
    seen: set[str] = set()
    return [x for x in picked if not (x in seen or seen.add(x))][:6]


def compose_deck(
    plan: DeckPlan,
    structure: VideoStructure,
    meta: VideoMeta,
    *,
    grounding: str = "",
) -> Deck:
    slides: list[Slide] = []
    seen_messages: list[str] = []
    for i, sp in enumerate(plan.slides):
        print(f"[slides] writing {i + 1}/{len(plan.slides)}: {sp.purpose} — {sp.working_title}")
        try:
            slide = _write_slide(sp, structure, i, avoid=seen_messages)
            # Critic-gated regeneration: enforce the presentation rules.
            for attempt in range(_MAX_REWRITES):
                verdict = review_slide(slide, seen_messages)
                if verdict.passed:
                    break
                print(
                    f"[slides]   critic rejected (rewrite {attempt + 1}): "
                    f"{'; '.join(verdict.issues)[:120]}"
                )
                slide = _write_slide(
                    sp, structure, i,
                    feedback=verdict.rewrite_directive
                    or "; ".join(verdict.issues),
                    avoid=seen_messages,
                )
            # Groundedness guard: no fabricated %/割/倍 figures. Corrective,
            # not subtractive — feed the real data so the slide stays concrete.
            if grounding:
                bad = unsupported(slide, grounding)
                if bad:
                    print(f"[slides]   unsupported figures {bad}; regenerating")
                    real = _grounded_data(structure, sp.source_timestamps)
                    real_block = (
                        "\n出典に実在する数値(これらは使用可):\n"
                        + "\n".join(f"- {r}" for r in real)
                        if real
                        else "出典に数値データは乏しい。数値を使わず質的に述べる。"
                    )
                    slide = _write_slide(
                        sp, structure, i, avoid=seen_messages,
                        feedback=(
                            f"次の数値は出典に存在せず創作である: {', '.join(bad)}。"
                            "数値を一切創作しないこと。"
                            f"{real_block}\n"
                            "創作値は削除せず、上記の実数値で具体性を保って書き換える。"
                        ),
                    )
                    still = unsupported(slide, grounding)
                    if still:
                        print(f"[slides]   still unsupported {still}; scrubbing")
                        slide = scrub(slide, still)
            slides.append(slide)
            if slide.message:
                seen_messages.append(slide.message)
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
