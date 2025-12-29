"""Deal detection service - finds products with extreme discounts."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from uuid import UUID

from ..clients.camelcamelcamel import CamelCamelCamelClient, PriceStats
from ..clients.category_scraper import AmazonCategoryScraper, ScrapedProduct
from ..models import (
    Category,
    Deal,
    DealCreate,
    DiscoveredProduct,
    DiscoveredProductCreate,
)

logger = logging.getLogger(__name__)


@dataclass
class DealAnalysis:
    """Analysis of a potential deal."""
    is_deal: bool
    deal_type: str  # "all_time_low", "extreme_discount", "price_error"
    discount_percent: float
    current_price: float
    all_time_low: float
    reason: str


class DealDetector:
    """Service for detecting deals by comparing prices to historical data."""

    def __init__(
        self,
        category_scraper: Optional[AmazonCategoryScraper] = None,
        camel_client: Optional[CamelCamelCamelClient] = None,
    ):
        self.category_scraper = category_scraper or AmazonCategoryScraper()
        self.camel_client = camel_client or CamelCamelCamelClient()
        self._owns_clients = category_scraper is None or camel_client is None

    def scan_category(
        self,
        category: Category,
        on_product_found: Optional[callable] = None,
        on_deal_found: Optional[callable] = None,
    ) -> tuple[list[DiscoveredProduct], list[Deal]]:
        """
        Scan a category for products and detect deals.

        Args:
            category: The category to scan
            on_product_found: Callback when a product is found (for DB storage)
            on_deal_found: Callback when a deal is detected (for notifications)

        Returns:
            Tuple of (discovered products, detected deals)
        """
        start_time = time.time()
        logger.info(f"Scanning category: {category.name}")

        # Scrape products from category page
        scraped_products = self.category_scraper.scrape_category(
            str(category.url),
            max_pages=3,
        )

        discovered_products: list[DiscoveredProduct] = []
        deals: list[Deal] = []

        for scraped in scraped_products:
            # Apply quality filters
            if not self._passes_filters(scraped, category):
                continue

            # Get price history from CamelCamelCamel
            price_stats = self.camel_client.get_price_history(scraped.asin)

            # Create discovered product record
            product = self._create_discovered_product(scraped, category.id, price_stats)
            discovered_products.append(product)

            if on_product_found:
                on_product_found(product)

            # Check if it's a deal
            if scraped.current_price and price_stats and price_stats.all_time_low:
                analysis = self._analyze_deal(
                    current_price=scraped.current_price,
                    all_time_low=price_stats.all_time_low,
                    min_discount=category.min_discount_percent,
                )

                if analysis.is_deal:
                    deal = self._create_deal(product, analysis)
                    deals.append(deal)

                    logger.info(
                        f"DEAL FOUND: {scraped.name[:50]} - "
                        f"${scraped.current_price:.2f} ({analysis.discount_percent:.0f}% below ATL)"
                    )

                    if on_deal_found:
                        on_deal_found(deal)

            # Rate limiting
            time.sleep(1.0)

        elapsed = time.time() - start_time
        logger.info(
            f"Category scan complete: {len(discovered_products)} products, "
            f"{len(deals)} deals found in {elapsed:.1f}s"
        )

        return discovered_products, deals

    def _passes_filters(self, product: ScrapedProduct, category: Category) -> bool:
        """Check if product passes category quality filters."""
        # Skip sponsored products
        if product.is_sponsored:
            return False

        # Minimum reviews filter
        if category.min_reviews > 0:
            if not product.review_count or product.review_count < category.min_reviews:
                return False

        # Minimum rating filter
        if category.min_rating > 0:
            if not product.rating or product.rating < category.min_rating:
                return False

        # Max price filter
        if category.max_price is not None and category.max_price > 0:
            if product.current_price and product.current_price > category.max_price:
                return False

        # Must have a price
        if not product.current_price or product.current_price <= 0:
            return False

        return True

    def _analyze_deal(
        self,
        current_price: float,
        all_time_low: float,
        min_discount: float = 50.0,
    ) -> DealAnalysis:
        """Analyze if the current price represents a deal."""

        # Calculate discount from all-time low
        if all_time_low <= 0:
            return DealAnalysis(
                is_deal=False,
                deal_type="",
                discount_percent=0,
                current_price=current_price,
                all_time_low=all_time_low,
                reason="Invalid all-time low price",
            )

        # Price below all-time low = new all-time low!
        if current_price < all_time_low:
            discount_percent = ((all_time_low - current_price) / all_time_low) * 100

            # Check if it's a price error (too good to be true)
            if discount_percent >= 90:
                return DealAnalysis(
                    is_deal=True,
                    deal_type="price_error",
                    discount_percent=discount_percent,
                    current_price=current_price,
                    all_time_low=all_time_low,
                    reason=f"Potential price error: {discount_percent:.0f}% below all-time low",
                )

            if discount_percent >= min_discount:
                return DealAnalysis(
                    is_deal=True,
                    deal_type="all_time_low",
                    discount_percent=discount_percent,
                    current_price=current_price,
                    all_time_low=all_time_low,
                    reason=f"New all-time low: {discount_percent:.0f}% below previous ATL of ${all_time_low:.2f}",
                )

        # Price at or near all-time low (within 5%)
        if current_price <= all_time_low * 1.05:
            return DealAnalysis(
                is_deal=True,
                deal_type="extreme_discount",
                discount_percent=0,
                current_price=current_price,
                all_time_low=all_time_low,
                reason=f"At all-time low price of ${all_time_low:.2f}",
            )

        return DealAnalysis(
            is_deal=False,
            deal_type="",
            discount_percent=0,
            current_price=current_price,
            all_time_low=all_time_low,
            reason=f"Current price ${current_price:.2f} is above ATL ${all_time_low:.2f}",
        )

    def _create_discovered_product(
        self,
        scraped: ScrapedProduct,
        category_id: UUID,
        price_stats: Optional[PriceStats],
    ) -> DiscoveredProduct:
        """Create a DiscoveredProduct from scraped data."""
        from uuid import uuid4

        now = datetime.utcnow()
        return DiscoveredProduct(
            id=uuid4(),
            asin=scraped.asin,
            name=scraped.name,
            url=scraped.url,
            current_price=scraped.current_price,
            list_price=scraped.list_price,
            rating=scraped.rating,
            review_count=scraped.review_count,
            category_id=category_id,
            image_url=scraped.image_url,
            all_time_low=price_stats.all_time_low if price_stats else None,
            all_time_high=price_stats.all_time_high if price_stats else None,
            created_at=now,
            updated_at=now,
            last_price_check=now,
        )

    def _create_deal(self, product: DiscoveredProduct, analysis: DealAnalysis) -> Deal:
        """Create a Deal from analysis results."""
        from uuid import uuid4

        return Deal(
            id=uuid4(),
            product_id=product.id,
            product_name=product.name,
            product_url=str(product.url),
            product_image=product.image_url,
            current_price=analysis.current_price,
            all_time_low=analysis.all_time_low,
            discount_percent=analysis.discount_percent,
            deal_type=analysis.deal_type,
            rating=product.rating,
            review_count=product.review_count,
            detected_at=datetime.utcnow(),
            notified=False,
            expired=False,
        )

    def check_single_product(self, asin: str) -> Optional[DealAnalysis]:
        """Check a single product for deals."""
        price_stats = self.camel_client.get_price_history(asin)
        if not price_stats or not price_stats.current_price or not price_stats.all_time_low:
            return None

        return self._analyze_deal(
            current_price=price_stats.current_price,
            all_time_low=price_stats.all_time_low,
        )

    def close(self) -> None:
        if self._owns_clients:
            self.category_scraper.close()
            self.camel_client.close()

    def __enter__(self) -> "DealDetector":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
