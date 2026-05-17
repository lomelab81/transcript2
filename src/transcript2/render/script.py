"""Presenter script export — Markdown rehearsal doc.

Packages the per-slide speaker notes (already produced by composition)
into a standalone document so the deck can be rehearsed without opening
PowerPoint's Presenter View.
"""

from __future__ import annotations

from pathlib import Path

from ..schema import Deck


def render_script(deck: Deck, out_path: Path) -> Path:
    src = deck.meta.url if deck.meta else ""
    lines = [
        f"# 発表者スクリプト — {deck.title}",
        "",
        f"全{len(deck.slides)}スライド" + (f" / 出典: {src}" if src else ""),
        "",
        "---",
        "",
    ]
    for i, s in enumerate(deck.slides, 1):
        lines += [f"## スライド {i}: {s.title}", "", f"**キーメッセージ:** {s.message}", ""]
        if s.bullets:
            lines.append("**要点:**")
            lines += [f"- {b}" for b in s.bullets]
            lines.append("")
        lines += [
            "**話す内容:**",
            "",
            s.speaker_notes.strip() or "_(なし)_",
            "",
            "---",
            "",
        ]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path
