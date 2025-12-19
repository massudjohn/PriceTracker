from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from uuid import UUID

import redis
from rq import Queue
from rq.scheduler import Scheduler

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
QUEUE_NAME = os.getenv("QUEUE_NAME", "price-tracker")

_connection = redis.from_url(REDIS_URL)
queue = Queue(QUEUE_NAME, connection=_connection)
scheduler = Scheduler(queue=queue, connection=_connection)


def fetch_product_page(product_id: UUID | None = None) -> None:
    """
    Placeholder task for fetching and parsing a product page.
    In a real implementation this would retrieve the page, parse pricing data,
    and record a PriceRecord entry.
    """
    logger.info("Fetching product page", extra={"product_id": str(product_id)})


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
