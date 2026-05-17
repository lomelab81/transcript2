"""Groundedness guard — no fabricated statistics.

The writer must not invent figures. We extract "rate-like" claims
(percentages, 割, 倍) from a slide and verify each appears in the source
transcript. Plain counts (14スキル, 12回) are low-risk and left alone to
avoid false positives — fabrication shows up as invented rates/deltas
("20%短縮", "5割削減") which the video never stated.
"""

from __future__ import annotations

import re

from ..schema import Slide

_FW = str.maketrans("０１２３４５６７８９％", "0123456789%")


def normalize(text: str) -> str:
    t = text.translate(_FW)
    t = t.replace("パーセント", "%").replace("％", "%")
    t = re.sub(r"(?<=\d),(?=\d)", "", t)  # 1,000 → 1000
    return t


# A rate-like claim: a number immediately bound to %, 割, or 倍.
_RATE_RE = re.compile(r"\d+(?:\.\d+)?\s*(?:%|割|倍)")


def rate_claims(text: str) -> set[str]:
    return {m.group(0).replace(" ", "") for m in _RATE_RE.finditer(normalize(text))}


def build_corpus(transcript_text: str, extra: str = "") -> str:
    """Normalized grounding corpus = raw transcript (+ optional structure)."""
    return normalize(transcript_text + "\n" + extra)


def unsupported(slide: Slide, corpus: str) -> list[str]:
    """Rate-like claims in the slide that do NOT occur in the source."""
    claims = rate_claims(slide.title) | rate_claims(slide.message)
    for b in slide.bullets:
        claims |= rate_claims(b)
    return sorted(c for c in claims if c not in corpus)


def scrub(slide: Slide, bad: list[str]) -> Slide:
    """Last-resort deterministic removal of unsupported figures.

    Drops the number+unit (and a trailing connective); removes a bullet that
    becomes too short to carry meaning.
    """
    pats = [re.compile(r"[:：]?\s*" + re.escape(b)) for b in bad]

    def strip(s: str) -> str:
        out = normalize(s)
        for p in pats:
            out = p.sub("", out)
        return re.sub(r"[\s、:：]+$", "", out).strip()

    slide.title = strip(slide.title) or slide.title
    slide.message = strip(slide.message)
    kept: list[str] = []
    for b in slide.bullets:
        nb = strip(b)
        if len(nb) >= 6:  # avoid leaving a meaningless stub
            kept.append(nb)
    slide.bullets = kept or slide.bullets
    return slide
