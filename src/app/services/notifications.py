from __future__ import annotations

import logging
import os
import smtplib
from email.message import EmailMessage
from typing import List, Optional
from uuid import UUID

import httpx

from ..database import SqlRepository
from ..models import Alert, PriceSnapshot, Product, UserPreference

logger = logging.getLogger(__name__)


class NotificationService:
    def __init__(self, repo: SqlRepository):
        self.repo = repo

    def _resolve_channels(self, alert: Optional[Alert] = None) -> tuple[Optional[UserPreference], List[str]]:
        prefs = self.repo.get_preferences()
        if alert and alert.channel:
            return prefs, [alert.channel]

        channels: List[str] = []
        if prefs:
            if prefs.email:
                channels.append("email")
            if prefs.webhook_url:
                channels.append("webhook")
            if prefs.slack_webhook_url:
                channels.append("slack")
        return prefs, channels

    def notify_if_anomaly(self, product_id: UUID, snapshot: PriceSnapshot) -> None:
        reasons: List[str] = []
        if snapshot.extreme_discount:
            reasons.append("Extreme discount detected against 30-day median")
        if snapshot.improbable_price:
            reasons.append("Improbable price detected")
        if not reasons:
            return

        product = self.repo.get_product(product_id)
        if not product:
            return

        prefs, channels = self._resolve_channels()
        for channel in channels:
            self._dispatch(channel, prefs, product, snapshot, reasons)

    def notify_threshold_matches(self, product_id: UUID, current_price: float) -> None:
        alerts = self.repo.list_alerts_for_product(product_id)
        if not alerts:
            return
        product = self.repo.get_product(product_id)
        if not product:
            return

        for alert in alerts:
            if current_price <= alert.threshold_price:
                prefs, channels = self._resolve_channels(alert)
                reason = [f"Price dropped below alert threshold {alert.threshold_price}"]
                for channel in channels:
                    self._dispatch(channel, prefs, product, None, reason)

    def _dispatch(
        self,
        channel: str,
        prefs: Optional[UserPreference],
        product: Product,
        snapshot: Optional[PriceSnapshot],
        reasons: List[str],
    ) -> None:
        if channel == "email" and prefs and prefs.email:
            self._send_email(prefs, product, snapshot, reasons)
        elif channel == "webhook" and prefs and prefs.webhook_url:
            self._send_webhook(prefs.webhook_url, product, snapshot, reasons)
        elif channel == "slack" and prefs and prefs.slack_webhook_url:
            self._send_webhook(prefs.slack_webhook_url, product, snapshot, reasons)
        else:
            logger.warning("No dispatcher found for channel", extra={"channel": channel})

    def _send_email(
        self, prefs: UserPreference, product: Product, snapshot: Optional[PriceSnapshot], reasons: List[str]
    ) -> None:
        smtp_host = prefs.smtp_host or os.getenv("SMTP_HOST")
        smtp_username = prefs.smtp_username or os.getenv("SMTP_USERNAME")
        smtp_password = prefs.smtp_password or os.getenv("SMTP_PASSWORD")
        smtp_port = int(os.getenv("SMTP_PORT", "587"))

        if not smtp_host or not prefs.email:
            logger.warning("Skipping email notification; SMTP or recipient missing")
            return

        body_lines = [f"Product: {product.name}", f"URL: {product.url}"]
        if snapshot and snapshot.current_price is not None:
            body_lines.append(f"Current price: {snapshot.current_price}")
        body_lines.append("Reasons: " + "; ".join(reasons))

        message = EmailMessage()
        message["Subject"] = f"Price alert for {product.name}"
        message["From"] = smtp_username or "alerts@pricetracker"
        message["To"] = prefs.email
        message.set_content("\n".join(body_lines))

        try:
            with smtplib.SMTP(smtp_host, smtp_port) as smtp:
                smtp.starttls()
                if smtp_username and smtp_password:
                    smtp.login(smtp_username, smtp_password)
                smtp.send_message(message)
                logger.info("Sent email notification", extra={"product_id": str(product.id)})
        except Exception:
            logger.exception("Failed to send email notification")

    def _send_webhook(self, url: str, product: Product, snapshot: Optional[PriceSnapshot], reasons: List[str]) -> None:
        payload = {
            "product_id": str(product.id),
            "product_name": product.name,
            "url": str(product.url),
            "current_price": snapshot.current_price if snapshot else None,
            "reasons": reasons,
        }
        try:
            with httpx.Client(timeout=5.0) as client:
                response = client.post(url, json=payload)
                response.raise_for_status()
                logger.info("Webhook notification sent", extra={"url": url})
        except Exception:
            logger.exception("Failed to send webhook notification", extra={"url": url})
