"""Anthropic Messages API adapter with structured output (output_config.format)."""

import base64
import time

import anthropic

from coursedeck.llm.base import (
    ImagePart,
    LLMRequest,
    LLMResponse,
    Message,
    PdfPart,
    TextPart,
    Usage,
)


def _b64(data: bytes) -> str:
    return base64.standard_b64encode(data).decode("ascii")


def _block(part) -> dict:
    if isinstance(part, TextPart):
        return {"type": "text", "text": part.text}
    if isinstance(part, ImagePart):
        return {"type": "image",
                "source": {"type": "base64", "media_type": part.media_type, "data": _b64(part.data)}}
    if isinstance(part, PdfPart):
        return {"type": "document",
                "source": {"type": "base64", "media_type": "application/pdf", "data": _b64(part.data)}}
    raise TypeError(f"unsupported part {type(part).__name__}")


def _message(m: Message) -> dict:
    return {"role": m.role, "content": [_block(p) for p in m.parts]}


class AnthropicAdapter:
    supports_pdf = True

    def __init__(self, model_id: str, effort: str | None = None,
                 timeout_s: float = 120.0, max_retries: int = 2,
                 client: anthropic.Anthropic | None = None):
        self.model_id = model_id
        self.effort = effort  # low | medium | high | xhigh | max; None = model default
        # The SDK retries 408/409/429/5xx, timeouts and connection errors with backoff.
        self.client = client or anthropic.Anthropic(timeout=timeout_s, max_retries=max_retries)

    def complete(self, request: LLMRequest) -> LLMResponse:
        output_config: dict = {"format": {"type": "json_schema", "schema": request.schema}}
        if self.effort:
            output_config["effort"] = self.effort
        started = time.perf_counter()
        resp = self.client.messages.create(
            model=self.model_id,
            max_tokens=request.max_tokens,
            # The system prompt is identical for every document, so cache it.
            system=[{"type": "text", "text": request.system,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[_message(m) for m in request.messages],
            output_config=output_config,
        )
        latency = time.perf_counter() - started
        u = resp.usage
        return LLMResponse(
            text="".join(b.text for b in resp.content if b.type == "text"),
            stop_reason=resp.stop_reason or "unknown",
            usage=Usage(
                input_tokens=u.input_tokens,
                output_tokens=u.output_tokens,
                cache_read_tokens=u.cache_read_input_tokens or 0,
                cache_write_tokens=u.cache_creation_input_tokens or 0,
            ),
            latency_s=latency,
            request_id=resp._request_id,
        )
