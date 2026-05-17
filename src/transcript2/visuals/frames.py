"""Attach real YouTube frames to slides that asked for visual_type='frame'.

Slides keep the original timestamp anchors; we grab one representative frame
per such slide and attach its path. Generated-image slides are left for the
Canva stage (generate-design) — we only preserve their image_prompt.
"""

from __future__ import annotations

from pathlib import Path

from ..config import CONFIG
from ..ingest.youtube import extract_frames
from ..schema import Deck


def attach_frames(deck: Deck, url: str, run_dir: Path) -> Deck:
    if not CONFIG.extract_frames:
        return deck

    wanted: dict[int, float] = {}
    for idx, s in enumerate(deck.slides):
        if s.visual_type == "frame" and s.source_timestamps:
            mid = sorted(s.source_timestamps)[len(s.source_timestamps) // 2]
            wanted[idx] = round(mid, 1)

    if not wanted:
        return deck

    # Cap how many we download/extract.
    items = list(wanted.items())[: CONFIG.frame_count]
    ts_list = sorted({ts for _, ts in items})
    grabbed = extract_frames(url, run_dir, ts_list)

    if not grabbed:
        # Downgrade unfulfilled frame slides to generated so the deck still works.
        for idx, _ in items:
            s = deck.slides[idx]
            if not s.image_prompt:
                s.image_prompt = (
                    f"Minimal corporate Japanese business slide visual for: {s.title}"
                )
            s.visual_type = "generated"
        return deck

    for idx, ts in items:
        path = grabbed.get(ts)
        if path:
            deck.slides[idx].image_path = path
        else:
            deck.slides[idx].visual_type = "generated"
    return deck
