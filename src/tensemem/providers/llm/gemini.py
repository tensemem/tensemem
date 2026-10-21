"""Gemini generateContent adapter. Uses the REST API so timeouts are real."""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable, Mapping, Sequence
from enum import StrEnum
from typing import TypeVar, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pydantic import BaseModel, ValidationError

from tensemem.core.models import (
    Cardinality,
    ExtractedOp,
    ExtractionResult,
    Modality,
    OpKind,
    ValidPrecision,
)
from tensemem.providers.llm.base import ProviderError, last_user_text

T = TypeVar("T", bound=BaseModel)
E = TypeVar("E", bound=StrEnum)

_API = "https://generativelanguage.googleapis.com/v1beta/models"
_TIMEOUT_SECONDS = 45.0
_RETRIES = 2
_RETRY_STATUSES = {429, 503}
Post = Callable[[str, bytes, dict[str, str], float], tuple[int, bytes]]


class GeminiProvider:
    def __init__(
        self,
        model: str = "gemini-3.6-flash",
        *,
        fallbacks: Sequence[str] = (),
        post: Post | None = None,
    ) -> None:
        self.model = _bare_model(model)
        self.cache_namespace = "gemini"
        self._fallbacks = tuple(_bare_model(item) for item in fallbacks)
        self._post = post

    def structured(
        self,
        messages: Sequence[Mapping[str, str]],
        schema: type[T],
        **kwargs: object,
    ) -> T:
        del kwargs
        key = _api_key()
        last = "gemini request failed"
        for model in _models(self.model, self._fallbacks):
            for attempt in range(_RETRIES):
                try:
                    status, raw = _post(
                        self._post,
                        _url(model),
                        _payload(messages),
                        {"Content-Type": "application/json", "x-goog-api-key": key},
                        _TIMEOUT_SECONDS,
                    )
                except TimeoutError:
                    last = f"Timeout model={model} after {_TIMEOUT_SECONDS}s"
                    print(f"tensemem extract: {last}", file=sys.stderr)
                    continue
                except ProviderError as extra:
                    last = str(extra)
                    if attempt + 1 < _RETRIES:
                        continue
                    raise
                print(f"tensemem extract: gemini model={model} http={status}", file=sys.stderr)
                if status in _RETRY_STATUSES:
                    last = _http_error(model, status, raw)
                    continue
                if status >= 400:
                    raise ProviderError(_http_error(model, status, raw))
                parsed = _parse(schema, raw, model=model)
                if isinstance(parsed, ExtractionResult):
                    return _with_quotes(parsed, messages)
                return parsed
        raise ProviderError(last)


def _bare_model(name: str) -> str:
    text = name.strip()
    if text.startswith("gemini/"):
        return text[7:].strip() or "gemini-3.6-flash"
    return text or "gemini-3.6-flash"


def _models(primary: str, fallbacks: Sequence[str]) -> tuple[str, ...]:
    seen: list[str] = []
    for item in (primary, *fallbacks):
        if item and item not in seen:
            seen.append(item)
    return tuple(seen)


def _api_key() -> str:
    key = (
        os.environ.get("GEMINI_API_KEY", "").strip() or os.environ.get("GOOGLE_API_KEY", "").strip()
    )
    if not key:
        raise ProviderError("GEMINI_API_KEY is missing")
    return key


def _url(model: str) -> str:
    return f"{_API}/{model}:generateContent"


