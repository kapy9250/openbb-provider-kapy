"""Shared HTTP helper for kapy-provider fetchers.

Retry policy:
- 3 attempts, exponential back-off: 1 s → 2 s → 4 s
- Non-retryable HTTP status codes: 401, 403, 404, 422, 429
- Retryable: 5xx, connection errors, timeouts
"""
from __future__ import annotations

import time
from typing import Any

import requests

DEFAULT_UA = "Mozilla/5.0 KapyProvider/1.0"
_NON_RETRYABLE = {401, 403, 404, 422, 429}


def _request(
    url: str,
    *,
    timeout: int = 20,
    headers: dict | None = None,
    params: dict | None = None,
    proxies: dict | None = None,
    retries: int = 3,
    backoff: float = 1.0,
) -> requests.Response:
    h = {"User-Agent": DEFAULT_UA}
    if headers:
        h.update(headers)

    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=h, params=params, proxies=proxies, timeout=timeout)
            resp.raise_for_status()
            return resp
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code in _NON_RETRYABLE:
                raise
            last_exc = e
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            last_exc = e

        if attempt < retries - 1:
            time.sleep(backoff * (2 ** attempt))

    assert last_exc is not None, "retries must be >= 1"
    raise last_exc


def get_json(
    url: str,
    *,
    timeout: int = 20,
    headers: dict | None = None,
    params: dict | None = None,
    proxies: dict | None = None,
    retries: int = 3,
    backoff: float = 1.0,
) -> Any:
    """GET url and return parsed JSON. Retries on transient errors."""
    return _request(
        url, timeout=timeout, headers=headers, params=params, proxies=proxies,
        retries=retries, backoff=backoff,
    ).json()


def get_text(
    url: str,
    *,
    timeout: int = 20,
    headers: dict | None = None,
    params: dict | None = None,
    retries: int = 3,
    backoff: float = 1.0,
) -> str:
    """GET url and return response text. Retries on transient errors."""
    return _request(
        url, timeout=timeout, headers=headers, params=params,
        retries=retries, backoff=backoff,
    ).text


def get_bytes(
    url: str,
    *,
    timeout: int = 60,
    headers: dict | None = None,
    params: dict | None = None,
    retries: int = 3,
    backoff: float = 2.0,
) -> bytes:
    """GET url and return response bytes. Retries on transient errors."""
    return _request(
        url, timeout=timeout, headers=headers, params=params,
        retries=retries, backoff=backoff,
    ).content
