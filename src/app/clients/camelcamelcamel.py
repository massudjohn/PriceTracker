"""CamelCamelCamel scraper for Amazon price history."""
from __future__ import annotations

import logging
import random
import re
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
]


@dataclass
class PriceStats:
    """Price statistics from CamelCamelCamel."""
    asin: str
    current_price: Optional[float] = None
    all_time_low: Optional[float] = None
    all_time_low_date: Optional[datetime] = None
    all_time_high: Optional[float] = None
    average_price: Optional[float] = None


class CamelCamelCamelClient:
    """Client for scraping CamelCamelCamel price history."""

    BASE_URL = "https://camelcamelcamel.com"

    def __init__(self, timeout: float = 15.0, max_retries: int = 3):
        self.timeout = timeout
        self.max_retries = max_retries
        self._client: Optional[httpx.Client] = None

    def _get_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                timeout=self.timeout,
                follow_redirects=True,
                headers={
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.5",
                    "Accept-Encoding": "gzip, deflate, br",
                    "DNT": "1",
                    "Connection": "keep-alive",
                    "Upgrade-Insecure-Requests": "1",
                },
            )
        return self._client

    def _random_delay(self) -> None:
        """Random delay to avoid rate limiting."""
        time.sleep(random.uniform(1.0, 3.0))

    def get_price_history(self, asin: str) -> Optional[PriceStats]:
        """
        Fetch price history for an ASIN from CamelCamelCamel.

        Returns PriceStats with all-time low, high, and average prices.
        """
        url = f"{self.BASE_URL}/product/{asin}"

        for attempt in range(self.max_retries):
            try:
                client = self._get_client()
                client.headers["User-Agent"] = random.choice(USER_AGENTS)

                response = client.get(url)

                if response.status_code == 404:
                    logger.info(f"Product not found on CamelCamelCamel: {asin}")
                    return None

                if response.status_code == 429:
                    logger.warning(f"Rate limited by CamelCamelCamel, waiting... (attempt {attempt + 1})")
                    time.sleep(30 * (attempt + 1))
                    continue

                response.raise_for_status()
                return self._parse_price_page(asin, response.text)

            except httpx.TimeoutException:
                logger.warning(f"Timeout fetching CamelCamelCamel for {asin} (attempt {attempt + 1})")
                self._random_delay()
            except httpx.HTTPStatusError as e:
                logger.warning(f"HTTP error {e.response.status_code} for {asin}")
                if e.response.status_code >= 500:
                    self._random_delay()
                    continue
                return None
            except Exception as e:
                logger.exception(f"Error fetching CamelCamelCamel for {asin}: {e}")
                self._random_delay()

        return None

    def _parse_price_page(self, asin: str, html: str) -> PriceStats:
        """Parse the CamelCamelCamel product page for price stats."""
        soup = BeautifulSoup(html, "html.parser")
        stats = PriceStats(asin=asin)

        # Look for price statistics in the page
        # CamelCamelCamel shows prices in a table format
        try:
            # Find Amazon price section
            price_rows = soup.select("table.product_pane tr")

            for row in price_rows:
                cells = row.find_all("td")
                if len(cells) >= 2:
                    label = cells[0].get_text(strip=True).lower()
                    value_text = cells[1].get_text(strip=True)

                    price = self._extract_price(value_text)

                    if "current" in label and price:
                        stats.current_price = price
                    elif "lowest" in label and price:
                        stats.all_time_low = price
                    elif "highest" in label and price:
                        stats.all_time_high = price
                    elif "average" in label and price:
                        stats.average_price = price

            # Alternative: look for specific elements
            if stats.all_time_low is None:
                low_elem = soup.select_one(".lowest_price, [class*='lowest']")
                if low_elem:
                    stats.all_time_low = self._extract_price(low_elem.get_text())

            # Look for chart data or summary stats
            stat_elements = soup.select(".stat, .price_stat, .summary_stat")
            for elem in stat_elements:
                text = elem.get_text(strip=True).lower()
                price = self._extract_price(text)
                if price:
                    if "low" in text and stats.all_time_low is None:
                        stats.all_time_low = price
                    elif "high" in text and stats.all_time_high is None:
                        stats.all_time_high = price
                    elif "avg" in text or "average" in text:
                        stats.average_price = price

        except Exception as e:
            logger.warning(f"Error parsing CamelCamelCamel page for {asin}: {e}")

        return stats

    def _extract_price(self, text: str) -> Optional[float]:
        """Extract a price value from text."""
        if not text:
            return None

        # Find price patterns like $19.99 or 19.99
        match = re.search(r'\$?([\d,]+\.?\d*)', text.replace(',', ''))
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                pass
        return None

    def close(self) -> None:
        if self._client:
            self._client.close()
            self._client = None

    def __enter__(self) -> "CamelCamelCamelClient":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
