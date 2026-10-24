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
        # Cheap current GPT tier via OpenRouter (prices as listed by OpenRouter, Oct 2026).
        ModelSpec("gpt-6-luna", "openrouter", "openai/gpt-6-luna", 0.10, 0.50),
        # Local models: no per-token price (hardware and electricity are not counted).
        ModelSpec("qwen3-vl-8b", "ollama", "qwen3-vl:8b-instruct"),
        ModelSpec("qwen3-vl-4b", "ollama", "qwen3-vl:4b-instruct"),
    ]
}


@dataclass(frozen=True)
class Sampling:
    """Generation settings. None = provider default.

    Current Claude models reject non-default temperature/top_p, so their knob is effort;
    temperature/top_p apply to Ollama and OpenRouter models.
    """

    effort: str | None = None
    temperature: float | None = None
    top_p: float | None = None

    def label(self) -> str:
        parts = [f"{k}={v}" for k, v in vars(self).items() if v is not None]
        return ", ".join(parts) or "default"


def make_adapter(spec: ModelSpec, sampling: Sampling | None = None, timeout_s: float = 120.0,
                 max_retries: int = 2) -> Adapter:
    sampling = sampling or Sampling()
    if spec.provider == "anthropic":
        if sampling.temperature is not None or sampling.top_p is not None:
            raise ValueError("current Claude models reject non-default temperature/top_p; "
                             "use effort")
        from coursedeck.llm.anthropic_adapter import AnthropicAdapter

        return AnthropicAdapter(spec.model_id, effort=sampling.effort, timeout_s=timeout_s,
                                max_retries=max_retries)
    if sampling.effort is not None:
        raise ValueError("effort is an Anthropic setting; use temperature/top_p")
    if spec.provider == "ollama":
        from coursedeck.llm.ollama_adapter import OllamaAdapter
        from coursedeck.schema import LIST_LIMITS

        # local generation of a long document can take minutes on a laptop
        return OllamaAdapter(spec.model_id, temperature=sampling.temperature,
                             top_p=sampling.top_p, timeout_s=max(timeout_s, 600),
                             max_items=LIST_LIMITS)
    if spec.provider == "openrouter":
        from coursedeck.llm.openrouter_adapter import OpenRouterAdapter

        return OpenRouterAdapter(spec.model_id, temperature=sampling.temperature,
                                 top_p=sampling.top_p, timeout_s=timeout_s, retries=max_retries)
    raise ValueError(f"unknown provider {spec.provider}")
