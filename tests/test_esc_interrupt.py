"""Tests for ESC interrupt enhancement - dual-wait cancellation.

[HIGH-RISK] Tests for async cancellation patterns in LLM clients.
Validates the request_with_cancel function from llm/_cancel_support.py.
"""

import asyncio

import httpx
import pytest

from quangan.llm._cancel_support import request_with_cancel


class TestRequestWithCancel:
    """Test the dual-wait cancellation pattern via request_with_cancel."""

    @pytest.mark.asyncio
    async def test_cancel_event_stops_request(self) -> None:
        """Normal: cancel_event set should raise CancelledError."""
        cancel_event = asyncio.Event()
        cancel_event.set()  # Pre-set cancel

        async def slow_request() -> httpx.Response:
            await asyncio.sleep(10)  # Simulates slow HTTP
            return httpx.Response(200, text="ok")

        with pytest.raises(asyncio.CancelledError):
            await request_with_cancel(slow_request(), cancel_event)

    @pytest.mark.asyncio
    async def test_normal_request_completes(self) -> None:
        """Normal: without cancel, request completes normally."""
        cancel_event = asyncio.Event()

        async def fast_request() -> httpx.Response:
            await asyncio.sleep(0.01)
            return httpx.Response(200, text="response")

        response = await request_with_cancel(fast_request(), cancel_event)
        assert response.status_code == 200
        assert response.text == "response"

    @pytest.mark.asyncio
    async def test_none_cancel_event_passes_through(self) -> None:
        """Edge: None cancel_event should just await normally."""

        async def fast_request() -> httpx.Response:
            return httpx.Response(200, text="ok")

        response = await request_with_cancel(fast_request(), None)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_pending_tasks_cleaned_up(self) -> None:
        """Normal: pending tasks are properly cancelled after cancel race."""
        cancel_event = asyncio.Event()
        task_started = asyncio.Event()

        async def slow_request() -> httpx.Response:
            task_started.set()
            await asyncio.sleep(10)
            return httpx.Response(200, text="ok")

        async def trigger_cancel() -> None:
            await task_started.wait()
            cancel_event.set()

        # Run both concurrently
        cancel_trigger = asyncio.create_task(trigger_cancel())
        with pytest.raises(asyncio.CancelledError):
            await request_with_cancel(slow_request(), cancel_event)

        await cancel_trigger
        # If we reach here, cleanup was successful (no hanging tasks)

    @pytest.mark.asyncio
    async def test_idempotent_cancel(self) -> None:
        """Edge: multiple cancel_event.set() calls don't cause errors."""
        cancel_event = asyncio.Event()
        cancel_event.set()
        cancel_event.set()  # Double set should be safe

        async def slow_request() -> httpx.Response:
            await asyncio.sleep(10)
            return httpx.Response(200, text="ok")

        with pytest.raises(asyncio.CancelledError):
            await request_with_cancel(slow_request(), cancel_event)

    @pytest.mark.asyncio
    async def test_request_error_propagated(self) -> None:
        """Edge: request exception is propagated, not swallowed."""
        cancel_event = asyncio.Event()

        async def failing_request() -> httpx.Response:
            raise RuntimeError("Connection refused")

        with pytest.raises(RuntimeError, match="Connection refused"):
            await request_with_cancel(failing_request(), cancel_event)

    @pytest.mark.asyncio
    async def test_delayed_cancel_during_request(self) -> None:
        """Normal: cancel set during request should interrupt promptly."""
        cancel_event = asyncio.Event()

        async def slow_request() -> httpx.Response:
            await asyncio.sleep(10)
            return httpx.Response(200, text="ok")

        async def delayed_cancel() -> None:
            await asyncio.sleep(0.05)
            cancel_event.set()

        cancel_task = asyncio.create_task(delayed_cancel())

        with pytest.raises(asyncio.CancelledError):
            await request_with_cancel(slow_request(), cancel_event)

        await cancel_task
