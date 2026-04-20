"""Tests for LLM client retry, timeout configuration, and model prefix matching.

[HIGH-RISK] Tests for retry strategy and cancel_event interaction.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from quangan.config.llm_config import (
    MODEL_CONTEXT_LIMITS,
    LLMConfig,
    get_model_context_limit,
)
from quangan.llm._cancel_support import (
    _cancellable_sleep,
    request_with_retry,
)

# ─────────────────────────────────────────────────────────────────────────────
# Model prefix matching
# ─────────────────────────────────────────────────────────────────────────────


class TestModelPrefixMatching:
    """Test longest-prefix matching for model context limits."""

    def test_exact_match(self) -> None:
        """Known exact model name should return its configured limit."""
        result = get_model_context_limit("qwen-plus")
        assert result == MODEL_CONTEXT_LIMITS["qwen-plus"]

    def test_prefix_match_prefers_longest(self) -> None:
        """Longer prefix 'qwen-max-longcontext' should win over 'qwen-max'."""
        # 'qwen-max-longcontext' is an exact key; 'qwen-max-longcontext-xxx'
        # should match 'qwen-max-longcontext' (len=20) over 'qwen-max' (len=8)
        result = get_model_context_limit("qwen-max-longcontext-v2")
        assert result == MODEL_CONTEXT_LIMITS["qwen-max-longcontext"]

    def test_shorter_prefix_fallback(self) -> None:
        """When only shorter prefix matches, use it."""
        result = get_model_context_limit("qwen-max-special")
        assert result == MODEL_CONTEXT_LIMITS["qwen-max"]

    def test_unknown_model_returns_default(self) -> None:
        """Unknown model returns default 128k."""
        result = get_model_context_limit("completely-unknown-model-xyz")
        assert result == 128_000

    def test_empty_model_returns_default(self) -> None:
        """Empty string returns default 128k."""
        result = get_model_context_limit("")
        assert result == 128_000


# ─────────────────────────────────────────────────────────────────────────────
# LLMConfig retry fields
# ─────────────────────────────────────────────────────────────────────────────


class TestLLMConfigRetryFields:
    """Test LLMConfig retry configuration fields have correct defaults."""

    def _make_config(self, **overrides) -> LLMConfig:
        defaults = {
            "provider": "test",
            "api_key": "sk-test",
            "base_url": "https://example.com/v1",
            "model": "test-model",
        }
        defaults.update(overrides)
        return LLMConfig(**defaults)

    def test_default_timeout(self) -> None:
        config = self._make_config()
        assert config.timeout_seconds == 120

    def test_default_max_retries(self) -> None:
        config = self._make_config()
        assert config.max_retries == 2

    def test_default_retry_status_codes(self) -> None:
        config = self._make_config()
        assert config.retry_status_codes == (429, 500, 502, 503)

    def test_custom_timeout(self) -> None:
        config = self._make_config(timeout_seconds=60)
        assert config.timeout_seconds == 60

    def test_custom_max_retries(self) -> None:
        config = self._make_config(max_retries=5)
        assert config.max_retries == 5

    def test_custom_retry_status_codes(self) -> None:
        config = self._make_config(retry_status_codes=(429,))
        assert config.retry_status_codes == (429,)


# ─────────────────────────────────────────────────────────────────────────────
# Cancellable sleep
# ─────────────────────────────────────────────────────────────────────────────


class TestCancellableSleep:
    """Test _cancellable_sleep respects cancel_event."""

    @pytest.mark.asyncio
    async def test_sleep_completes_normally(self) -> None:
        """Sleep should complete normally when no cancel."""
        await _cancellable_sleep(0.01, None)  # should not raise

    @pytest.mark.asyncio
    async def test_sleep_cancelled_by_event(self) -> None:
        """Sleep should raise CancelledError when event is set."""
        event = asyncio.Event()
        event.set()  # pre-set the event
        with pytest.raises(asyncio.CancelledError):
            await _cancellable_sleep(10.0, event)

    @pytest.mark.asyncio
    async def test_sleep_interrupted_mid_sleep(self) -> None:
        """Sleep should be interrupted when event fires during sleep."""
        event = asyncio.Event()

        async def set_after_delay() -> None:
            await asyncio.sleep(0.05)
            event.set()

        task = asyncio.create_task(set_after_delay())
        with pytest.raises(asyncio.CancelledError):
            await _cancellable_sleep(10.0, event)
        await task


# ─────────────────────────────────────────────────────────────────────────────
# request_with_retry
# ─────────────────────────────────────────────────────────────────────────────


def _make_response(status_code: int = 200) -> httpx.Response:
    """Create a mock httpx.Response."""
    return httpx.Response(status_code=status_code, request=httpx.Request("POST", "https://test"))


class TestRequestWithRetry:
    """Test request_with_retry logic."""

    @pytest.mark.asyncio
    async def test_success_no_retry(self) -> None:
        """Successful request should return immediately, no retry."""
        factory = AsyncMock(return_value=_make_response(200))
        result = await request_with_retry(factory, None, max_retries=2)
        assert result.status_code == 200
        factory.assert_called_once()

    @pytest.mark.asyncio
    async def test_retry_on_status_code(self) -> None:
        """Should retry on configured status codes then succeed."""
        responses = [_make_response(503), _make_response(200)]
        call_count = 0

        async def factory():
            nonlocal call_count
            resp = responses[call_count]
            call_count += 1
            return resp

        with patch("quangan.llm._cancel_support._cancellable_sleep", new_callable=AsyncMock):
            result = await request_with_retry(factory, None, max_retries=2)
        assert result.status_code == 200
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_retry_exhausted_returns_last_response(self) -> None:
        """When all retries exhausted on retryable status, return last response."""
        factory = AsyncMock(return_value=_make_response(503))

        with patch("quangan.llm._cancel_support._cancellable_sleep", new_callable=AsyncMock):
            result = await request_with_retry(factory, None, max_retries=1)
        # After 2 attempts (initial + 1 retry), should return the 503 response
        assert result.status_code == 503
        assert factory.call_count == 2

    @pytest.mark.asyncio
    async def test_cancel_before_first_attempt(self) -> None:
        """Should raise CancelledError if cancel_event already set."""
        event = asyncio.Event()
        event.set()
        factory = AsyncMock(return_value=_make_response(200))

        with pytest.raises(asyncio.CancelledError):
            await request_with_retry(factory, event, max_retries=2)
        factory.assert_not_called()

    @pytest.mark.asyncio
    async def test_non_retryable_status_returns_immediately(self) -> None:
        """Non-retryable status code should return without retry."""
        factory = AsyncMock(return_value=_make_response(400))
        result = await request_with_retry(
            factory, None, max_retries=2, retry_status_codes=(429, 500)
        )
        assert result.status_code == 400
        factory.assert_called_once()

    @pytest.mark.asyncio
    async def test_http_error_retried(self) -> None:
        """httpx.HTTPError should trigger retry."""
        call_count = 0

        async def factory():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise httpx.ConnectError("connection failed")
            return _make_response(200)

        with patch("quangan.llm._cancel_support._cancellable_sleep", new_callable=AsyncMock):
            result = await request_with_retry(factory, None, max_retries=2)
        assert result.status_code == 200
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_http_error_exhausted_raises(self) -> None:
        """httpx.HTTPError after all retries should re-raise."""

        async def factory():
            raise httpx.ConnectError("connection failed")

        with patch("quangan.llm._cancel_support._cancellable_sleep", new_callable=AsyncMock):
            with pytest.raises(httpx.ConnectError):
                await request_with_retry(factory, None, max_retries=1)

    @pytest.mark.asyncio
    async def test_zero_retries(self) -> None:
        """max_retries=0 means only one attempt."""
        factory = AsyncMock(return_value=_make_response(503))
        result = await request_with_retry(factory, None, max_retries=0)
        assert result.status_code == 503
        factory.assert_called_once()
