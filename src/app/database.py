"""
In-memory persistence for the prototype application.
This can be swapped for a real database later without changing the API surface.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from statistics import median
from typing import Dict, List
from uuid import UUID

from .models import (
    Alert,
    AlertCreate,
    AlertUpdate,
    Product,
    ProductCreate,
    ProductUpdate,
    PriceSnapshot,
    PriceSnapshotCreate,
    new_alert,
    new_product,
    new_price_snapshot,
)


class InMemoryRepository:
    def __init__(self) -> None:
        self.products: Dict[UUID, Product] = {}
        self.alerts: Dict[UUID, Alert] = {}
        self.price_snapshots: List[PriceSnapshot] = []

    # Product CRUD
    def list_products(self) -> List[Product]:
        return list(self.products.values())

    def get_product(self, product_id: UUID) -> Product | None:
        return self.products.get(product_id)

    def create_product(self, data: ProductCreate) -> Product:
        product = new_product(data)
        self.products[product.id] = product
        return product

    def update_product(self, product_id: UUID, data: ProductUpdate) -> Product | None:
        product = self.products.get(product_id)
        if not product:
            return None
        updated = product.model_copy(update=data.model_dump(exclude_unset=True))
        updated.updated_at = datetime.utcnow()
        self.products[product_id] = updated
        return updated

    def delete_product(self, product_id: UUID) -> bool:
        return self.products.pop(product_id, None) is not None

    # Alert CRUD
    def list_alerts(self) -> List[Alert]:
        return list(self.alerts.values())

    def get_alert(self, alert_id: UUID) -> Alert | None:
        return self.alerts.get(alert_id)

    def create_alert(self, data: AlertCreate) -> Alert:
        alert = new_alert(data)
        self.alerts[alert.id] = alert
        return alert

    def update_alert(self, alert_id: UUID, data: AlertUpdate) -> Alert | None:
        alert = self.alerts.get(alert_id)
        if not alert:
            return None
        updated = alert.model_copy(update=data.model_dump(exclude_unset=True))
        self.alerts[alert_id] = updated
        return updated

    def delete_alert(self, alert_id: UUID) -> bool:
        return self.alerts.pop(alert_id, None) is not None

    # Pricing snapshots
    def list_price_snapshots(self, product_id: UUID | None = None) -> List[PriceSnapshot]:
        if product_id:
            return [s for s in self.price_snapshots if s.product_id == product_id]
        return list(self.price_snapshots)

    def _median_price_last_30_days(self, product_id: UUID) -> float | None:
        cutoff = datetime.utcnow() - timedelta(days=30)
        prices = [
            snapshot.current_price
            for snapshot in self.price_snapshots
            if snapshot.product_id == product_id
            and snapshot.current_price is not None
            and snapshot.collected_at >= cutoff
        ]
        if not prices:
            return None
        return median(prices)

    def record_price_snapshot(self, data: PriceSnapshotCreate) -> PriceSnapshot:
        median_price = self._median_price_last_30_days(data.product_id)

        extreme_discount = False
        improbable_price = False

        if data.current_price is not None:
            if median_price is not None:
                extreme_discount = data.current_price <= median_price * 0.6
                improbable_price = data.current_price > median_price * 3
            if data.current_price <= 0:
                improbable_price = True
            if data.list_price is not None and data.current_price < data.list_price * 0.1:
                improbable_price = True

        snapshot = new_price_snapshot(
            data,
            extreme_discount=extreme_discount,
            improbable_price=improbable_price,
        )
        self.price_snapshots.append(snapshot)
        return snapshot


def get_repository() -> InMemoryRepository:
    # For now this returns a global singleton. In production we would wire this
    # through dependency injection tied to a database session.
    global _repository
    try:
        return _repository
    except NameError:
        _repository = InMemoryRepository()
        return _repository
