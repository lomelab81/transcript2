"""End-to-end orchestrator: YouTube URL → executive Japanese deck.

Stages (each writes a typed artifact to the run directory for traceability):
  1. meta          — yt-dlp metadata
  2. transcript    — captions → whisper fallback (timestamped)
  3. chunk         — semantic chunking
  4. structure     — reconstruct the video's argument (NOT a summary)
  5. plan          — map structure onto an executive arc
  6. compose       — write each slide in executive Japanese
  7. frames        — attach real YouTube frames where relevant
  8. emit          — slides.json, canva_spec.json, deck.pptx
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .analyze.chunker import chunk
from .analyze.structure import analyze_structure
from .compose.grounding import build_corpus
from .compose.narrative import plan_deck
from .compose.slides import compose_deck
from .config import CONFIG
from .ingest.transcript import get_transcript
from .ingest.youtube import fetch_meta
from .llm.ollama_client import ping
from .render.pdf import render_pdf
from .render.pptx import render_pptx
from .render.script import render_script
from .schema import Deck
from .visuals.canva_adapter import write_canva_spec
from .visuals.frames import attach_frames


@dataclass
class Result:
    run_dir: Path
    slides_json: Path
    canva_spec: Path
    pptx: Path | None
    deck: Deck


def _save(obj, path: Path):
    path.write_text(
        json.dumps(obj, ensure_ascii=False, indent=2)
        if isinstance(obj, (dict, list))
        else obj.model_dump_json(indent=2),
        encoding="utf-8",
    )


def run(url: str, *, make_pptx: bool = True) -> Result:
    if not ping():
        raise RuntimeError(
            f"Ollama not reachable at {CONFIG.ollama_host}. Start it with `ollama serve`."
        )

    print(f"▶ [1/8] metadata — {url}")
    meta = fetch_meta(url)
    run_dir = CONFIG.run_dir(meta.video_id)
    _save(meta, run_dir / "meta.json")
    print(f"   {meta.title}  ({meta.duration:.0f}s)")

    print("▶ [2/8] transcript")
    segs = get_transcript(url, meta, run_dir)
    _save([s.model_dump() for s in segs], run_dir / "transcript.json")
    print(f"   {len(segs)} segments via {meta.transcript_source}")
    if not segs:
        raise RuntimeError("No transcript could be obtained.")

    print("▶ [3/8] semantic chunking")
    chunks = chunk(segs)
    print(f"   {len(chunks)} topical chunks")

    print("▶ [4/8] structural analysis (reconstructing the argument)")
    structure = analyze_structure(chunks)
    _save(structure, run_dir / "structure.json")
    print(f"   thesis: {structure.thesis[:80]}…  ({len(structure.sections)} sections)")

    print("▶ [5/8] narrative planning (executive arc)")
    plan = plan_deck(structure, CONFIG.target_slides)
    _save(plan, run_dir / "plan.json")
    print(f"   {len(plan.slides)} slides planned")

    print("▶ [6/8] composing slides in executive Japanese")
    corpus = build_corpus(
        " ".join(s.text for s in segs),
        " ".join(i.text for sec in structure.sections for i in sec.insights),
    )
    deck = compose_deck(plan, structure, meta, grounding=corpus)

    print("▶ [7/8] attaching visuals (YouTube frames)")
    deck = attach_frames(deck, url, run_dir)

    print("▶ [8/8] emitting artifacts")
    slides_json = run_dir / "slides.json"
    _save(deck.to_output(), slides_json)
    _save(deck, run_dir / "deck.full.json")
    canva_spec = write_canva_spec(deck, run_dir)

    pptx_path = None
    if make_pptx:
        try:
            pptx_path = render_pptx(deck, run_dir / "deck.pptx")
        except Exception as e:
            print(f"   pptx render failed (non-fatal): {e}")
    try:
        render_pdf(deck, run_dir / "deck_local.pdf")
    except Exception as e:
        print(f"   pdf render failed (non-fatal): {e}")
    try:
        render_script(deck, run_dir / "presenter_script.md")
    except Exception as e:
        print(f"   script export failed (non-fatal): {e}")

    print(f"✔ done → {run_dir}")
    return Result(run_dir, slides_json, canva_spec, pptx_path, deck)
