"""
In-memory persistence for the prototype application.
This can be swapped for a real database later without changing the API surface.
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict, List
from uuid import UUID

from .models import (
    Alert,
    AlertCreate,
    AlertUpdate,
    Product,
    ProductCreate,
    ProductUpdate,
    new_alert,
    new_product,
)


class InMemoryRepository:
    def __init__(self) -> None:
        self.products: Dict[UUID, Product] = {}
        self.alerts: Dict[UUID, Alert] = {}

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


def get_repository() -> InMemoryRepository:
    # For now this returns a global singleton. In production we would wire this
    # through dependency injection tied to a database session.
    global _repository
    try:
        return _repository
    except NameError:
        _repository = InMemoryRepository()
        return _repository
