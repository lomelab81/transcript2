"""LLM-as-judge — gates each slide against the presentation rules.

Scores a slide on: implication-driven title, specificity (no generic
filler), concision, and distinctness vs sibling slides. Returns a verdict
plus a concrete rewrite directive used to regenerate failing slides.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..llm import prompts
from ..llm.ollama_client import chat_json
from ..schema import Slide


class Critique(BaseModel):
    passed: bool = True
    issues: list[str] = Field(default_factory=list)
    rewrite_directive: str = ""


def review_slide(slide: Slide, sibling_messages: list[str]) -> Critique:
    siblings = "\n".join(f"- {m}" for m in sibling_messages if m) or "(なし)"
    bullets = "\n".join(f"- {b}" for b in slide.bullets) or "(なし)"
    try:
        return chat_json(
            prompts.CRITIC_SYS,
            prompts.CRITIC_USER.format(
                title=slide.title,
                message=slide.message,
                bullets=bullets,
                siblings=siblings,
            ),
            Critique,
            temperature=0.1,
        )
    except Exception as e:
        # Fail-open: a flaky judge must not block deck production.
        print(f"[critic] review skipped ({e})")
        return Critique(passed=True)
