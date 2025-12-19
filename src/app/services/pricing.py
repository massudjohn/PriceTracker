from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional
from uuid import UUID

from bs4 import BeautifulSoup

from ..clients.amazon import AmazonClient
from ..database import SqlRepository
from ..models import PriceSnapshot, PriceSnapshotCreate, ProductUpdate
from .notifications import NotificationService

logger = logging.getLogger(__name__)


@dataclass
class PriceParseResult:
    current_price: Optional[float]
    list_price: Optional[float]
    availability: Optional[str]


class PriceParser:
    PRICE_SELECTORS = [
        "#priceblock_ourprice",
        "#priceblock_dealprice",
        "#priceblock_saleprice",
        "span.a-price > span.a-offscreen",
        "span.apexPriceToPay > span.a-offscreen",
    ]
    LIST_PRICE_SELECTORS = [
        "#priceblock_ourprice",
        "span.a-price.a-text-price > span.a-offscreen",
        "span.priceBlockStrikePriceString",
    ]

    @classmethod
    def parse_product_page(cls, html: str) -> PriceParseResult:
        soup = BeautifulSoup(html, "html.parser")

        current_price = cls._extract_price(soup, cls.PRICE_SELECTORS)
        list_price = cls._extract_price(soup, cls.LIST_PRICE_SELECTORS)
        availability = cls._extract_availability(soup)

        return PriceParseResult(
            current_price=current_price,
            list_price=list_price,
            availability=availability,
        )

    @classmethod
    def _extract_availability(cls, soup: BeautifulSoup) -> Optional[str]:
        availability_node = soup.select_one("#availability")
        if availability_node:
            text = availability_node.get_text(strip=True)
            return text or None
        return None

    @classmethod
    def _extract_price(cls, soup: BeautifulSoup, selectors: list[str]) -> Optional[float]:
        for selector in selectors:
            node = soup.select_one(selector)
            if node:
                price = cls._parse_price_string(node.get_text(strip=True))
                if price is not None:
                    return price
        return None

    @staticmethod
    def _parse_price_string(value: str) -> Optional[float]:
        # Strip common currency symbols and whitespace
        cleaned = re.sub(r"[^0-9,.-]", "", value)
        if not cleaned:
            return None

        # Handle regional decimal separators
        if "," in cleaned and "." in cleaned:
            if cleaned.rfind(",") > cleaned.rfind("."):
                cleaned = cleaned.replace(".", "").replace(",", ".")
            else:
                cleaned = cleaned.replace(",", "")
        elif "," in cleaned:
            comma_index = cleaned.rfind(",")
            if len(cleaned) - comma_index <= 3:
                cleaned = cleaned.replace(",", ".")
            else:
                cleaned = cleaned.replace(",", "")

        try:
            return float(cleaned)
        except ValueError:
            return None


class PriceFetcher:
    def __init__(self, repo: SqlRepository, client: Optional[AmazonClient] = None) -> None:
        self.repo = repo
        self.client = client or AmazonClient()
        self.notifier = NotificationService(self.repo)

    @staticmethod
    def extract_asin(url: str) -> Optional[str]:
        match = re.search(r"/dp/([A-Z0-9]{10})", url, re.IGNORECASE)
        if match:
            return match.group(1).upper()
        return None

    def fetch_and_store(self, asin: str, product_id: UUID) -> PriceSnapshot:
        html = self.client.fetch_product_page(asin)
        parsed = PriceParser.parse_product_page(html)

        median_price = self.repo.median_price_last_30_days(product_id)

        extreme_discount = False
        improbable_price = False

        if parsed.current_price is not None:
            if median_price is not None:
                extreme_discount = parsed.current_price <= median_price * 0.6
                improbable_price = parsed.current_price > median_price * 3
            if parsed.current_price <= 0:
                improbable_price = True
            if parsed.list_price is not None and parsed.current_price < parsed.list_price * 0.1:
                improbable_price = True

        snapshot = self.repo.record_price_snapshot(
            PriceSnapshotCreate(
                product_id=product_id,
                current_price=parsed.current_price,
                list_price=parsed.list_price,
                availability=parsed.availability,
            ),
            extreme_discount=extreme_discount,
            improbable_price=improbable_price,
        )

        if parsed.current_price is not None:
            self.repo.update_product(product_id, ProductUpdate(current_price=parsed.current_price))

        logger.info(
            "Recorded price snapshot",
            extra={
                "product_id": str(product_id),
                "asin": asin,
                "current_price": parsed.current_price,
                "extreme_discount": snapshot.extreme_discount,
                "improbable_price": snapshot.improbable_price,
            },
        )
        self.notifier.notify_if_anomaly(product_id, snapshot)
        if parsed.current_price is not None:
            self.notifier.notify_threshold_matches(product_id, parsed.current_price)
        return snapshot

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> "PriceFetcher":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[override]
        self.close()
