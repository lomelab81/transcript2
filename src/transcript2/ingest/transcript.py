"""Transcript retrieval.

Strategy:
  1. youtube-transcript-api  (preferred — fast, timestamped)
  2. faster-whisper          (fallback when captions are unavailable)

The faster-whisper import is lazy + guarded: on Python 3.14 the ctranslate2
wheel may be missing, so the pipeline degrades gracefully and reports it.
"""

from __future__ import annotations

from pathlib import Path

from ..config import CONFIG
from ..schema import TranscriptSegment, VideoMeta


def _via_captions(video_id: str) -> list[TranscriptSegment]:
    from youtube_transcript_api import YouTubeTranscriptApi  # noqa: PLC0415

    prefs = ["ja", "en", "en-US", "en-GB"]

    # Support both the 0.6.x and 1.x APIs.
    raw = None
    try:  # newer 1.x instance API
        api = YouTubeTranscriptApi()
        try:
            fetched = api.fetch(video_id, languages=prefs)
        except Exception:
            tlist = api.list(video_id)
            fetched = tlist.find_transcript(prefs).fetch()
        raw = [
            {"text": s.text, "start": s.start, "duration": s.duration}
            for s in fetched
        ]
    except Exception:
        raw = None

    if raw is None:  # legacy 0.6.x classmethod API
        get = getattr(YouTubeTranscriptApi, "get_transcript", None)
        if get is None:
            raise RuntimeError("Unsupported youtube-transcript-api version")
        raw = get(video_id, languages=prefs)

    return [
        TranscriptSegment(
            start=float(r["start"]),
            duration=float(r.get("duration", 0.0)),
            text=r["text"].replace("\n", " ").strip(),
        )
        for r in raw
        if r.get("text", "").strip()
    ]


def _via_whisper(url: str, run_dir: Path) -> list[TranscriptSegment]:
    try:
        from faster_whisper import WhisperModel  # noqa: PLC0415
    except Exception as e:  # pragma: no cover - env dependent
        raise RuntimeError(
            f"faster-whisper unavailable ({e}); no captions and no ASR fallback."
        ) from e

    import yt_dlp  # noqa: PLC0415

    audio = run_dir / "audio.m4a"
    if not audio.exists():
        opts = {
            "quiet": True,
            "no_warnings": True,
            "format": "bestaudio/best",
            "outtmpl": str(run_dir / "audio.%(ext)s"),
            "postprocessors": [
                {"key": "FFmpegExtractAudio", "preferredcodec": "m4a"}
            ],
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])
        cand = list(run_dir.glob("audio.*"))
        if cand:
            audio = cand[0]

    model = WhisperModel(CONFIG.whisper_model, device="cpu", compute_type="int8")
    segments, _ = model.transcribe(str(audio), vad_filter=True)
    return [
        TranscriptSegment(
            start=float(s.start),
            duration=float(s.end - s.start),
            text=s.text.strip(),
        )
        for s in segments
        if s.text.strip()
    ]


def get_transcript(
    url: str, meta: VideoMeta, run_dir: Path
) -> list[TranscriptSegment]:
    try:
        segs = _via_captions(meta.video_id)
        if segs:
            meta.transcript_source = "captions"
            return segs
    except Exception as e:
        print(f"[transcript] captions unavailable: {e}")

    print("[transcript] falling back to faster-whisper ASR…")
    segs = _via_whisper(url, run_dir)
    meta.transcript_source = "whisper"
    return segs
