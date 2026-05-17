"""Pydantic data contracts shared across the pipeline.

The schema is the backbone of the agent-friendly design: every stage reads
and writes typed objects, and the final slide deck conforms exactly to the
user-requested output schema.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

# --------------------------------------------------------------------------- #
# Ingestion
# --------------------------------------------------------------------------- #


class TranscriptSegment(BaseModel):
    """A timestamped unit of spoken content."""

    start: float = Field(..., description="Start time in seconds")
    duration: float = Field(0.0, description="Duration in seconds")
    text: str

    @property
    def end(self) -> float:
        return self.start + self.duration


class VideoMeta(BaseModel):
    video_id: str
    url: str
    title: str = ""
    author: str = ""
    duration: float = 0.0
    description: str = ""
    language: str = "unknown"
    transcript_source: Literal["captions", "whisper", "none"] = "none"


# --------------------------------------------------------------------------- #
# Analysis — preserve the ORIGINAL intellectual structure of the video
# --------------------------------------------------------------------------- #


class Insight(BaseModel):
    text: str
    kind: Literal["insight", "example", "framework", "data", "emphasis"] = "insight"
    start: float = 0.0
    end: float = 0.0


class Section(BaseModel):
    """A coherent topical section as it appeared in the source video."""

    title: str
    summary: str = ""
    start: float = 0.0
    end: float = 0.0
    insights: list[Insight] = Field(default_factory=list)
    transition_in: str = Field(
        "", description="How the speaker moved INTO this section"
    )


class VideoStructure(BaseModel):
    """The reconstructed argument of the video — not a chronological summary."""

    thesis: str = Field("", description="The central argument / through-line")
    sections: list[Section] = Field(default_factory=list)
    frameworks: list[str] = Field(default_factory=list)
    narrative_arc: str = Field(
        "", description="How the speaker builds the argument start→end"
    )


# --------------------------------------------------------------------------- #
# Composition — executive presentation
# --------------------------------------------------------------------------- #

SlideLayout = Literal[
    "title",
    "agenda",
    "section",
    "content",
    "two_column",
    "quote",
    "data",
    "closing",
]

VisualType = Literal["frame", "generated", "icon", "none"]


class Slide(BaseModel):
    """Conforms to the user-requested output schema (plus traceability)."""

    title: str = Field("", description="Implication-driven business headline (JP)")
    message: str = Field("", description="One-line key message / so-what (JP)")
    bullets: list[str] = Field(default_factory=list)
    speaker_notes: str = ""
    visual_type: VisualType = "none"
    image_prompt: str = ""
    layout: SlideLayout = "content"
    # Traceability — not in the minimal schema but required by system behavior.
    source_timestamps: list[float] = Field(default_factory=list)
    image_path: Optional[str] = None


class Deck(BaseModel):
    title: str = ""
    subtitle: str = ""
    language: str = "ja"
    slides: list[Slide] = Field(default_factory=list)
    meta: Optional[VideoMeta] = None

    def to_output(self) -> dict:
        """Emit the exact schema the user asked for."""
        return {
            "slides": [
                {
                    "title": s.title,
                    "message": s.message,
                    "bullets": s.bullets,
                    "speaker_notes": s.speaker_notes,
                    "visual_type": s.visual_type,
                    "image_prompt": s.image_prompt,
                    "layout": s.layout,
                }
                for s in self.slides
            ]
        }
