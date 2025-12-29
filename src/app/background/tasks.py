from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from ..database import get_repository
from ..services.pricing import PriceFetcher

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
QUEUE_NAME = os.getenv("QUEUE_NAME", "price-tracker")

# Lazy initialization for Redis/RQ - only connect when needed
_connection = None
_queue = None
_scheduler = None


def _get_connection():
    global _connection
    if _connection is None:
        try:
            import redis
            _connection = redis.from_url(REDIS_URL)
        except ImportError:
            logger.warning("redis package not installed; background jobs disabled")
            return None
        except Exception as e:
            logger.warning(f"Failed to connect to Redis: {e}")
            return None
    return _connection


def _get_queue():
    global _queue
    if _queue is None:
        conn = _get_connection()
        if conn:
            try:
                from rq import Queue
                _queue = Queue(QUEUE_NAME, connection=conn)
            except ImportError:
                logger.warning("rq package not installed; background jobs disabled")
                return None
    return _queue


def _get_scheduler():
    global _scheduler
    if _scheduler is None:
        conn = _get_connection()
        queue = _get_queue()
        if conn and queue:
            try:
                # Try rq-scheduler package first (separate package)
                from rq_scheduler import Scheduler
                _scheduler = Scheduler(queue=queue, connection=conn)
            except ImportError:
                try:
                    # Fallback to built-in scheduler in newer rq versions
                    from rq.scheduler import Scheduler
                    _scheduler = Scheduler(queue=queue, connection=conn)
                except (ImportError, AttributeError):
                    logger.warning("rq-scheduler not available; periodic jobs disabled")
                    return None
    return _scheduler


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
    scheduler = _get_scheduler()
    if scheduler is None:
        logger.info("Scheduler not available; periodic fetches disabled")
        return

    try:
        existing_jobs = scheduler.get_jobs()
        if not any(getattr(job, 'func', None) == fetch_product_page for job in existing_jobs):
            scheduler.schedule(
                scheduled_time=datetime.utcnow(),
                func=fetch_product_page,
                args=(),
                interval=timedelta(minutes=interval_minutes).total_seconds(),
                repeat=None,
            )
            logger.info("Scheduled periodic fetches", extra={"interval_minutes": interval_minutes})
    except Exception as e:
        logger.warning(f"Failed to configure scheduler: {e}")
