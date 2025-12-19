from __future__ import annotations

import logging
import random
import time
from typing import Dict

import httpx

logger = logging.getLogger(__name__)


class AmazonClient:
    """HTTP client for retrieving Amazon product pages with rotation and retries."""

    USER_AGENTS = [
        # A small pool of recent desktop user agents to help avoid throttling.
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    ]

    REGIONAL_DOMAINS: Dict[str, str] = {
        "US": "www.amazon.com",
        "UK": "www.amazon.co.uk",
        "DE": "www.amazon.de",
        "FR": "www.amazon.fr",
        "JP": "www.amazon.co.jp",
        "CA": "www.amazon.ca",
    }

    def __init__(
        self,
        *,
        timeout: float = 15.0,
        max_retries: int = 3,
        backoff_factor: float = 0.75,
    ) -> None:
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.client = httpx.Client(follow_redirects=True, timeout=timeout)

    def _headers(self) -> Dict[str, str]:
        return {
            "User-Agent": random.choice(self.USER_AGENTS),
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Cache-Control": "no-cache",
        }

    def fetch_product_page(self, asin: str, region: str = "US") -> str:
        domain = self.REGIONAL_DOMAINS.get(region.upper(), self.REGIONAL_DOMAINS["US"])
        url = f"https://{domain}/dp/{asin}?th=1&psc=1"

        for attempt in range(self.max_retries):
            try:
                response = self.client.get(url, headers=self._headers())
                if response.status_code >= 500:
                    raise httpx.HTTPStatusError("Server error", request=response.request, response=response)
                response.raise_for_status()
                return response.text
            except httpx.HTTPError as exc:
                if attempt >= self.max_retries - 1:
                    logger.exception("Failed to fetch Amazon page after retries", extra={"asin": asin})
                    raise

                sleep_seconds = self.backoff_factor * (2**attempt) + random.uniform(0, 0.3)
                logger.warning(
                    "Amazon fetch failed; retrying",
                    extra={"asin": asin, "attempt": attempt + 1, "sleep_seconds": sleep_seconds},
                )
                time.sleep(sleep_seconds)

        raise RuntimeError("Unreachable retry loop")

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> "AmazonClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[override]
        self.close()
