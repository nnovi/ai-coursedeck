"""Model registry: aliases used in experiments, provider, model id and prices."""

from dataclasses import dataclass

from coursedeck.llm.base import Adapter, Usage


@dataclass(frozen=True)
class ModelSpec:
    alias: str
    provider: str  # anthropic | ollama
    model_id: str
    # USD per 1M tokens; cache writes cost 1.25x input and reads 0.1x input on Anthropic.
    input_price: float = 0.0
    output_price: float = 0.0
    # Some models charge more once the prompt exceeds a threshold (tokens): (threshold, in, out).
    long_prompt: tuple[int, float, float] | None = None

    def cost(self, usage: Usage) -> float:
        inp, out = self.input_price, self.output_price
        if self.long_prompt and usage.prompt_tokens > self.long_prompt[0]:
            _, inp, out = self.long_prompt
        return (
            usage.input_tokens * inp
            + usage.cache_write_tokens * inp * 1.25
            + usage.cache_read_tokens * inp * 0.1
            + usage.output_tokens * out
        ) / 1e6


MODELS: dict[str, ModelSpec] = {
    m.alias: m
    for m in [
        ModelSpec("haiku", "anthropic", "claude-haiku-5-5", 0.10, 0.50,
                  long_prompt=(100_000, 0.50, 2.50)),
        ModelSpec("sonnet", "anthropic", "claude-sonnet-5-5", 2.00, 10.00),
        # Local models: no per-token price (hardware and electricity are not counted).
        ModelSpec("qwen3-vl-8b", "ollama", "qwen3-vl:8b-instruct"),
        ModelSpec("qwen3-vl-4b", "ollama", "qwen3-vl:4b-instruct"),
    ]
}


def make_adapter(spec: ModelSpec, effort: str | None = None,
                 temperature: float | None = None) -> Adapter:
    if spec.provider == "anthropic":
        if temperature is not None:
            raise ValueError("current Claude models reject non-default temperature; use effort")
        from coursedeck.llm.anthropic_adapter import AnthropicAdapter

        return AnthropicAdapter(spec.model_id, effort=effort)
    if spec.provider == "ollama":
        if effort is not None:
            raise ValueError("effort is an Anthropic setting; use temperature for Ollama models")
        from coursedeck.llm.ollama_adapter import OllamaAdapter
        from coursedeck.schema import LIST_LIMITS

        return OllamaAdapter(spec.model_id, temperature=temperature, max_items=LIST_LIMITS)
    raise ValueError(f"unknown provider {spec.provider}")
