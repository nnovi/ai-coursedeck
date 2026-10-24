"""Two-layer LLM client: provider-neutral request/response types plus provider adapters."""

from coursedeck.llm.base import (
    Adapter,
    ImagePart,
    LLMRequest,
    LLMResponse,
    Message,
    PdfPart,
    TextPart,
    Usage,
)
from coursedeck.llm.models import MODELS, ModelSpec, make_adapter

__all__ = [
    "MODELS",
    "Adapter",
    "ImagePart",
    "LLMRequest",
    "LLMResponse",
    "Message",
    "ModelSpec",
    "PdfPart",
    "TextPart",
    "Usage",
    "make_adapter",
]
