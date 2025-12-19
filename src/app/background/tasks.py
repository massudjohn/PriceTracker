from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from uuid import UUID

import redis
from rq import Queue
from rq.scheduler import Scheduler

from ..database import get_repository
from ..services.pricing import PriceFetcher

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
QUEUE_NAME = os.getenv("QUEUE_NAME", "price-tracker")

_connection = redis.from_url(REDIS_URL)
queue = Queue(QUEUE_NAME, connection=_connection)
scheduler = Scheduler(queue=queue, connection=_connection)


def fetch_product_page(product_id: UUID | None = None) -> None:
    """Fetch and store the latest price snapshot for one or all products."""
    repo = get_repository()
    try:
        with PriceFetcher(repo) as fetcher:
            if product_id:
                product = repo.get_product(product_id)
                if not product:
                    logger.warning("Product not found during fetch", extra={"product_id": str(product_id)})
                    return
                asin = fetcher.extract_asin(str(product.url))
                if not asin:
                    logger.warning("Could not derive ASIN from URL", extra={"product_id": str(product_id)})
                    return
                fetcher.fetch_and_store(asin, product.id)
                return

            for product in repo.list_products():
                asin = fetcher.extract_asin(str(product.url))
                if not asin:
                    logger.warning("Could not derive ASIN from URL", extra={"product_id": str(product.id)})
                    continue
                try:
                    fetcher.fetch_and_store(asin, product.id)
                except Exception:
                    logger.exception("Failed to fetch product page", extra={"product_id": str(product.id)})
    finally:
        repo.close()


def queue_periodic_fetches(interval_minutes: int = 30) -> None:
    """Ensure a periodic job is scheduled to refresh product pricing."""
    try:
        existing_jobs = scheduler.get_jobs()  # type: ignore[assignment]
        if not any(job.func == fetch_product_page for job in existing_jobs):
            scheduler.schedule(
                scheduled_time=datetime.utcnow(),
                func=fetch_product_page,
                args=(),
                interval=timedelta(minutes=interval_minutes).total_seconds(),
                repeat=None,
            )
            logger.info("Scheduled periodic fetches", extra={"interval_minutes": interval_minutes})
    except redis.ConnectionError:
        logger.warning("Redis unavailable; skipping scheduler configuration")
