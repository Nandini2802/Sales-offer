
from collections.abc import Callable
from typing import Any
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import settings


def with_retry(
    attempts: int | None = None,
    min_wait: float | None = None,
    max_wait: float | None = None,
    exceptions: tuple[type[Exception], ...] = (Exception,),
) -> Callable[..., Any]:
    """
    Create a reusable retry decorator with exponential backoff.

    Uses retry settings from the application configuration by default.
    Individual clients can override these values when required.

    Args:
        attempts: Maximum number of attempts, including the first call.
        min_wait: Minimum delay between retries in seconds.
        max_wait: Maximum delay between retries in seconds.
        exceptions: Exception types that should trigger a retry.

    Returns:
        A Tenacity retry decorator.
    """

    return retry(
        stop=stop_after_attempt(
            attempts if attempts is not None else settings.retry_attempts
        ),
        wait=wait_exponential(
            multiplier=1,
            min=min_wait if min_wait is not None else settings.retry_min_wait_seconds,
            max=max_wait if max_wait is not None else settings.retry_max_wait_seconds,
        ),
        retry=retry_if_exception_type(exceptions),
        reraise=True,
    )
