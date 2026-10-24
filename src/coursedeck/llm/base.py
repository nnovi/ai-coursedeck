"""Provider-neutral request/response types. Adapters translate them to each provider's API."""

from dataclasses import dataclass, field
from typing import Literal, Protocol


@dataclass(frozen=True)
class TextPart:
    text: str


@dataclass(frozen=True)
class ImagePart:
    data: bytes
    media_type: str = "image/png"


@dataclass(frozen=True)
class PdfPart:
    """A whole PDF, for providers that read PDFs natively (text layer + page images)."""

    data: bytes


Part = TextPart | ImagePart | PdfPart


@dataclass
class Message:
    role: Literal["user", "assistant"]
    parts: list[Part]


@dataclass
class LLMRequest:
    system: str
    messages: list[Message]
    schema: dict  # JSON schema the reply must follow (structured output)
    max_tokens: int = 16000


@dataclass
class Usage:
    input_tokens: int = 0  # uncached input
    output_tokens: int = 0  # includes thinking tokens where the provider bills them as output
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(
            self.input_tokens + other.input_tokens,
            self.output_tokens + other.output_tokens,
            self.cache_read_tokens + other.cache_read_tokens,
            self.cache_write_tokens + other.cache_write_tokens,
        )

    @property
    def prompt_tokens(self) -> int:
        return self.input_tokens + self.cache_read_tokens + self.cache_write_tokens


@dataclass
class LLMResponse:
    text: str
    stop_reason: str  # normalized: end_turn | max_tokens | refusal | other provider values
    usage: Usage
    latency_s: float
    request_id: str | None = None
    extra: dict = field(default_factory=dict)


class Adapter(Protocol):
    supports_pdf: bool

    def complete(self, request: LLMRequest) -> LLMResponse: ...
