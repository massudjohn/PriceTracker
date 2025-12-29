from __future__ import annotations

import logging
import os
import re
import smtplib
from dataclasses import dataclass
from datetime import datetime
from email.message import EmailMessage
from typing import List, Optional
from uuid import UUID

import httpx

from ..database import SqlRepository
from ..models import Alert, Deal, PriceSnapshot, Product, UserPreference

logger = logging.getLogger(__name__)


@dataclass
class NotificationResult:
    success: bool
    channel: str
    message: str
    sent_at: datetime


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

    def _format_price(self, price: Optional[float]) -> str:
        """Format price with currency symbol."""
        if price is None:
            return "N/A"
        return f"${price:,.2f}"

    def _build_email_body(
        self, product: Product, snapshot: Optional[PriceSnapshot], reasons: List[str]
    ) -> str:
        """Build a well-formatted email body with all relevant details."""
        lines = [
            "=" * 50,
            "PRICE TRACKER ALERT",
            "=" * 50,
            "",
            f"Product: {product.name}",
            f"URL: {product.url}",
            "",
            "-" * 30,
            "PRICE INFORMATION",
            "-" * 30,
        ]

        if snapshot:
            lines.append(f"Current Price: {self._format_price(snapshot.current_price)}")
            if snapshot.list_price:
                lines.append(f"List Price: {self._format_price(snapshot.list_price)}")
                if snapshot.current_price and snapshot.list_price > 0:
                    discount = ((snapshot.list_price - snapshot.current_price) / snapshot.list_price) * 100
                    if discount > 0:
                        lines.append(f"Discount: {discount:.1f}% off")
            if snapshot.availability:
                lines.append(f"Availability: {snapshot.availability}")
        elif product.current_price is not None:
            lines.append(f"Current Price: {self._format_price(product.current_price)}")

        if product.desired_price is not None:
            lines.append(f"Your Target Price: {self._format_price(product.desired_price)}")

        lines.extend([
            "",
            "-" * 30,
            "ALERT REASONS",
            "-" * 30,
        ])
        for reason in reasons:
            lines.append(f"• {reason}")

        lines.extend([
            "",
            "=" * 50,
            "This is an automated message from Price Tracker.",
            "Manage your alerts at your Price Tracker dashboard.",
            "=" * 50,
        ])

        return "\n".join(lines)

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

        if not self.validate_email(prefs.email):
            logger.warning("Skipping email notification; invalid email format", extra={"email": prefs.email})
            return

        body = self._build_email_body(product, snapshot, reasons)

        # Determine subject based on alert type
        subject_prefix = "🔔 Price Alert"
        if snapshot:
            if snapshot.extreme_discount:
                subject_prefix = "🎉 Extreme Discount"
            elif snapshot.improbable_price:
                subject_prefix = "⚠️ Price Warning"

        message = EmailMessage()
        message["Subject"] = f"{subject_prefix}: {product.name}"
        message["From"] = smtp_username or "alerts@pricetracker"
        message["To"] = prefs.email
        message.set_content(body)

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

    @staticmethod
    def validate_email(email: str) -> bool:
        """Validate email address format."""
        pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        return bool(re.match(pattern, email))

    def send_test_email(self) -> NotificationResult:
        """Send a test email to verify SMTP configuration."""
        prefs = self.repo.get_preferences()
        if not prefs:
            return NotificationResult(
                success=False,
                channel="email",
                message="No preferences configured. Please set up email preferences first.",
                sent_at=datetime.utcnow(),
            )

        if not prefs.email:
            return NotificationResult(
                success=False,
                channel="email",
                message="No recipient email address configured in preferences.",
                sent_at=datetime.utcnow(),
            )

        if not self.validate_email(prefs.email):
            return NotificationResult(
                success=False,
                channel="email",
                message=f"Invalid email address format: {prefs.email}",
                sent_at=datetime.utcnow(),
            )

        smtp_host = prefs.smtp_host or os.getenv("SMTP_HOST")
        smtp_username = prefs.smtp_username or os.getenv("SMTP_USERNAME")
        smtp_password = prefs.smtp_password or os.getenv("SMTP_PASSWORD")
        smtp_port = int(os.getenv("SMTP_PORT", "587"))

        if not smtp_host:
            return NotificationResult(
                success=False,
                channel="email",
                message="No SMTP host configured. Set smtp_host in preferences or SMTP_HOST environment variable.",
                sent_at=datetime.utcnow(),
            )

        message = EmailMessage()
        message["Subject"] = "Price Tracker - Test Email"
        message["From"] = smtp_username or "alerts@pricetracker"
        message["To"] = prefs.email
        message.set_content(
            "This is a test email from your Price Tracker application.\n\n"
            "If you received this email, your email notification settings are configured correctly!\n\n"
            "You will receive notifications when:\n"
            "- A tracked product's price drops below your alert threshold\n"
            "- An extreme discount is detected (40%+ off 30-day median)\n"
            "- An improbable price is detected (potential error or scam)\n\n"
            "Happy price tracking!"
        )

        try:
            with smtplib.SMTP(smtp_host, smtp_port) as smtp:
                smtp.starttls()
                if smtp_username and smtp_password:
                    smtp.login(smtp_username, smtp_password)
                smtp.send_message(message)
                logger.info("Test email sent successfully", extra={"recipient": prefs.email})
                return NotificationResult(
                    success=True,
                    channel="email",
                    message=f"Test email sent successfully to {prefs.email}",
                    sent_at=datetime.utcnow(),
                )
        except smtplib.SMTPAuthenticationError as e:
            logger.exception("SMTP authentication failed")
            return NotificationResult(
                success=False,
                channel="email",
                message=f"SMTP authentication failed: {str(e)}",
                sent_at=datetime.utcnow(),
            )
        except smtplib.SMTPConnectError as e:
            logger.exception("Failed to connect to SMTP server")
            return NotificationResult(
                success=False,
                channel="email",
                message=f"Failed to connect to SMTP server {smtp_host}:{smtp_port}: {str(e)}",
                sent_at=datetime.utcnow(),
            )
        except Exception as e:
            logger.exception("Failed to send test email")
            return NotificationResult(
                success=False,
                channel="email",
                message=f"Failed to send test email: {str(e)}",
                sent_at=datetime.utcnow(),
            )

    def send_deal_notification(self, deal: Deal) -> NotificationResult:
        """Send an instant notification for a detected deal."""
        prefs = self.repo.get_preferences()
        if not prefs or not prefs.email:
            return NotificationResult(
                success=False,
                channel="email",
                message="No email configured",
                sent_at=datetime.utcnow(),
            )

        smtp_host = prefs.smtp_host or os.getenv("SMTP_HOST")
        smtp_username = prefs.smtp_username or os.getenv("SMTP_USERNAME")
        smtp_password = prefs.smtp_password or os.getenv("SMTP_PASSWORD")
        smtp_port = int(os.getenv("SMTP_PORT", "587"))

        if not smtp_host:
            return NotificationResult(
                success=False,
                channel="email",
                message="No SMTP host configured",
                sent_at=datetime.utcnow(),
            )

        # Build email body for deal
        deal_type_label = {
            "all_time_low": "NEW ALL-TIME LOW",
            "price_error": "POTENTIAL PRICE ERROR",
            "extreme_discount": "EXTREME DISCOUNT",
        }.get(deal.deal_type, "DEAL ALERT")

        body = f"""
{'=' * 50}
{deal_type_label}
{'=' * 50}

Product: {deal.product_name}
URL: {deal.product_url}

{'-' * 30}
PRICE INFORMATION
{'-' * 30}
Current Price: ${deal.current_price:.2f}
All-Time Low: ${deal.all_time_low:.2f}
Discount: {deal.discount_percent:.0f}% BELOW all-time low!

{'-' * 30}
PRODUCT QUALITY
{'-' * 30}
Rating: {deal.rating:.1f}/5.0 stars
Reviews: {deal.review_count:,} reviews

{'=' * 50}
This deal was automatically detected by Deal Hunter.
Act fast - deals like this don't last long!
{'=' * 50}
"""

        # Subject with emoji based on deal type
        if deal.deal_type == "price_error":
            subject = f"⚠️ PRICE ERROR? {deal.product_name[:50]} - ${deal.current_price:.2f} ({deal.discount_percent:.0f}% below ATL)"
        else:
            subject = f"🔥 DEAL ALERT: {deal.product_name[:50]} - ${deal.current_price:.2f} ({deal.discount_percent:.0f}% below ATL)"

        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = smtp_username or "deals@dealhunter"
        message["To"] = prefs.email
        message.set_content(body)

        try:
            with smtplib.SMTP(smtp_host, smtp_port) as smtp:
                smtp.starttls()
                if smtp_username and smtp_password:
                    smtp.login(smtp_username, smtp_password)
                smtp.send_message(message)
                logger.info("Deal notification sent", extra={"deal_id": str(deal.id)})
                return NotificationResult(
                    success=True,
                    channel="email",
                    message=f"Deal notification sent to {prefs.email}",
                    sent_at=datetime.utcnow(),
                )
        except Exception as e:
            logger.exception("Failed to send deal notification")
            return NotificationResult(
                success=False,
                channel="email",
                message=f"Failed to send notification: {str(e)}",
                sent_at=datetime.utcnow(),
            )
