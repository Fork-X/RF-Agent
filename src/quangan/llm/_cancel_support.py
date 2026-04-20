"""Shared cancellation and retry support for LLM clients.

[HIGH-RISK] This module provides:
- Dual-wait cancellation pattern for immediate ESC interrupt response
- Retry with exponential backoff that respects cancel_event between attempts

The core idea: use asyncio.wait() to race between the HTTP request and a cancel
signal (asyncio.Event), so that when the user presses ESC, the agent can respond
immediately without waiting for the HTTP response to complete.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

import httpx

from quangan.utils.errors import LLMError

T = TypeVar("T")


async def request_with_cancel(
    post_coro: Awaitable[httpx.Response],
    cancel_event: asyncio.Event | None,
) -> httpx.Response:
    """Execute HTTP request with cancellation support.

    [HIGH-RISK] Uses asyncio.wait to race between the HTTP request and a cancel
    signal, enabling immediate ESC interrupt response during network blocking.

    Args:
        post_coro: The HTTP POST coroutine to execute.
        cancel_event: Optional cancellation event from Agent.abort().

    Returns:
        HTTP response from the successful request.

    Raises:
        asyncio.CancelledError: If cancel_event is set before response completes.
    """
    request_task = asyncio.ensure_future(post_coro)

    if cancel_event is None:
        return await request_task

    cancel_task = asyncio.create_task(cancel_event.wait())
    try:
        done, pending = await asyncio.wait(
            [request_task, cancel_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
    except BaseException:
        request_task.cancel()
        cancel_task.cancel()
        raise

    # Clean up pending tasks
    for task in pending:
        task.cancel()
        # Suppress CancelledError from cleanup
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass

    if request_task in done:
        return request_task.result()

    # Cancel event was triggered
    raise asyncio.CancelledError("Request cancelled by user (ESC)")


async def _cancellable_sleep(
    seconds: float, cancel_event: asyncio.Event | None
) -> None:
    """Sleep that can be interrupted by cancel_event.

    Args:
        seconds: Duration to sleep.
        cancel_event: Optional cancellation event.

    Raises:
        asyncio.CancelledError: If cancel_event is set during sleep.
    """
    if cancel_event is None:
        await asyncio.sleep(seconds)
        return

    cancel_task = asyncio.create_task(cancel_event.wait())
    sleep_task = asyncio.create_task(asyncio.sleep(seconds))
    try:
        done, pending = await asyncio.wait(
            [sleep_task, cancel_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
    except BaseException:
        sleep_task.cancel()
        cancel_task.cancel()
        raise

    for task in pending:
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass

    if cancel_task in done:
        raise asyncio.CancelledError("Request cancelled by user during retry backoff")


async def request_with_retry(
    post_coro_factory: Callable[[], Awaitable[httpx.Response]],
    cancel_event: asyncio.Event | None,
    *,
    max_retries: int = 2,
    retry_status_codes: tuple[int, ...] = (429, 500, 502, 503),
) -> httpx.Response:
    """Execute HTTP request with retry and cancellation support.

    [HIGH-RISK] Retries on configured status codes with exponential backoff.
    Respects cancel_event between retries and during backoff sleep.

    Args:
        post_coro_factory: Factory that creates a fresh POST coroutine for each attempt.
        cancel_event: Optional cancellation event.
        max_retries: Maximum number of retry attempts.
        retry_status_codes: HTTP status codes that trigger a retry.

    Returns:
        Successful HTTP response.

    Raises:
        LLMError: After all retries exhausted on retryable status codes.
        asyncio.CancelledError: If cancelled during retry.
    """
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        # Check cancel before each attempt
        if cancel_event and cancel_event.is_set():
            raise asyncio.CancelledError("Request cancelled by user")

        try:
            response = await request_with_cancel(
                post_coro_factory(),
                cancel_event,
            )
            if response.status_code in retry_status_codes:
                if attempt < max_retries:
                    wait_time = float(2 ** attempt)  # Exponential backoff: 1s, 2s
                    await _cancellable_sleep(wait_time, cancel_event)
                    continue
            return response
        except httpx.HTTPError as exc:
            last_exc = exc
            if attempt < max_retries:
                await _cancellable_sleep(float(2 ** attempt), cancel_event)
                continue
            raise

    # Should not reach here, but just in case
    raise LLMError(
        f"Request failed after {max_retries + 1} attempts: {last_exc}"
    )
