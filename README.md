# transcript2

YouTube → **executive Japanese presentation** generation pipeline.

Given a YouTube URL, it reconstructs the video's *intellectual structure* (not a
chronological summary), re-tells it as a consulting-style executive story, and
writes every slide in concise business Japanese with implication-driven
headlines — then emits structured slide JSON, a Canva-ready spec, and a `.pptx`.

Fully local: LLM via **Ollama** (`qwen2.5:7b`), embeddings via
`nomic-embed-text`. No external API keys.

## Pipeline

```
URL → metadata (yt-dlp)
    → transcript (youtube-transcript-api → faster-whisper fallback)
    → semantic chunking (nomic-embed-text)
    → structural analysis      ← reconstruct the ARGUMENT, keep timestamps
    → narrative planning       ← map onto executive arc (課題→分析→提言)
    → per-slide JP writing     ← consulting register, So-What headlines
    → frame attachment (yt-dlp + ffmpeg key frames)
    → emit: slides.json + canva_spec.json + deck.pptx
```

Every stage writes a typed artifact to `output/<video_id>/` for traceability.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
# faster-whisper fallback is optional:
.venv/bin/pip install -e ".[whisper]"
ollama serve   # qwen2.5:7b + nomic-embed-text must be pulled
```

## Usage

```bash
transcript2 "https://www.youtube.com/watch?v=VIDEO_ID" --slides 12
transcript2 VIDEO_ID --no-pptx --model gpt-oss:20b
```

### Output schema (`slides.json`)

```json
{ "slides": [ {
  "title": "", "message": "", "bullets": [],
  "speaker_notes": "", "visual_type": "", "image_prompt": "", "layout": ""
} ] }
```

## Canva integration

`canva_spec.json` is a connector-ready spec. The agent drives the **Canva MCP
connector** (`mcp__claude_ai_Canva__generate-design-structured`,
`upload-asset-from-url`, `export-design`) to build and export the live deck —
no Canva Connect OAuth app required.

## Config (env vars)

| Var | Default | Purpose |
|-----|---------|---------|
| `T2_LLM_MODEL` | `qwen2.5:7b` | Ollama model |
| `T2_EMBED_MODEL` | `nomic-embed-text:latest` | chunking embeddings |
| `T2_TARGET_SLIDES` | `12` | target slide count |
| `T2_FRAMES` | `1` | extract YouTube frames |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama endpoint |
