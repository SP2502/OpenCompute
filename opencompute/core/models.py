"""Model access.

OpenCompute is model-agnostic: any provider that speaks the OpenAI chat
completions API works (OpenAI, OpenRouter, Together, DeepSeek, Ollama, ...).
We wrap that in one tiny client so the rest of the code never touches a
provider directly.

Cost is recorded with an honesty flag because token counts are sometimes
missing or the provider price is unknown:

    "exact"      -- real token counts and a known per-token price
    "estimated"  -- token counts present but price is an assumption
    "unknown"    -- we have no usable numbers at all
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

# Approximate USD per million tokens, used only to turn token counts into a
# rough dollar figure. Anything not listed here is reported as "unknown".
_PRICE_PER_MILLION = {
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4.1": (2.00, 8.00),
    "claude-3-5-haiku": (0.80, 4.00),
    "claude-3-5-sonnet": (3.00, 15.00),
    "deepseek-chat": (0.27, 1.10),
    "llama-3.1-8b": (0.05, 0.05),  # via OpenRouter, varies
}


@dataclass
class ModelResult:
    text: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost: float = 0.0
    # "exact" | "estimated" | "unknown"
    cost_status: str = "unknown"
    provider: str = ""
    latency: float = 0.0  # seconds for the API call

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass
class ModelClient:
    """Base client. Subclasses implement ``complete``."""

    default_model: str = "gpt-4o-mini"

    def complete(self, messages: list[dict], model: Optional[str] = None) -> ModelResult:
        raise NotImplementedError

    def _price(self, model: str, prompt: int, completion: int) -> tuple[float, str]:
        """Turn token counts into a cost estimate, if we know the price."""
        key = model.split("/")[-1].lower()
        if key in _PRICE_PER_MILLION:
            pin, pout = _PRICE_PER_MILLION[key]
            cost = (prompt * pin + completion * pout) / 1_000_000
            return cost, "estimated"
        return 0.0, "unknown"


class OpenAICompatClient(ModelClient):
    """Backed by the ``openai`` SDK pointed at any compatible endpoint."""

    def __init__(
        self,
        default_model: str = "gpt-4o-mini",
        base_url: str | None = None,
        api_key: str | None = None,
    ):
        super().__init__(default_model=default_model)
        from openai import OpenAI

        self._client = OpenAI(base_url=base_url, api_key=api_key)
        # Label the provider from the endpoint hostname, else default to openai.
        self.provider = "openai"
        if base_url:
            host = base_url.split("://")[-1].split("/")[0]
            if host:
                self.provider = host

    def complete(self, messages: list[dict], model: Optional[str] = None) -> ModelResult:
        import time

        model = model or self.default_model
        start = time.perf_counter()
        resp = self._client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.2,
        )
        latency = time.perf_counter() - start
        prompt = resp.usage.prompt_tokens if resp.usage else 0
        completion = resp.usage.completion_tokens if resp.usage else 0
        cost, status = self._price(model, prompt, completion)
        return ModelResult(
            text=resp.choices[0].message.content or "",
            prompt_tokens=prompt,
            completion_tokens=completion,
            cost=cost,
            cost_status=status,
            provider=self.provider,
            latency=latency,
        )
