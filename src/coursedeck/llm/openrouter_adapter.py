"""OpenRouter adapter (OpenAI-compatible chat completions) with strict JSON-schema output."""

import base64
import os
import time

import httpx

from coursedeck.llm.base import (
    ImagePart,
    LLMRequest,
    LLMResponse,
    Message,
    PdfPart,
    TextPart,
    Usage,
)

API_URL = "https://openrouter.ai/api/v1/chat/completions"
STOP_REASONS = {"stop": "end_turn", "length": "max_tokens", "content_filter": "refusal"}
RETRY_STATUS = {408, 429, 500, 502, 503, 504}


def inline_refs(schema: dict) -> dict:
    """Replace "$ref" with the referenced definition and drop "$defs".

    OpenAI strict mode rejects keywords next to "$ref" (Pydantic puts "description" there).
    """
    defs = schema.get("$defs", {})

    def walk(node):
        if isinstance(node, dict):
            if "$ref" in node:
                target = defs[node["$ref"].rsplit("/", 1)[-1]]
                rest = {k: v for k, v in node.items() if k != "$ref"}
                return walk({**target, **rest})
            return {k: walk(v) for k, v in node.items() if k != "$defs"}
        if isinstance(node, list):
            return [walk(v) for v in node]
        return node

    return walk(schema)


def _content(part) -> dict:
    if isinstance(part, TextPart):
        return {"type": "text", "text": part.text}
    if isinstance(part, ImagePart):
        b64 = base64.standard_b64encode(part.data).decode("ascii")
        return {"type": "image_url", "image_url": {"url": f"data:{part.media_type};base64,{b64}"}}
    if isinstance(part, PdfPart):
        raise TypeError("pdf mode is not wired for OpenRouter; render pages to images instead")
    raise TypeError(f"unsupported part {type(part).__name__}")


def _message(m: Message) -> dict:
    if m.role == "assistant":
        return {"role": "assistant", "content": "".join(p.text for p in m.parts)}
    return {"role": m.role, "content": [_content(p) for p in m.parts]}


class OpenRouterAdapter:
    supports_pdf = False

    def __init__(self, model_id: str, temperature: float | None = None,
                 top_p: float | None = None, api_key: str | None = None,
                 timeout_s: float = 120, retries: int = 2):
        self.model_id = model_id
        self.temperature = temperature
        self.top_p = top_p
        self.api_key = api_key or os.environ["OPENROUTER_API_KEY"]
        self.client = httpx.Client(timeout=timeout_s)
        self.retries = retries

    def _post(self, payload: dict) -> dict:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        for attempt in range(self.retries + 1):
            r = self.client.post(API_URL, json=payload, headers=headers)
            if r.status_code in RETRY_STATUS and attempt < self.retries:
                time.sleep(2 ** (attempt + 1))
                continue
            if r.is_error:
                raise RuntimeError(f"OpenRouter HTTP {r.status_code}: {r.text[:500]}")
            data = r.json()
            if "error" in data:  # OpenRouter may report upstream errors with HTTP 200
                raise RuntimeError(f"OpenRouter error: {data['error']}")
            return data
        raise RuntimeError("unreachable")

    def complete(self, request: LLMRequest) -> LLMResponse:
        payload: dict = {
            "model": self.model_id,
            "messages": [{"role": "system", "content": request.system}]
                        + [_message(m) for m in request.messages],
            "response_format": {"type": "json_schema", "json_schema": {
                "name": "lecture_card", "strict": True, "schema": inline_refs(request.schema)}},
            "max_tokens": request.max_tokens,
            "usage": {"include": True},  # returns the provider-billed cost
        }
        if self.temperature is not None:
            payload["temperature"] = self.temperature
        if self.top_p is not None:
            payload["top_p"] = self.top_p
        started = time.perf_counter()
        data = self._post(payload)
        latency = time.perf_counter() - started
        choice = data["choices"][0]
        u = data.get("usage") or {}
        cached = (u.get("prompt_tokens_details") or {}).get("cached_tokens", 0)
        return LLMResponse(
            text=choice["message"].get("content") or "",
            stop_reason=STOP_REASONS.get(choice.get("finish_reason"),
                                         choice.get("finish_reason") or "unknown"),
            usage=Usage(input_tokens=u.get("prompt_tokens", 0) - cached,
                        output_tokens=u.get("completion_tokens", 0),
                        cache_read_tokens=cached),
            latency_s=latency,
            request_id=data.get("id"),
            extra={"billed_cost_usd": u.get("cost"), "provider": data.get("provider")},
        )
