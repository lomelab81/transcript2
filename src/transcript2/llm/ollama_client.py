"""Thin, robust client for a local Ollama instance.

Provides:
  * chat_json()  — structured JSON generation with schema coercion + retries
  * embed()      — embeddings for semantic chunking

No external API keys: everything runs against the local Ollama daemon.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any, Optional, Type, TypeVar

import requests
from pydantic import BaseModel, ValidationError

from ..config import CONFIG

T = TypeVar("T", bound=BaseModel)

_JSON_BLOCK = re.compile(r"\{.*\}|\[.*\]", re.DOTALL)


class OllamaError(RuntimeError):
    pass


def _post(path: str, payload: dict, timeout: int) -> dict:
    url = f"{CONFIG.ollama_host}{path}"
    try:
        r = requests.post(url, json=payload, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:  # pragma: no cover - network
        raise OllamaError(f"Ollama request failed ({url}): {e}") from e


def _extract_json(raw: str) -> Any:
    """Best-effort recovery of a JSON object from a model response."""
    raw = raw.strip()
    # Strip code fences.
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-zA-Z]*\n?|\n?```$", "", raw).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    m = _JSON_BLOCK.search(raw)
    if m:
        return json.loads(m.group(0))
    raise OllamaError(f"No JSON found in model output: {raw[:200]!r}")


def chat(
    system: str,
    user: str,
    *,
    model: Optional[str] = None,
    temperature: float = 0.3,
    json_mode: bool = False,
) -> str:
    payload = {
        "model": model or CONFIG.llm_model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
        "options": {"temperature": temperature, "num_ctx": 8192},
    }
    if json_mode:
        payload["format"] = "json"
    data = _post("/api/chat", payload, CONFIG.llm_timeout)
    return data.get("message", {}).get("content", "")


_PY_EXAMPLE = {
    "str": "...",
    "int": 0,
    "float": 0.0,
    "bool": False,
}


def _field_guide(
    model_cls: Type[BaseModel], exclude: frozenset[str]
) -> tuple[str, dict]:
    """Build a concise field list + a filled-in example skeleton.

    A 7B model follows a concrete example far more reliably than a raw JSON
    Schema (which it tends to echo as `{description, properties}`).
    Internal/traceability fields are excluded so the model never fabricates
    them (they are set programmatically afterwards).
    """
    lines: list[str] = []
    example: dict = {}
    for name, f in model_cls.model_fields.items():
        if name in exclude:
            continue
        ann = f.annotation
        ann_name = getattr(ann, "__name__", str(ann))
        desc = f.description or ""
        origin = getattr(ann, "__origin__", None)
        if origin in (list, set) or ann_name == "list":
            example[name] = ["..."]
            kind = "array of strings"
        elif ann_name in ("int", "float"):
            example[name] = 0
            kind = "number"
        elif ann_name == "bool":
            example[name] = False
            kind = "boolean"
        elif "Literal" in str(ann):
            opts = getattr(ann, "__args__", ())
            example[name] = opts[0] if opts else "..."
            kind = "one of: " + ", ".join(str(o) for o in opts)
        else:
            example[name] = "..."
            kind = "string"
        lines.append(f"  - {name} ({kind}){f': {desc}' if desc else ''}")
    return "\n".join(lines), example


def _unwrap(obj):
    """Recover the instance if the model echoed a JSON-Schema wrapper."""
    if isinstance(obj, dict):
        if "properties" in obj and isinstance(obj["properties"], dict) and (
            "type" in obj or "description" in obj or "$defs" in obj
            or set(obj.keys()) <= {"properties", "type", "description", "title", "required", "$defs"}
        ):
            return obj["properties"]
        if len(obj) == 1:
            (only,) = obj.values()
            if isinstance(only, dict):
                return only
    return obj


def chat_json(
    system: str,
    user: str,
    model_cls: Type[T],
    *,
    retries: int = 3,
    temperature: float = 0.2,
    exclude: Optional[set[str]] = None,
) -> T:
    """Generate JSON and validate it against a pydantic model.

    Injects a concrete field guide + example skeleton (not the raw JSON
    Schema) so small local models produce instances rather than echoing the
    schema. Retries with escalating explicitness; unwraps schema-echo shapes.
    `exclude` fields are kept out of generation and stripped from the reply.
    """
    excl = frozenset(exclude or ())
    guide, example = _field_guide(model_cls, excl)
    example_json = json.dumps(example, ensure_ascii=False, indent=2)
    last_err: Optional[Exception] = None
    for attempt in range(retries):
        hint = ""
        if attempt:
            hint = (
                f"\n\nYOUR PREVIOUS REPLY WAS INVALID: {last_err}\n"
                "Output ONLY the filled JSON object. Do NOT include 'properties', "
                "'type', or schema metadata. No markdown, no commentary."
            )
        full_user = (
            f"{user}\n\n"
            f"Return a single JSON object with EXACTLY these top-level keys "
            f"(fill the values, keep the keys):\n{guide}\n\n"
            f"Shape (replace the placeholder values):\n{example_json}{hint}"
        )
        try:
            raw = chat(
                system,
                full_user,
                model=model_cls.__dict__.get("_t2_model"),
                temperature=temperature,
                json_mode=True,
            )
            obj = _unwrap(_extract_json(raw))
            if isinstance(obj, dict):
                for k in excl:
                    obj.pop(k, None)
            inst = model_cls.model_validate(obj)
            # Guard against an all-empty parse slipping through as "valid".
            if not any(
                v not in (None, "", [], {}, 0, 0.0, False)
                for v in inst.model_dump().values()
            ):
                raise ValueError("model returned an empty object")
            return inst
        except (OllamaError, ValidationError, ValueError, json.JSONDecodeError) as e:
            last_err = e
            time.sleep(1.0 + attempt)
    raise OllamaError(f"chat_json failed after {retries} attempts: {last_err}")


def embed(texts: list[str], *, model: Optional[str] = None) -> list[list[float]]:
    out: list[list[float]] = []
    mdl = model or CONFIG.embed_model
    for t in texts:
        data = _post(
            "/api/embeddings",
            {"model": mdl, "prompt": t},
            CONFIG.llm_timeout,
        )
        out.append(data.get("embedding", []))
    return out


def ping() -> bool:
    try:
        requests.get(f"{CONFIG.ollama_host}/api/tags", timeout=5).raise_for_status()
        return True
    except requests.RequestException:
        return False
