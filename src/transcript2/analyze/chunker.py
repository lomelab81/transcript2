"""Semantic chunking.

Groups raw transcript segments into topically-coherent windows so the LLM
structural pass receives meaningful units instead of caption fragments.
Boundaries are placed where embedding similarity between consecutive windows
drops — i.e. where the topic shifts. Falls back to fixed-size windows if the
embedding model is unavailable.
"""

from __future__ import annotations

from ..llm.ollama_client import embed
from ..schema import TranscriptSegment


def _cos(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 1.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return dot / (na * nb) if na and nb else 1.0


def _windows(segs: list[TranscriptSegment], size: int) -> list[list[TranscriptSegment]]:
    return [segs[i : i + size] for i in range(0, len(segs), size)]


def chunk(
    segs: list[TranscriptSegment],
    *,
    window: int = 6,
    drop: float = 0.62,
) -> list[dict]:
    """Return a list of {text, start, end} topical chunks."""
    if not segs:
        return []
    wins = _windows(segs, window)
    texts = [" ".join(s.text for s in w) for w in wins]

    try:
        vecs = embed(texts)
    except Exception as e:
        print(f"[chunker] embeddings unavailable ({e}); using fixed windows")
        vecs = None

    chunks: list[dict] = []
    cur: list[TranscriptSegment] = list(wins[0])
    for i in range(1, len(wins)):
        boundary = True
        if vecs:
            boundary = _cos(vecs[i - 1], vecs[i]) < drop
        if boundary:
            chunks.append(_pack(cur))
            cur = list(wins[i])
        else:
            cur.extend(wins[i])
    if cur:
        chunks.append(_pack(cur))
    return chunks


def _pack(group: list[TranscriptSegment]) -> dict:
    return {
        "start": round(group[0].start, 1),
        "end": round(group[-1].end, 1),
        "text": " ".join(s.text for s in group).strip(),
    }


def transcript_with_timestamps(chunks: list[dict], limit: int = 12000) -> str:
    """Render chunks as a timestamped block for prompt injection (capped)."""
    lines = []
    for c in chunks:
        lines.append(f"[{c['start']:.0f}s–{c['end']:.0f}s] {c['text']}")
    blob = "\n".join(lines)
    return blob[:limit]
