"""CLI entrypoint:  transcript2 <youtube_url> [--no-pptx] [--slides N]"""

from __future__ import annotations

import argparse
import sys

from .config import CONFIG
from .pipeline import run


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="transcript2",
        description="YouTube → executive Japanese presentation pipeline.",
    )
    ap.add_argument("url", help="YouTube URL or 11-char video id")
    ap.add_argument("--no-pptx", action="store_true", help="skip PPTX rendering")
    ap.add_argument("--slides", type=int, default=None, help="target slide count")
    ap.add_argument("--model", default=None, help="override Ollama LLM model")
    args = ap.parse_args(argv)

    if args.slides:
        CONFIG.target_slides = args.slides
    if args.model:
        CONFIG.llm_model = args.model

    try:
        res = run(args.url, make_pptx=not args.no_pptx)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    print("\nArtifacts:")
    print(f"  slides.json   {res.slides_json}")
    print(f"  canva_spec    {res.canva_spec}")
    if res.pptx:
        print(f"  deck.pptx     {res.pptx}")
    print(f"  (full run)    {res.run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
