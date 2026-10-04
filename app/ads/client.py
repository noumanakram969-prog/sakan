"""The only module that talks to the Meta Graph API.

Same shape as app/whatsapp.py: one place that knows about HTTP, so the rest of
the package deals in dicts and never in status codes. That is what makes a
provider or version change a one-file edit.

Two things here are not boilerplate:

* **Retries are selective.** Meta answers rate limits, transient errors and your
  own bad request with the same HTTP 400. Retrying a malformed campaign forever
  is not resilience, it is a loop. So only the documented transient codes are
  retried, with the backoff Meta asks for.

* **Writes are logged before they are sent.** An ads API spends money. When
  something unexpected appears in an account, the first question is "did we do
  that", and the log has to be able to answer it.
"""

from __future__ import annotations

import logging
import random
import time
from typing import Any

import httpx

log = logging.getLogger("mistri.ads")

GRAPH = "https://graph.facebook.com"

# Meta's documented transient errors. Everything else is our fault and retrying
# it just burns rate limit.
#   1, 2    - unknown/temporary platform errors
#   4, 17   - application and user rate limits
#   341     - temporary throttling
#   80000+  - the per-product ads rate limits
RETRYABLE = {1, 2, 4, 17, 341, 80000, 80003, 80004, 80005, 80006, 80008, 80009, 80014}

MAX_ATTEMPTS = 4


class MetaError(RuntimeError):
    """A Graph API error, with the fields worth seeing in a log line."""

    def __init__(self, payload: dict[str, Any], *, status: int) -> None:
        err = (payload or {}).get("error", {}) or {}
        self.code: int | None = err.get("code")
        self.subcode: int | None = err.get("error_subcode")
        self.type: str = err.get("type", "")
        self.message: str = err.get("message", "unknown error")
        self.trace: str = err.get("fbtrace_id", "")
        self.status = status
        self.user_message: str = err.get("error_user_msg") or ""
        super().__init__(
            f"[{status}] {self.type} {self.code}"
            f"{'/' + str(self.subcode) if self.subcode else ''}: {self.message}"
            f"{' (' + self.trace + ')' if self.trace else ''}"
        )

    @property
    def retryable(self) -> bool:
        return self.code in RETRYABLE


class GraphClient:
    """A thin, synchronous Graph client.

    Synchronous on purpose: campaign builds and reports run in background jobs
    and from the CLI, where the clarity of straight-line code is worth more than
    the concurrency. The WhatsApp path, which is on the request hot path, is the
    async one.
    """

    def __init__(
        self,
        access_token: str,
        *,
        version: str = "v21.0",
        timeout: float = 30.0,
        client: httpx.Client | None = None,
    ) -> None:
        if not access_token:
            raise ValueError("access_token is required")
        self.token = access_token
        self.version = version
        self._client = client or httpx.Client(timeout=timeout)
        self._owns_client = client is None

    # -- plumbing ----------------------------------------------------------

    def _url(self, path: str) -> str:
        return f"{GRAPH}/{self.version}/{path.lstrip('/')}"

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        params = dict(params or {})
        params["access_token"] = self.token

        if method != "GET":
            # Logged before the call, without the token, so an unexpected object
            # in the account can always be traced back to a line in this log.
            log.info("meta write %s %s %s", method, path, _loggable(data))

        last: MetaError | None = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                resp = self._client.request(
                    method, self._url(path), params=params, data=data
                )
            except httpx.TimeoutException as exc:
                # A timed-out write may well have landed. Say so in the log
                # rather than implying nothing happened.
                log.warning("meta %s %s timed out (attempt %d)", method, path, attempt)
                if attempt == MAX_ATTEMPTS:
                    raise MetaError(
                        {"error": {"message": f"timeout after {attempt} attempts: {exc}"}},
                        status=0,
                    ) from exc
                _sleep_backoff(attempt)
                continue

            if resp.status_code < 400:
                return resp.json() if resp.content else {}

            try:
                payload = resp.json()
            except ValueError:
                payload = {"error": {"message": resp.text[:500]}}

            err = MetaError(payload, status=resp.status_code)
            if not err.retryable or attempt == MAX_ATTEMPTS:
                log.error("meta %s %s failed: %s", method, path, err)
                raise err

            last = err
            log.warning("meta %s %s retryable (%s), attempt %d", method, path, err.code, attempt)
            _sleep_backoff(attempt)

        assert last is not None
        raise last

    # -- verbs -------------------------------------------------------------

    def get(self, path: str, **params: Any) -> dict[str, Any]:
        return self._request("GET", path, params=params)

    def post(self, path: str, **data: Any) -> dict[str, Any]:
        return self._request("POST", path, data=data)

    def delete(self, path: str, **params: Any) -> dict[str, Any]:
        return self._request("DELETE", path, params=params)

    def paged(self, path: str, *, limit: int = 100, max_pages: int = 20, **params: Any):
        """Yield every row across pages.

        max_pages is a guard, not a preference: a report over a wide date range
        with a bad breakdown can page forever, and an infinite loop inside a
        scheduled job is worse than a short report.
        """
        params["limit"] = limit
        page = self.get(path, **params)
        pages = 0
        while True:
            yield from page.get("data", [])
            pages += 1
            nxt = (page.get("paging") or {}).get("next")
            if not nxt or pages >= max_pages:
                if nxt:
                    log.warning("meta paging stopped at %d pages for %s", max_pages, path)
                return
            page = self._client.get(nxt).json()

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "GraphClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def _sleep_backoff(attempt: int) -> None:
    # Jittered, so a fleet of workers hitting the same rate limit does not
    # retry in lockstep and trip it again.
    time.sleep(min(2 ** attempt, 30) * (0.5 + random.random() / 2))


def _loggable(data: dict[str, Any] | None) -> dict[str, Any]:
    """Never let a token or customer data reach the log."""
    if not data:
        return {}
    out = {}
    for k, v in data.items():
        if "token" in k.lower() or k in {"user_data", "email", "phone"}:
            out[k] = "<redacted>"
        else:
            out[k] = v if len(str(v)) < 200 else str(v)[:200] + "..."
    return out
