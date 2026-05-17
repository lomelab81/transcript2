"""YouTube ingestion: metadata + key-frame extraction via yt-dlp + ffmpeg."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import yt_dlp

from ..schema import VideoMeta

_ID_RE = re.compile(r"(?:v=|youtu\.be/|/shorts/|/embed/)([0-9A-Za-z_-]{11})")


def parse_video_id(url: str) -> str:
    m = _ID_RE.search(url)
    if m:
        return m.group(1)
    if re.fullmatch(r"[0-9A-Za-z_-]{11}", url):
        return url
    raise ValueError(f"Could not parse a YouTube video id from: {url!r}")


def fetch_meta(url: str) -> VideoMeta:
    vid = parse_video_id(url)
    opts = {"quiet": True, "skip_download": True, "no_warnings": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    return VideoMeta(
        video_id=vid,
        url=f"https://www.youtube.com/watch?v={vid}",
        title=info.get("title", ""),
        author=info.get("uploader", ""),
        duration=float(info.get("duration", 0) or 0),
        description=(info.get("description", "") or "")[:2000],
    )


def _download_video(url: str, dest: Path) -> Path | None:
    """Download a low-res stream just for frame grabbing."""
    target = dest / "source.mp4"
    if target.exists():
        return target
    opts = {
        "quiet": True,
        "no_warnings": True,
        "format": "bv*[height<=480]+ba/b[height<=480]/worst",
        "outtmpl": str(target),
        "merge_output_format": "mp4",
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])
        return target if target.exists() else None
    except Exception:
        return None


def extract_frames(url: str, run_dir: Path, timestamps: list[float]) -> dict[float, str]:
    """Grab frames at the given timestamps. Returns {timestamp: image_path}.

    Degrades gracefully — if download or ffmpeg fails, returns {}.
    """
    if not timestamps:
        return {}
    video = _download_video(url, run_dir)
    if not video:
        return {}
    frames_dir = run_dir / "frames"
    out: dict[float, str] = {}
    for ts in timestamps:
        ts = max(ts, 0.0)
        img = frames_dir / f"frame_{int(ts):06d}.jpg"
        cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-ss", str(ts), "-i", str(video),
            "-frames:v", "1", "-q:v", "3", str(img),
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=60)
            if img.exists():
                out[ts] = str(img)
        except (subprocess.SubprocessError, OSError):
            continue
    return out
