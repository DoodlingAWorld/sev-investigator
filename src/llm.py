from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Generic, Type, TypeVar

import openai
from openai.types.chat import (
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

MODEL: str = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")


@dataclass
class LLMResponse(Generic[T]):
    result: T
    prompt_tokens: int
    completion_tokens: int
    latency_ms: float


def system_msg(content: str) -> ChatCompletionSystemMessageParam:
    return {"role": "system", "content": content}


def user_msg(content: str) -> ChatCompletionUserMessageParam:
    return {"role": "user", "content": content}


_client: openai.OpenAI | None = None


def _get_client() -> openai.OpenAI:
    global _client
    if _client is None:
        _client = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    return _client


def parse(
    messages: list[ChatCompletionMessageParam],
    response_format: Type[T],
    *,
    model: str = MODEL,
) -> LLMResponse[T]:
    """Single structured LLM call. Returns the parsed model plus usage metadata."""
    client = _get_client()
    t0 = time.monotonic()
    response = client.beta.chat.completions.parse(
        model=model,
        messages=messages,
        response_format=response_format,
    )
    latency_ms = (time.monotonic() - t0) * 1000
    parsed = response.choices[0].message.parsed
    if parsed is None:
        raise ValueError("OpenAI returned no parsed content")
    usage = response.usage
    return LLMResponse(
        result=parsed,
        prompt_tokens=usage.prompt_tokens if usage else 0,
        completion_tokens=usage.completion_tokens if usage else 0,
        latency_ms=latency_ms,
    )
