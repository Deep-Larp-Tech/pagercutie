from http import HTTPStatus

from pagercutie.core.errors import NotReady, Overloaded, RateLimited, error_body, retry_after


def test_overload_answers_503_and_a_rate_limit_429_both_with_retry_after() -> None:
    overloaded, limited = Overloaded("pool exhausted", 1), RateLimited("payments-webhook", 3)

    assert (error_body(overloaded)[0], retry_after(overloaded)) == (HTTPStatus.SERVICE_UNAVAILABLE, 1)
    assert (error_body(limited)[0], retry_after(limited)) == (HTTPStatus.TOO_MANY_REQUESTS, 3)


def test_other_errors_have_no_retry_after() -> None:
    assert retry_after(NotReady("Rules are not loaded")) is None
