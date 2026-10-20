"""Model prices for cost estimates and actual-cost logging.

USD per million tokens, from https://platform.claude.com/docs/en/about-claude/pricing (checked
2026-10-15). Override or add models with the MODEL_PRICES setting.
"""

from dataclasses import dataclass

from app.config import Settings

BATCH_DISCOUNT = 0.5


@dataclass(frozen=True)
class Price:
    input: float
    output: float
    cache_write: float  # 5-minute cache writes
    cache_read: float


PRICES: dict[str, Price] = {
    "claude-haiku-5-5": Price(input=0.10, output=0.50, cache_write=0.125, cache_read=0.01),
    "claude-sonnet-5-5": Price(input=2.00, output=10.00, cache_write=2.50, cache_read=0.10),
}

# Haiku 5.5 charges more for any request whose prompt exceeds 100K tokens.
LONG_PROMPT_PRICES: dict[str, tuple[int, Price]] = {
    "claude-haiku-5-5": (100_000, Price(input=0.50, output=2.50, cache_write=0.625, cache_read=0.05)),
}


class UnknownModelPrice(Exception):
    pass


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    @property
    def prompt_tokens(self) -> int:
        return self.input_tokens + self.cache_read_tokens + self.cache_write_tokens

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(
            self.input_tokens + other.input_tokens,
            self.output_tokens + other.output_tokens,
            self.cache_read_tokens + other.cache_read_tokens,
            self.cache_write_tokens + other.cache_write_tokens,
        )

    def as_dict(self) -> dict:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_write_tokens": self.cache_write_tokens,
        }


def price_for(model: str, prompt_tokens: int, settings: Settings | None = None) -> Price:
    if settings and model in settings.model_prices:
        return Price(**settings.model_prices[model])
    if model in LONG_PROMPT_PRICES:
        threshold, long_price = LONG_PROMPT_PRICES[model]
        if prompt_tokens > threshold:
            return long_price
    if model not in PRICES:
        raise UnknownModelPrice(
            f"No price on file for model '{model}'. Add it to app/analysis/pricing.py or the MODEL_PRICES setting."
        )
    return PRICES[model]


def request_cost(model: str, usage: Usage, *, batch: bool, settings: Settings | None = None) -> float:
    """Cost of one request (prices depend on that request's own prompt length)."""
    p = price_for(model, usage.prompt_tokens, settings)
    dollars = (
        usage.input_tokens * p.input
        + usage.output_tokens * p.output
        + usage.cache_read_tokens * p.cache_read
        + usage.cache_write_tokens * p.cache_write
    ) / 1_000_000
    return dollars * (BATCH_DISCOUNT if batch else 1.0)
