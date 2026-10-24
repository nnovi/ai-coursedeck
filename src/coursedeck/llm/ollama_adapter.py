"""Ollama /api/chat adapter for local vision models (e.g. Qwen3-VL) with JSON-schema output."""

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

DEFAULT_HOST = "http://localhost:11434"
# A card is ~300-600 tokens; the cap bounds a runaway JSON-whitespace loop of a local model.
MAX_OUTPUT_TOKENS = 4096
STOP_REASONS = {"stop": "end_turn", "length": "max_tokens"}


def _message(m: Message) -> dict:
    """Ollama takes one text string plus a list of images per message.

    Images keep their order; the text marks pages ("--- Page N ---") so the model can match
    them, since the interleaving of text and images is not preserved.
    """
    text, images = [], []
    for p in m.parts:
        if isinstance(p, TextPart):
            text.append(p.text)
        elif isinstance(p, ImagePart):
            images.append(base64.standard_b64encode(p.data).decode("ascii"))
        elif isinstance(p, PdfPart):
            raise TypeError("Ollama models do not read PDFs; render pages to images instead")
    msg: dict = {"role": m.role, "content": "\n\n".join(text)}
    if images:
        msg["images"] = images
    return msg


class OllamaAdapter:
    supports_pdf = False

    def __init__(self, model_id: str, temperature: float | None = None, num_ctx: int = 65536,
                 host: str | None = None, timeout_s: float = 1800,
                 max_items: dict[str, int] | None = None):
        self.model_id = model_id
        self.temperature = temperature
        # maxItems per top-level list field; the JSON grammar then forces lists to end
        self.max_items = max_items or {}
        self.num_ctx = num_ctx  # page images take many tokens; the default 4K context is too small
        self.host = (host or os.environ.get("OLLAMA_HOST") or DEFAULT_HOST).rstrip("/")
        self.client = httpx.Client(timeout=timeout_s)

    def _schema(self, schema: dict) -> dict:
        if not self.max_items:
            return schema
        props = {k: dict(v) for k, v in schema["properties"].items()}
        for field, limit in self.max_items.items():
            if props.get(field, {}).get("type") == "array":
                props[field]["maxItems"] = limit
        return {**schema, "properties": props}

    def complete(self, request: LLMRequest) -> LLMResponse:
        options: dict = {"num_ctx": self.num_ctx,
                         "num_predict": min(request.max_tokens, MAX_OUTPUT_TOKENS)}
        if self.temperature is not None:
            options["temperature"] = self.temperature
        payload = {
            "model": self.model_id,
            "messages": [{"role": "system", "content": request.system}]
                        + [_message(m) for m in request.messages],
            "format": self._schema(request.schema),
            "stream": False,
            "options": options,
        }
        started = time.perf_counter()
        r = self.client.post(f"{self.host}/api/chat", json=payload)
        r.raise_for_status()
        data = r.json()
        latency = time.perf_counter() - started
        return LLMResponse(
            text=data["message"]["content"],
            stop_reason=STOP_REASONS.get(data.get("done_reason", ""), data.get("done_reason", "")),
            usage=Usage(input_tokens=data.get("prompt_eval_count", 0),
                        output_tokens=data.get("eval_count", 0)),
            latency_s=latency,
            extra={"load_duration_s": data.get("load_duration", 0) / 1e9},
        )
