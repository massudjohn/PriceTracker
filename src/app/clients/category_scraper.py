"""Amazon category/search page scraper for product discovery."""
from __future__ import annotations

import logging
import random
import re
import time
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urljoin, urlparse, parse_qs

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]


@dataclass
class ScrapedProduct:
    """A product discovered from a category/search page."""
    asin: str
    name: str
    url: str
    current_price: Optional[float] = None
    list_price: Optional[float] = None
    rating: Optional[float] = None
    review_count: Optional[int] = None
    image_url: Optional[str] = None
    is_prime: bool = False
    is_sponsored: bool = False


class AmazonCategoryScraper:
    """Scraper for Amazon category and search result pages."""

    BASE_URL = "https://www.amazon.com"

    def __init__(self, timeout: float = 20.0, max_retries: int = 3):
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
        time.sleep(random.uniform(2.0, 5.0))

    def scrape_category(self, url: str, max_pages: int = 3) -> list[ScrapedProduct]:
        """
        Scrape products from a category or search URL.

        Args:
            url: Amazon category or search URL
            max_pages: Maximum number of pages to scrape

        Returns:
            List of discovered products
        """
        all_products: list[ScrapedProduct] = []
        current_url = url

        for page in range(max_pages):
            logger.info(f"Scraping page {page + 1} of category: {url[:80]}...")

            products, next_url = self._scrape_page(current_url)
            all_products.extend(products)

            if not next_url:
                break

            current_url = next_url
            self._random_delay()

        # Deduplicate by ASIN
        seen_asins = set()
        unique_products = []
        for p in all_products:
            if p.asin not in seen_asins:
                seen_asins.add(p.asin)
                unique_products.append(p)

        logger.info(f"Found {len(unique_products)} unique products from category")
        return unique_products

    def _scrape_page(self, url: str) -> tuple[list[ScrapedProduct], Optional[str]]:
        """Scrape a single page and return products + next page URL."""
        for attempt in range(self.max_retries):
            try:
                client = self._get_client()
                client.headers["User-Agent"] = random.choice(USER_AGENTS)

                response = client.get(url)

                if response.status_code == 503:
                    logger.warning(f"Amazon blocking request, waiting... (attempt {attempt + 1})")
                    time.sleep(30 * (attempt + 1))
                    continue

                response.raise_for_status()
                return self._parse_search_results(response.text, url)

            except httpx.TimeoutException:
                logger.warning(f"Timeout scraping category (attempt {attempt + 1})")
                self._random_delay()
            except Exception as e:
                logger.exception(f"Error scraping category: {e}")
                self._random_delay()

        return [], None

    def _parse_search_results(self, html: str, base_url: str) -> tuple[list[ScrapedProduct], Optional[str]]:
        """Parse search/category results page."""
        soup = BeautifulSoup(html, "html.parser")
        products: list[ScrapedProduct] = []

        # Find product containers - Amazon uses various selectors
        product_containers = soup.select(
            "[data-asin]:not([data-asin='']) [data-component-type='s-search-result'], "
            "[data-asin]:not([data-asin=''])"
        )

        # Fallback to other selectors
        if not product_containers:
            product_containers = soup.select(".s-result-item[data-asin]")

        for container in product_containers:
            asin = container.get("data-asin", "")
            if not asin or len(asin) != 10:
                continue

            # Skip sponsored products optionally
            is_sponsored = bool(container.select_one(".s-sponsored-label-text, [data-component-type='sp-sponsored-result']"))

            product = self._parse_product_card(container, asin, is_sponsored)
            if product and product.name:
                products.append(product)

        # Find next page URL
        next_url = None
        next_link = soup.select_one(".s-pagination-next:not(.s-pagination-disabled), a.s-pagination-next")
        if next_link and next_link.get("href"):
            next_url = urljoin(base_url, next_link["href"])

        return products, next_url

    def _parse_product_card(self, container, asin: str, is_sponsored: bool) -> Optional[ScrapedProduct]:
        """Parse a single product card."""
        try:
            # Product name
            name_elem = container.select_one(
                "h2 a span, "
                ".a-size-medium.a-color-base.a-text-normal, "
                ".a-size-base-plus.a-color-base.a-text-normal, "
                "[data-cy='title-recipe'] span"
            )
            name = name_elem.get_text(strip=True) if name_elem else ""

            if not name:
                return None

            # Product URL
            link_elem = container.select_one("h2 a, a.a-link-normal[href*='/dp/']")
            url = ""
            if link_elem and link_elem.get("href"):
                href = link_elem["href"]
                if "/dp/" in href:
                    url = urljoin(self.BASE_URL, href.split("?")[0])
                else:
                    url = f"{self.BASE_URL}/dp/{asin}"
            else:
                url = f"{self.BASE_URL}/dp/{asin}"

            # Current price
            current_price = None
            price_elem = container.select_one(
                ".a-price:not(.a-text-price) .a-offscreen, "
                "span.a-price span.a-offscreen, "
                ".a-price-whole"
            )
            if price_elem:
                current_price = self._extract_price(price_elem.get_text())

            # List price (original price)
            list_price = None
            list_price_elem = container.select_one(
                ".a-price.a-text-price .a-offscreen, "
                "span.a-text-price span.a-offscreen"
            )
            if list_price_elem:
                list_price = self._extract_price(list_price_elem.get_text())

            # Rating
            rating = None
            rating_elem = container.select_one(
                ".a-icon-star-small .a-icon-alt, "
                ".a-icon-star .a-icon-alt, "
                "[data-cy='reviews-ratings-slot'] .a-icon-alt"
            )
            if rating_elem:
                rating_text = rating_elem.get_text()
                match = re.search(r'([\d.]+)\s*out of', rating_text)
                if match:
                    rating = float(match.group(1))

            # Review count
            review_count = None
            review_elem = container.select_one(
                "[data-cy='reviews-ratings-slot'] .a-size-base, "
                ".a-size-base.s-underline-text, "
                "a[href*='customerReviews'] span"
            )
            if review_elem:
                review_text = review_elem.get_text().replace(",", "").replace("(", "").replace(")", "")
                match = re.search(r'([\d,]+)', review_text)
                if match:
                    review_count = int(match.group(1).replace(",", ""))

            # Image URL
            image_url = None
            img_elem = container.select_one("img.s-image, .s-product-image-container img")
            if img_elem and img_elem.get("src"):
                image_url = img_elem["src"]

            # Prime badge
            is_prime = bool(container.select_one(".s-prime, .a-icon-prime"))

            return ScrapedProduct(
                asin=asin,
                name=name[:500],  # Limit name length
                url=url,
                current_price=current_price,
                list_price=list_price,
                rating=rating,
                review_count=review_count,
                image_url=image_url,
                is_prime=is_prime,
                is_sponsored=is_sponsored,
            )

        except Exception as e:
            logger.warning(f"Error parsing product card for {asin}: {e}")
            return None

    def _extract_price(self, text: str) -> Optional[float]:
        """Extract price from text."""
        if not text:
            return None

        # Clean and extract price
        cleaned = re.sub(r'[^\d.,]', '', text)
        if not cleaned:
            return None

        # Handle formats like 1,299.99 or 1.299,99
        if ',' in cleaned and '.' in cleaned:
            if cleaned.rfind(',') > cleaned.rfind('.'):
                cleaned = cleaned.replace('.', '').replace(',', '.')
            else:
                cleaned = cleaned.replace(',', '')
        elif ',' in cleaned:
            if len(cleaned.split(',')[-1]) == 2:
                cleaned = cleaned.replace(',', '.')
            else:
                cleaned = cleaned.replace(',', '')

        try:
            return float(cleaned)
        except ValueError:
            return None

    @staticmethod
    def extract_asin_from_url(url: str) -> Optional[str]:
        """Extract ASIN from an Amazon product URL."""
        patterns = [
            r'/dp/([A-Z0-9]{10})',
            r'/gp/product/([A-Z0-9]{10})',
            r'/product/([A-Z0-9]{10})',
            r'asin=([A-Z0-9]{10})',
        ]
        for pattern in patterns:
            match = re.search(pattern, url, re.IGNORECASE)
            if match:
                return match.group(1).upper()
        return None

    def close(self) -> None:
        if self._client:
            self._client.close()
            self._client = None

    def __enter__(self) -> "AmazonCategoryScraper":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