def _payload(messages: Sequence[Mapping[str, str]]) -> bytes:
    system: list[str] = []
    contents: list[dict[str, object]] = []
    for message in messages:
        role = str(message.get("role") or "user")
        text = str(message.get("content") or "")
        if role == "system":
            system.append(text)
            continue
        contents.append(
            {
                "role": "model" if role == "assistant" else "user",
                "parts": [{"text": text}],
            }
        )
    body: dict[str, object] = {
        "contents": contents or [{"role": "user", "parts": [{"text": ""}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": _RESPONSE_SCHEMA,
        },
    }
    if system:
        body["system_instruction"] = {"parts": [{"text": "\n".join(system)}]}
    return json.dumps(body).encode()


def _post(
    injected: Post | None,
    url: str,
    payload: bytes,
    headers: dict[str, str],
    timeout: float,
) -> tuple[int, bytes]:
    if injected is not None:
        return injected(url, payload, headers, timeout)
    request = Request(url, data=payload, headers=headers, method="POST")
    try:
        with urlopen(request, timeout=timeout) as response:
            return int(response.status), response.read()
    except HTTPError as extra:
        return int(extra.code), extra.read()
    except TimeoutError as extra:
        raise extra
    except URLError as extra:
        reason = extra.reason
        if isinstance(reason, TimeoutError | OSError) and "timed out" in str(reason).casefold():
            raise TimeoutError(str(reason)) from extra
        raise ProviderError(f"gemini unreachable: {reason}") from extra


def _http_error(model: str, status: int, raw: bytes) -> str:
    detail = raw.decode("utf-8", errors="replace").replace("\n", " ")[:220]
    return f"HTTP {status} model={model}: {detail}"


def _with_quotes(
    result: ExtractionResult, messages: Sequence[Mapping[str, str]]
) -> ExtractionResult:
    quote = last_user_text(messages)
    if not quote:
        return result
    filled: list[ExtractedOp] = []
    for op in result.ops:
        if op.evidence and op.evidence in quote:
            filled.append(op)
            continue
        filled.append(op.model_copy(update={"evidence": quote}))
    return result.model_copy(update={"ops": tuple(filled)})


def _parse(schema: type[T], raw: bytes, *, model: str) -> T:
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as extra:
        raise ProviderError(f"gemini {model} returned non-JSON") from extra
    body = _as_map(parsed)
    if body is None:
        raise ProviderError(f"gemini {model} returned an unusable payload")
    text = _candidate_text(body)
    if not text:
        raise ProviderError(f"gemini {model} returned an empty structured response")
    try:
        payload = _coerce_result(_loads_json(text))
        return schema.model_validate(payload)
    except (ValidationError, ValueError, TypeError, json.JSONDecodeError) as extra:
        detail = _validation_detail(extra)
        raise ProviderError(
            f"gemini {model} returned an unusable structured response ({detail})"
        ) from extra


def _candidate_text(body: Mapping[str, object]) -> str:
    parts = _parts(body)
    texts: list[str] = []
    for part in parts:
        if part.get("thought") is True:
            continue
        text = part.get("text")
        if isinstance(text, str) and text.strip():
            texts.append(text.strip())
    for text in reversed(texts):
        if _looks_like_json(text):
            return text
    return texts[-1] if texts else ""


def _parts(body: Mapping[str, object]) -> list[Mapping[str, object]]:
    candidates = _as_list(body.get("candidates"))
    if not candidates:
        return []
    first = _as_map(candidates[0])
    if first is None:
        return []
    content = _as_map(first.get("content"))
    if content is None:
        return []
    return [part for item in _as_list(content.get("parts")) if (part := _as_map(item))]


def _looks_like_json(text: str) -> bool:
    stripped = _strip_fence(text).lstrip()
    return stripped.startswith("{") or stripped.startswith("[")


def _loads_json(text: str) -> object:
    stripped = _strip_fence(text)
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start >= 0 and end > start:
            return json.loads(stripped[start : end + 1])
        raise


def _strip_fence(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _coerce_result(payload: object) -> dict[str, object]:
    ops = [_clean_op(item) for item in _ops_from(payload)]
    return {"ops": [op for op in ops if op is not None]}


def _ops_from(payload: object) -> list[object]:
    listed = _as_list(payload)
    if listed:
        return listed
    mapped = _as_map(payload)
    if mapped is None:
        return []
    for key in ("ops", "operations", "facts", "items"):
        value = _as_list(mapped.get(key))
        if value:
            return value
    for value in mapped.values():
        found = _ops_from(value)
        if found:
            return found
    return []


def _clean_op(raw: object) -> dict[str, object] | None:
    mapped = _as_map(raw)
    if mapped is None:
        return None
    predicate = str(mapped.get("predicate") or mapped.get("key") or "").strip()
    obj = mapped.get("object")
    if obj is None:
        obj = mapped.get("value") or mapped.get("object_value") or mapped.get("obj")
    obj_text = str(obj or "").strip()
    if not predicate or not obj_text:
        return None
    cleaned: dict[str, object] = {
        "subject": str(mapped.get("subject") or "user").strip() or "user",
        "predicate": predicate,
        "object": obj_text,
        "op": _enum(mapped.get("op") or mapped.get("operation"), OpKind, OpKind.SET).value,
        "modality": _enum(mapped.get("modality"), Modality, Modality.ASSERTED).value,
        "valid_precision": _enum(
            mapped.get("valid_precision"), ValidPrecision, ValidPrecision.UNKNOWN
        ).value,
        "evidence": str(mapped.get("evidence") or ""),
        "is_confirmation": bool(mapped.get("is_confirmation", False)),
    }
    valid_from = mapped.get("valid_from")
    if isinstance(valid_from, str) and valid_from.strip():
        cleaned["valid_from"] = valid_from.strip()
    confidence = mapped.get("confidence")
    if isinstance(confidence, int | float):
        cleaned["confidence"] = max(0.0, min(1.0, float(confidence)))
    predicate_spec = _clean_predicate(mapped.get("new_predicate"))
    if predicate_spec is None:
        predicate_spec = {"name": predicate, "cardinality": Cardinality.MANY.value}
    cleaned["new_predicate"] = predicate_spec
    return cleaned


def _clean_predicate(raw: object) -> dict[str, object] | None:
    if isinstance(raw, str) and raw.strip():
        return {"name": raw.strip()}
    mapped = _as_map(raw)
    if mapped is None:
        return None
    name = str(mapped.get("name") or "").strip()
    if not name:
        return None
    return {
        "name": name,
        "cardinality": _enum(mapped.get("cardinality"), Cardinality, Cardinality.ONE).value,
        "description": str(mapped.get("description") or ""),
    }


def _as_map(raw: object) -> dict[str, object] | None:
    if not isinstance(raw, dict):
        return None
    return cast(dict[str, object], raw)


def _as_list(raw: object) -> list[object]:
    if not isinstance(raw, list):
        return []
    return cast(list[object], raw)


def _enum(raw: object, choices: type[E], default: E) -> E:
    text = str(raw or "").strip()
    if not text:
        return default
    folded = text.replace("-", "_").replace(" ", "_")
    for item in choices:
        if item.value.casefold() == folded.casefold() or item.name.casefold() == folded.casefold():
            return item
    return default


def _validation_detail(extra: Exception) -> str:
    if isinstance(extra, ValidationError) and extra.errors():
        first = extra.errors()[0]
        loc = ".".join(str(part) for part in first.get("loc", ()))
        return f"{loc} {first.get('type')}"
    return type(extra).__name__


_RESPONSE_SCHEMA: dict[str, object] = {
    "type": "OBJECT",
    "properties": {
        "ops": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "subject": {"type": "STRING"},
                    "predicate": {"type": "STRING"},
                    "object": {"type": "STRING"},
                    "op": {
                        "type": "STRING",
                        "enum": ["SET", "ADD", "REMOVE", "RETRACT", "REPLACE_SET", "DENY"],
                    },
                    "modality": {
                        "type": "STRING",
                        "enum": ["asserted", "planned", "hypothetical", "negated"],
                    },
                    "valid_precision": {
                        "type": "STRING",
                        "enum": ["instant", "day", "month", "year", "unknown"],
                    },
                    "confidence": {"type": "NUMBER"},
                    "evidence": {"type": "STRING"},
                    "is_confirmation": {"type": "BOOLEAN"},
                    "new_predicate": {
                        "type": "OBJECT",
                        "properties": {
                            "name": {"type": "STRING"},
                            "cardinality": {"type": "STRING", "enum": ["ONE", "MANY"]},
                            "description": {"type": "STRING"},
                        },
                        "required": ["name"],
                    },
                },
                "required": ["subject", "predicate", "object", "op"],
            },
        }
    },
    "required": ["ops"],
}
