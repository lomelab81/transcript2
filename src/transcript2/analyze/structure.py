"""LLM structural pass — reconstruct the video's argument (not a summary).

Single pass for short videos; map-reduce for long ones so the transcript is
NEVER truncated:
  * MAP    — extract sections from each context-bounded window
  * REDUCE — synthesise thesis / narrative_arc / frameworks over all sections
Sections are concatenated in time order (the reduce step is deliberately
non-lossy: it never rewrites or merges section content).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..llm import prompts
from ..llm.ollama_client import chat_json
from ..schema import Insight, Section, VideoStructure
from .chunker import context_windows


# Flat MAP schema — a 7B model reliably fills flat string lists, but fails
# on deeply-nested models (Section→Insight with Literal kinds). We assemble
# the rich Section objects in Python afterwards.
class _FlatSection(BaseModel):
    title: str = ""
    summary: str = ""
    start: float = 0.0
    end: float = 0.0
    key_points: list[str] = Field(default_factory=list)


class _PartialStructure(BaseModel):
    sections: list[_FlatSection] = Field(default_factory=list)
    frameworks: list[str] = Field(default_factory=list)


class _ReduceOut(BaseModel):
    thesis: str = ""
    narrative_arc: str = ""
    frameworks: list[str] = Field(default_factory=list)


def analyze_structure(chunks: list[dict], *, single_pass_chars: int = 6500) -> VideoStructure:
    windows = context_windows(chunks, max_chars=single_pass_chars)

    # Short video → one shot, full structure directly.
    if len(windows) <= 1:
        block = windows[0] if windows else ""
        return chat_json(
            prompts.STRUCTURE_SYS,
            prompts.STRUCTURE_USER.format(transcript=block),
            VideoStructure,
            temperature=0.2,
        )

    # Long video → MAP each window.
    sections: list[Section] = []
    frameworks: list[str] = []
    for i, win in enumerate(windows, 1):
        print(f"[structure] map {i}/{len(windows)}")
        try:
            part = chat_json(
                prompts.STRUCTURE_MAP_SYS,
                prompts.STRUCTURE_MAP_USER.format(
                    part=i, total=len(windows), transcript=win
                ),
                _PartialStructure,
                temperature=0.2,
            )
            for fs in part.sections:
                sections.append(
                    Section(
                        title=fs.title,
                        summary=fs.summary,
                        start=fs.start,
                        end=fs.end,
                        insights=[
                            Insight(text=kp, kind="insight")
                            for kp in fs.key_points
                            if kp.strip()
                        ],
                    )
                )
            frameworks.extend(part.frameworks)
        except Exception as e:
            print(f"[structure]   map {i} failed ({e}); skipping window")

    sections.sort(key=lambda s: s.start)

    # REDUCE — synthesise the through-line over the section overview only.
    overview = "\n".join(
        f"[{s.start:.0f}-{s.end:.0f}s] {s.title} — {s.summary}" for s in sections
    )[:9000]
    try:
        red = chat_json(
            prompts.STRUCTURE_REDUCE_SYS,
            prompts.STRUCTURE_REDUCE_USER.format(sections_overview=overview),
            _ReduceOut,
            temperature=0.2,
        )
        thesis, arc = red.thesis, red.narrative_arc
        frameworks.extend(red.frameworks)
    except Exception as e:
        print(f"[structure] reduce failed ({e}); deriving fallback thesis")
        thesis = sections[0].summary if sections else ""
        arc = ""

    # De-dupe frameworks, keep order.
    seen: set[str] = set()
    fw = [f for f in frameworks if f and not (f in seen or seen.add(f))]

    return VideoStructure(
        thesis=thesis, sections=sections, frameworks=fw, narrative_arc=arc
    )
