"""Unit tests for the shared ARQ retry policy (no Redis, no database)."""

from __future__ import annotations

import pytest
from arq.worker import Retry

from app.core.errors import AppError, NotFoundError, ValidationAppError
from app.worker.retry import MAX_TRIES, backoff_seconds, is_retryable, retry_or_fail


def test_backoff_is_exponential_and_capped() -> None:
    assert [backoff_seconds(n) for n in (1, 2, 3, 4)] == [5, 10, 20, 40]
    assert backoff_seconds(10) == 60


@pytest.mark.parametrize("job_try", range(1, MAX_TRIES))
def test_transient_error_on_non_final_attempt_raises_arq_retry(job_try: int) -> None:
    original = OSError("redis blip")
    with pytest.raises(Retry) as caught:
        retry_or_fail({"job_try": job_try}, original, task="t")
    # ARQ reads defer_score (ms) to re-queue the job later.
    assert caught.value.defer_score == backoff_seconds(job_try) * 1000
    assert caught.value.__cause__ is original


def test_final_attempt_returns_so_the_caller_records_failure() -> None:
    assert retry_or_fail({"job_try": MAX_TRIES}, OSError("still down"), task="t") is None


def test_missing_job_try_counts_as_first_attempt() -> None:
    with pytest.raises(Retry):
        retry_or_fail({}, OSError("x"), task="t")


@pytest.mark.parametrize(
    "exc", [ValidationAppError(code="resume.unreadable_pdf"), NotFoundError("gone")]
)
def test_permanent_errors_fail_immediately_without_retry(exc: Exception) -> None:
    assert not is_retryable(exc)
    assert retry_or_fail({"job_try": 1}, exc, task="t") is None


def test_llm_upstream_errors_stay_retryable() -> None:
    # The Anthropic adapter wraps rate limits/overloads as AppError.
    exc = AppError(code="llm.upstream_error")
    assert is_retryable(exc)
    with pytest.raises(Retry):
        retry_or_fail({"job_try": 1}, exc, task="t")
