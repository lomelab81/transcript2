"""Evaluation harness — scores a generated deck so changes are measurable.

Deterministic metrics (cheap, reliable, no model):
  * groundedness  — fraction of slides with no fabricated %/割/倍 figures
  * distinctness  — unique-message ratio + embedding pairwise separation
  * conciseness   — fraction of bullets within the length cap
  * coverage      — slide count vs target

Optional LLM rubric (one judge call): structure-fidelity, JP business
register, implication-title rate — each 1–5 with a one-line rationale.

Usage:  transcript2-eval output/<video_id> [--no-llm]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pydantic import BaseModel, Field

from .analyze.chunker import _cos
from .compose.grounding import build_corpus, unsupported
from .config import CONFIG
from .llm.ollama_client import chat_json, embed
from .schema import Deck


class LLMRubric(BaseModel):
    structure_fidelity: int = Field(0, ge=0, le=5)
    business_register: int = Field(0, ge=0, le=5)
    implication_titles: int = Field(0, ge=0, le=5)
    rationale: str = ""


class Scorecard(BaseModel):
    slides: int = 0
    groundedness: float = 0.0
    distinctness: float = 0.0
    conciseness: float = 0.0
    coverage: float = 0.0
    deterministic_score: float = 0.0
    llm: LLMRubric | None = None
    notes: list[str] = Field(default_factory=list)


_RUBRIC_SYS = """あなたはプレゼン品質の評価者です。各観点を1〜5で採点し、
理由を1文で述べます。甘くせず、コンサル提出基準で評価します。"""

_RUBRIC_USER = """# スライド(JSON)
{deck}

# 採点(1=不可, 5=優秀)
- structure_fidelity: 元動画の論理構造・具体性を保持しているか
- business_register: エグゼクティブ日本語として自然か(AI臭・冗長語がないか)
- implication_titles: タイトルが結論・示唆を語れているか(一般名詞の羅列は低評価)
- rationale: 最大の弱点を1文で"""


def _distinctness(deck: Deck) -> tuple[float, list[str]]:
    msgs = [s.message for s in deck.slides if s.message]
    if len(msgs) < 2:
        return 1.0, []
    uniq = len(set(msgs)) / len(msgs)
    notes: list[str] = []
    try:
        vecs = embed(msgs)
        worst = 0.0
        for a in range(len(vecs)):
            for b in range(a + 1, len(vecs)):
                worst = max(worst, _cos(vecs[a], vecs[b]))
        sep = 1.0 - worst
        if worst >= 0.93:
            notes.append(f"near-duplicate messages (max cos {worst:.2f})")
        return round(0.5 * uniq + 0.5 * sep, 3), notes
    except Exception:
        return round(uniq, 3), ["embeddings unavailable; uniq-ratio only"]


def evaluate(run_dir: Path, *, use_llm: bool = True) -> Scorecard:
    deck = Deck.model_validate(json.loads((run_dir / "deck.full.json").read_text()))
    tx = json.loads((run_dir / "transcript.json").read_text())
    struct = json.loads((run_dir / "structure.json").read_text())
    corpus = build_corpus(
        " ".join(s["text"] for s in tx),
        " ".join(i["text"] for sec in struct["sections"] for i in sec["insights"]),
    )

    n = len(deck.slides) or 1
    clean = sum(1 for s in deck.slides if not unsupported(s, corpus))
    bullets = [b for s in deck.slides for b in s.bullets]
    within = sum(1 for b in bullets if len(b) <= CONFIG.max_bullet_chars)
    dist, notes = _distinctness(deck)

    sc = Scorecard(
        slides=len(deck.slides),
        groundedness=round(clean / n, 3),
        distinctness=dist,
        conciseness=round(within / len(bullets), 3) if bullets else 1.0,
        coverage=round(min(len(deck.slides) / max(CONFIG.target_slides, 1), 1.0), 3),
        notes=notes,
    )
    sc.deterministic_score = round(
        0.4 * sc.groundedness
        + 0.35 * sc.distinctness
        + 0.15 * sc.conciseness
        + 0.10 * sc.coverage,
        3,
    )

    if use_llm:
        try:
            compact = [
                {"title": s.title, "message": s.message, "bullets": s.bullets}
                for s in deck.slides
            ]
            sc.llm = chat_json(
                _RUBRIC_SYS,
                _RUBRIC_USER.format(
                    deck=json.dumps(compact, ensure_ascii=False)[:6000]
                ),
                LLMRubric,
                temperature=0.1,
            )
        except Exception as e:
            sc.notes.append(f"LLM rubric skipped: {e}")

    (run_dir / "eval.json").write_text(
        sc.model_dump_json(indent=2), encoding="utf-8"
    )
    return sc


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="transcript2-eval")
    ap.add_argument("run_dir", help="output/<video_id> directory")
    ap.add_argument("--no-llm", action="store_true", help="deterministic only")
    args = ap.parse_args(argv)

    rd = Path(args.run_dir)
    if not (rd / "deck.full.json").exists():
        print(f"ERROR: {rd}/deck.full.json not found", file=sys.stderr)
        return 1
    sc = evaluate(rd, use_llm=not args.no_llm)

    print(f"\n── Scorecard: {rd} ──")
    print(f"  slides          {sc.slides}")
    print(f"  groundedness    {sc.groundedness:.3f}  (1.0 = no fabricated figures)")
    print(f"  distinctness    {sc.distinctness:.3f}")
    print(f"  conciseness     {sc.conciseness:.3f}")
    print(f"  coverage        {sc.coverage:.3f}")
    print(f"  ▶ deterministic {sc.deterministic_score:.3f} / 1.000")
    if sc.llm:
        L = sc.llm
        print(
            f"  LLM  fidelity={L.structure_fidelity}/5 "
            f"register={L.business_register}/5 titles={L.implication_titles}/5"
        )
        print(f"       {L.rationale}")
    for nte in sc.notes:
        print(f"  ! {nte}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
