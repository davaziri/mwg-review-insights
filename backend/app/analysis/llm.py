"""Thin wrapper over the Anthropic SDK: one structured-output request shape, used directly, in
batches, and for token counting. Tests swap in a fake that implements LLMClient.
"""

import json
import logging
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Protocol

import anthropic

from app.analysis.pricing import Usage
from app.config import Settings

log = logging.getLogger(__name__)

# Server-side refusal fallback ("default" routing). Claude API only; not accepted on the Batches API,
# and not offered for Haiku 5.5.
FALLBACK_BETA = "server-side-fallback-2026-07-01"
FALLBACK_MODELS = {"claude-sonnet-5-5"}


class LLMNotConfigured(Exception):
    pass


@dataclass
class LLMRequest:
    model: str
    system: str
    user: str
    schema: dict
    max_tokens: int
    effort: str | None = None

    def params(self) -> dict:
        output_config: dict = {"format": {"type": "json_schema", "schema": self.schema}}
        if self.effort:
            output_config["effort"] = self.effort
        return {
            "model": self.model,
            "max_tokens": self.max_tokens,
            # The system prompt (instructions + codebook) is identical across a run: cache it.
            "system": [{"type": "text", "text": self.system, "cache_control": {"type": "ephemeral"}}],
            "messages": [{"role": "user", "content": self.user}],
            "output_config": output_config,
        }


@dataclass
class LLMResult:
    data: dict | None
    usage: Usage
    model: str
    stop_reason: str | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.data is not None and self.error is None

    @property
    def refused(self) -> bool:
        return self.stop_reason == "refusal"


class LLMClient(Protocol):
    def complete(self, request: LLMRequest) -> LLMResult: ...
    def count_input_tokens(self, request: LLMRequest) -> int: ...
    def submit_batch(self, items: list[tuple[str, LLMRequest]]) -> str: ...
    def batch_ended(self, batch_id: str) -> bool: ...
    def batch_results(self, batch_id: str) -> Iterator[tuple[str, LLMResult]]: ...
    def cancel_batch(self, batch_id: str) -> None: ...


def _usage(u) -> Usage:
    return Usage(
        input_tokens=getattr(u, "input_tokens", 0) or 0,
        output_tokens=getattr(u, "output_tokens", 0) or 0,
        cache_read_tokens=getattr(u, "cache_read_input_tokens", 0) or 0,
        cache_write_tokens=getattr(u, "cache_creation_input_tokens", 0) or 0,
    )


def parse_message(message) -> LLMResult:
    usage = _usage(message.usage)
    model = getattr(message, "model", "") or ""
    stop = message.stop_reason
    if stop == "refusal":
        details = getattr(message, "stop_details", None)
        category = getattr(details, "category", None) if details else None
        return LLMResult(None, usage, model, stop, error=f"declined by the model (category: {category})")
    if stop == "max_tokens":
        return LLMResult(None, usage, model, stop, error="output was cut off at max_tokens")
    text = next((b.text for b in message.content if getattr(b, "type", None) == "text"), None)
    if text is None:
        return LLMResult(None, usage, model, stop, error="no text block in response")
    try:
        return LLMResult(json.loads(text), usage, model, stop)
    except json.JSONDecodeError as exc:
        return LLMResult(None, usage, model, stop, error=f"response was not valid JSON ({exc})")


class AnthropicLLM:
    def __init__(self, settings: Settings):
        if not settings.anthropic_api_key:
            raise LLMNotConfigured("ANTHROPIC_API_KEY is not set, so analysis can't run.")
        self.client = anthropic.Anthropic(
            api_key=settings.anthropic_api_key,
            base_url=settings.anthropic_api_base,
            max_retries=4,
        )

    def complete(self, request: LLMRequest) -> LLMResult:
        params = request.params()
        # Streaming avoids HTTP timeouts on long analysis-model responses.
        if request.model in FALLBACK_MODELS:
            with self.client.beta.messages.stream(**params, betas=[FALLBACK_BETA], fallbacks="default") as stream:
                message = stream.get_final_message()
        else:
            with self.client.messages.stream(**params) as stream:
                message = stream.get_final_message()
        return parse_message(message)

    def count_input_tokens(self, request: LLMRequest) -> int:
        params = request.params()
        params.pop("max_tokens")
        return self.client.messages.count_tokens(**params).input_tokens

    def submit_batch(self, items: list[tuple[str, LLMRequest]]) -> str:
        batch = self.client.messages.batches.create(
            requests=[{"custom_id": custom_id, "params": req.params()} for custom_id, req in items]
        )
        return batch.id

    def batch_ended(self, batch_id: str) -> bool:
        return self.client.messages.batches.retrieve(batch_id).processing_status == "ended"

    def batch_results(self, batch_id: str) -> Iterator[tuple[str, LLMResult]]:
        for entry in self.client.messages.batches.results(batch_id):
            result = entry.result
            if result.type == "succeeded":
                yield entry.custom_id, parse_message(result.message)
            else:
                detail = getattr(getattr(result, "error", None), "type", "") or ""
                yield entry.custom_id, LLMResult(None, Usage(), "", None, error=f"batch request {result.type} {detail}".strip())

    def cancel_batch(self, batch_id: str) -> None:
        self.client.messages.batches.cancel(batch_id)
