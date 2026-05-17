"""Offline smoke tests — no network, no Ollama required."""

from pathlib import Path

from transcript2.ingest.youtube import parse_video_id
from transcript2.render.pptx import render_pptx
from transcript2.schema import Deck, Slide, VideoMeta
from transcript2.visuals.canva_adapter import to_canva_spec


def test_parse_video_id():
    assert parse_video_id("https://www.youtube.com/watch?v=4XqVR6xI6Kw") == "4XqVR6xI6Kw"
    assert parse_video_id("https://youtu.be/4XqVR6xI6Kw") == "4XqVR6xI6Kw"
    assert parse_video_id("4XqVR6xI6Kw") == "4XqVR6xI6Kw"


def _deck() -> Deck:
    return Deck(
        title="成熟市場における収益構造転換",
        subtitle="動画分析サマリー",
        slides=[
            Slide(title="表紙", layout="title"),
            Slide(
                title="シェア争いより収益構造の転換が成長の鍵",
                message="価格競争は消耗戦であり、構造転換が唯一の出口",
                bullets=["既存の値下げ戦略は利益を毀損", "高付加価値領域へ資源を再配分"],
                speaker_notes="動画では具体的なA社事例で説明されていた。",
                visual_type="generated",
                image_prompt="calm corporate japanese chart",
                layout="content",
            ),
        ],
        meta=VideoMeta(video_id="x", url="https://y", title="t"),
    )


def test_to_output_schema():
    out = _deck().to_output()
    assert set(out["slides"][1].keys()) == {
        "title", "message", "bullets", "speaker_notes",
        "visual_type", "image_prompt", "layout",
    }


def test_canva_spec():
    spec = to_canva_spec(_deck())
    assert spec["design_type"] == "presentation"
    assert len(spec["pages"]) == 2
    assert spec["theme"]["style"] == "corporate-japanese-consulting"


def test_pptx_render(tmp_path: Path):
    out = render_pptx(_deck(), tmp_path / "d.pptx")
    assert out.exists() and out.stat().st_size > 0
