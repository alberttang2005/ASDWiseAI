"""OpenAI API client wrapper with streaming support and proactive rate limiting."""

import os
import re
import time
import random
import logging
import threading
from typing import Generator, List, Dict, Any, Optional
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class OpenAIClient:
    """Wrapper for OpenAI API with streaming support and header-driven rate limiting."""

    # Shared rate limit state across all instances (thread-safe)
    _lock = threading.Lock()
    _remaining_requests: Optional[int] = None
    _remaining_tokens: Optional[int] = None
    _reset_requests: Optional[float] = None  # seconds until request limit resets
    _reset_tokens: Optional[float] = None    # seconds until token limit resets
    _request_threshold = 5
    _token_threshold = 2000

    # Statistics
    _total_calls = 0
    _rate_limit_waits = 0
    _total_wait_time = 0.0

    def __init__(self, model: str = "gpt-5-nano", timeout: float = 300.0,
                 max_retries: int = 3):
        """Initialize the OpenAI client.

        Args:
            model: The model to use for completions.
            timeout: Request timeout in seconds.
            max_retries: Maximum number of retries on failure.
        """
        self.client = OpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            timeout=timeout,
            max_retries=max_retries,
        )
        self.model = model
        # Models that only support temperature=1 and use max_completion_tokens
        self._new_api_models = {"gpt-5-nano"}

    @staticmethod
    def _parse_reset_time(reset_str: str) -> float:
        """Parse rate limit reset header values like '1s', '6m0s', '200ms' into seconds."""
        if not reset_str:
            return 0.0
        total = 0.0
        for value, unit in re.findall(r'(\d+(?:\.\d+)?)(ms|s|m|h)', reset_str):
            value = float(value)
            if unit == 'ms':
                total += value / 1000.0
            elif unit == 's':
                total += value
            elif unit == 'm':
                total += value * 60.0
            elif unit == 'h':
                total += value * 3600.0
        return total

    @classmethod
    def _update_rate_limits(cls, headers) -> None:
        """Update shared rate limit state from response headers."""
        with cls._lock:
            remaining_req = headers.get('x-ratelimit-remaining-requests')
            if remaining_req is not None:
                cls._remaining_requests = int(remaining_req)
            remaining_tok = headers.get('x-ratelimit-remaining-tokens')
            if remaining_tok is not None:
                cls._remaining_tokens = int(remaining_tok)
            reset_req = headers.get('x-ratelimit-reset-requests')
            if reset_req is not None:
                cls._reset_requests = cls._parse_reset_time(reset_req)
            reset_tok = headers.get('x-ratelimit-reset-tokens')
            if reset_tok is not None:
                cls._reset_tokens = cls._parse_reset_time(reset_tok)
            cls._total_calls += 1

    @classmethod
    def _wait_if_needed(cls) -> None:
        """Proactively wait if remaining capacity is below thresholds."""
        with cls._lock:
            wait_time = 0.0
            reason = None

            if (cls._remaining_requests is not None
                    and cls._remaining_requests < cls._request_threshold
                    and cls._reset_requests is not None):
                wait_time = max(wait_time, cls._reset_requests)
                reason = f"remaining_requests={cls._remaining_requests}"

            if (cls._remaining_tokens is not None
                    and cls._remaining_tokens < cls._token_threshold
                    and cls._reset_tokens is not None):
                wait_time = max(wait_time, cls._reset_tokens)
                reason = f"remaining_tokens={cls._remaining_tokens}"

            if wait_time > 0:
                jitter = random.uniform(0, 1.0)
                wait_time += jitter
                cls._rate_limit_waits += 1
                cls._total_wait_time += wait_time
                logger.info(f"Rate limit throttle: waiting {wait_time:.1f}s ({reason})")

        if wait_time > 0:
            time.sleep(wait_time)

    @classmethod
    def get_rate_limit_stats(cls) -> Dict[str, Any]:
        """Return current rate limit statistics."""
        with cls._lock:
            return {
                "total_calls": cls._total_calls,
                "rate_limit_waits": cls._rate_limit_waits,
                "total_wait_time": round(cls._total_wait_time, 2),
                "remaining_requests": cls._remaining_requests,
                "remaining_tokens": cls._remaining_tokens,
            }

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 1.0,
        max_tokens: Optional[int] = None
    ) -> str:
        """Generate a chat completion.

        Args:
            messages: List of message dicts with 'role' and 'content'.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens to generate.

        Returns:
            The assistant's response text.
        """
        kwargs = dict(
            model=self.model,
            messages=messages,
        )
        if self.model not in self._new_api_models:
            kwargs["temperature"] = temperature
        if max_tokens is not None:
            token_key = "max_completion_tokens" if self.model in self._new_api_models else "max_tokens"
            kwargs[token_key] = max_tokens

        self._wait_if_needed()
        raw_response = self.client.chat.completions.with_raw_response.create(**kwargs)
        self._update_rate_limits(raw_response.headers)
        response = raw_response.parse()
        return response.choices[0].message.content or ""

    def chat_stream(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 1.0,
        max_tokens: Optional[int] = None
    ) -> Generator[str, None, None]:
        """Generate a streaming chat completion.

        Args:
            messages: List of message dicts with 'role' and 'content'.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens to generate.

        Yields:
            Chunks of the assistant's response text.
        """
        kwargs = dict(
            model=self.model,
            messages=messages,
            stream=True,
        )
        if self.model not in self._new_api_models:
            kwargs["temperature"] = temperature
        if max_tokens is not None:
            token_key = "max_completion_tokens" if self.model in self._new_api_models else "max_tokens"
            kwargs[token_key] = max_tokens

        self._wait_if_needed()
        stream = self.client.chat.completions.create(**kwargs)

        for chunk in stream:
            if chunk.choices[0].delta.content is not None:
                yield chunk.choices[0].delta.content
