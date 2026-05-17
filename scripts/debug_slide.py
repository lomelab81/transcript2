"""Reproduce a single slide-writing call and dump the RAW model output."""
import json
from transcript2.llm import prompts
from transcript2.llm.ollama_client import chat
from transcript2.schema import Slide, VideoStructure
from transcript2.compose.narrative import DeckPlan, evidence_for

structure = VideoStructure.model_validate(json.load(open("output/4XqVR6xI6Kw/structure.json")))
plan = DeckPlan.model_validate(json.load(open("output/4XqVR6xI6Kw/plan.json")))
sp = plan.slides[1]  # background, has timestamps

evidence = evidence_for(structure, sp.source_timestamps)
user = prompts.SLIDE_USER.format(
    purpose=sp.purpose, intent=sp.intent,
    working_title=sp.working_title, evidence=evidence, thesis=structure.thesis,
)
schema = json.dumps(Slide.model_json_schema(), ensure_ascii=False)
full = f"{user}\n\nRespond with a single JSON object matching this JSON schema:\n{schema}"

raw = chat(prompts.SLIDE_SYS, full, temperature=0.4, json_mode=True)
print("=== RAW (len", len(raw), ") ===")
print(raw[:1500])
