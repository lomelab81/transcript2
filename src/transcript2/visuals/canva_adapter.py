"""Canva adapter.

The live Canva work is driven by the agent via the Canva MCP connector
(`mcp__claude_ai_Canva__*`). Python's job is to emit a clean, connector-ready
spec the agent feeds into `generate-design-structured` (and, where a real
frame exists, `upload-asset-from-url` / image placement).

This keeps Python offline and deterministic; the agent performs the
network/Canva side.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..schema import Deck

_THEME = {
    "style": "corporate-japanese-consulting",
    "palette": ["#0B1F3A", "#1C3D5A", "#C9A227", "#F2F2F2", "#FFFFFF"],
    "font_hint": "Noto Sans JP / Yu Gothic",
    "mood": "calm, authoritative, executive, lots of whitespace",
}


def to_canva_spec(deck: Deck) -> dict:
    pages = []
    for s in deck.slides:
        visual = {
            "type": s.visual_type,
            "image_prompt": s.image_prompt or None,
            # Local frame path → agent uploads via upload-asset / file path.
            "frame_path": s.image_path,
        }
        pages.append(
            {
                "layout": s.layout,
                "title": s.title,
                "key_message": s.message,
                "bullets": s.bullets,
                "speaker_notes": s.speaker_notes,
                "visual": visual,
            }
        )
    return {
        "design_type": "presentation",
        "title": deck.title,
        "subtitle": deck.subtitle,
        "language": "ja",
        "theme": _THEME,
        "source_video": deck.meta.url if deck.meta else None,
        "pages": pages,
        "_agent_instructions": (
            "Use mcp__claude_ai_Canva__generate-design-structured with these "
            "pages. For pages with visual.frame_path, upload the local image "
            "and place it; for visual.type=='generated', let Canva generate an "
            "on-theme image from image_prompt. Keep the theme palette/fonts "
            "consistent across all pages. Finally export-design to PPTX/PDF."
        ),
    }


def write_canva_spec(deck: Deck, run_dir: Path) -> Path:
    spec = to_canva_spec(deck)
    p = run_dir / "canva_spec.json"
    p.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
    return p
