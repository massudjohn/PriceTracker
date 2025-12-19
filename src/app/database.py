from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import datetime, timedelta
from statistics import median
from typing import Iterable, List, Optional
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, create_engine
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

from .models import (
    Alert,
    AlertCreate,
    AlertUpdate,
    PriceSnapshot,
    PriceSnapshotCreate,
    Product,
    ProductCreate,
    ProductUpdate,
    UserPreference,
    UserPreferenceCreate,
    UserPreferenceUpdate,
)


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./price_tracker.db")
engine = create_engine(DATABASE_URL, echo=False, future=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


class ProductTable(Base):
    __tablename__ = "products"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True) if engine.url.get_backend_name() != "sqlite" else String, primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String, nullable=False)
    url: Mapped[str] = mapped_column(String, nullable=False)
    desired_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    current_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    alerts: Mapped[List["AlertTable"]] = relationship("AlertTable", back_populates="product", cascade="all, delete-orphan")
    snapshots: Mapped[List["PriceSnapshotTable"]] = relationship(
        "PriceSnapshotTable", back_populates="product", cascade="all, delete-orphan"
    )


class AlertTable(Base):
    __tablename__ = "alerts"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True) if engine.url.get_backend_name() != "sqlite" else String, primary_key=True, default=uuid4)
    product_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True) if engine.url.get_backend_name() != "sqlite" else String, ForeignKey("products.id"), nullable=False
    )
    threshold_price: Mapped[float] = mapped_column(Float, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    channel: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    product: Mapped[ProductTable] = relationship("ProductTable", back_populates="alerts")


class PriceSnapshotTable(Base):
    __tablename__ = "price_snapshots"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True) if engine.url.get_backend_name() != "sqlite" else String, primary_key=True, default=uuid4)
    product_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True) if engine.url.get_backend_name() != "sqlite" else String, ForeignKey("products.id"), nullable=False
    )
    current_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    list_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    availability: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    source: Mapped[str] = mapped_column(String, default="amazon", nullable=False)
    extreme_discount: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    improbable_price: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    product: Mapped[ProductTable] = relationship("ProductTable", back_populates="snapshots")


class UserPreferenceTable(Base):
    __tablename__ = "user_preferences"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True) if engine.url.get_backend_name() != "sqlite" else String, primary_key=True, default=uuid4)
    email: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    smtp_host: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    smtp_username: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    smtp_password: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    webhook_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    slack_webhook_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, onupdate=datetime.utcnow)


def _product_to_schema(row: ProductTable) -> Product:
    return Product(
        id=row.id if isinstance(row.id, UUID) else UUID(row.id),
        name=row.name,
        url=row.url,
        desired_price=row.desired_price,
        current_price=row.current_price,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _alert_to_schema(row: AlertTable) -> Alert:
    return Alert(
        id=row.id if isinstance(row.id, UUID) else UUID(row.id),
        product_id=row.product_id if isinstance(row.product_id, UUID) else UUID(row.product_id),
        threshold_price=row.threshold_price,
        active=row.active,
        channel=row.channel,
        created_at=row.created_at,
    )


def _snapshot_to_schema(row: PriceSnapshotTable) -> PriceSnapshot:
    return PriceSnapshot(
        id=row.id if isinstance(row.id, UUID) else UUID(row.id),
        product_id=row.product_id if isinstance(row.product_id, UUID) else UUID(row.product_id),
        current_price=row.current_price,
        list_price=row.list_price,
        availability=row.availability,
        collected_at=row.collected_at,
        source=row.source,
        extreme_discount=row.extreme_discount,
        improbable_price=row.improbable_price,
    )


def _preferences_to_schema(row: UserPreferenceTable) -> UserPreference:
    return UserPreference(
        id=row.id if isinstance(row.id, UUID) else UUID(row.id),
        email=row.email,
        smtp_host=row.smtp_host,
        smtp_username=row.smtp_username,
        smtp_password=row.smtp_password,
        webhook_url=row.webhook_url,
        slack_webhook_url=row.slack_webhook_url,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class SqlRepository:
    def __init__(self, session: Session):
        self.session = session

    def close(self) -> None:
        self.session.close()

    # Product CRUD
    def list_products(self) -> List[Product]:
        return [_product_to_schema(row) for row in self.session.query(ProductTable).all()]

    def get_product(self, product_id: UUID) -> Optional[Product]:
        row = self.session.get(ProductTable, str(product_id))
        return _product_to_schema(row) if row else None

    def create_product(self, data: ProductCreate) -> Product:
        row = ProductTable(
            id=uuid4(),
            name=data.name,
            url=str(data.url),
            desired_price=data.desired_price,
            current_price=data.current_price,
        )
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return _product_to_schema(row)

    def update_product(self, product_id: UUID, data: ProductUpdate) -> Optional[Product]:
        row: ProductTable | None = self.session.get(ProductTable, str(product_id))
        if not row:
            return None
        for key, value in data.model_dump(exclude_unset=True).items():
            setattr(row, key, value)
        row.updated_at = datetime.utcnow()
        self.session.commit()
        self.session.refresh(row)
        return _product_to_schema(row)

    def delete_product(self, product_id: UUID) -> bool:
        row = self.session.get(ProductTable, str(product_id))
        if not row:
            return False
        self.session.delete(row)
        self.session.commit()
        return True

    # Alert CRUD
    def list_alerts(self) -> List[Alert]:
        return [_alert_to_schema(row) for row in self.session.query(AlertTable).all()]

    def list_alerts_for_product(self, product_id: UUID) -> List[Alert]:
        rows = (
            self.session.query(AlertTable)
            .filter(AlertTable.product_id == str(product_id))
            .filter(AlertTable.active.is_(True))
            .all()
        )
        return [_alert_to_schema(row) for row in rows]

    def get_alert(self, alert_id: UUID) -> Optional[Alert]:
        row = self.session.get(AlertTable, str(alert_id))
        return _alert_to_schema(row) if row else None

    def create_alert(self, data: AlertCreate) -> Alert:
        row = AlertTable(
            id=uuid4(),
            product_id=data.product_id,
            threshold_price=data.threshold_price,
            active=data.active,
            channel=data.channel,
        )
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return _alert_to_schema(row)

    def update_alert(self, alert_id: UUID, data: AlertUpdate) -> Optional[Alert]:
        row: AlertTable | None = self.session.get(AlertTable, str(alert_id))
        if not row:
            return None
        for key, value in data.model_dump(exclude_unset=True).items():
            setattr(row, key, value)
        self.session.commit()
        self.session.refresh(row)
        return _alert_to_schema(row)

    def delete_alert(self, alert_id: UUID) -> bool:
        row = self.session.get(AlertTable, str(alert_id))
        if not row:
            return False
        self.session.delete(row)
        self.session.commit()
        return True

    # Pricing snapshots
    def list_price_snapshots(self, product_id: UUID | None = None) -> List[PriceSnapshot]:
        query = self.session.query(PriceSnapshotTable)
        if product_id:
            query = query.filter(PriceSnapshotTable.product_id == str(product_id))
        return [_snapshot_to_schema(row) for row in query.order_by(PriceSnapshotTable.collected_at.desc()).all()]

    def record_price_snapshot(self, data: PriceSnapshotCreate, *, extreme_discount: bool, improbable_price: bool) -> PriceSnapshot:
        row = PriceSnapshotTable(
            id=uuid4(),
            product_id=data.product_id,
            current_price=data.current_price,
            list_price=data.list_price,
            availability=data.availability,
            source=data.source,
            extreme_discount=extreme_discount,
            improbable_price=improbable_price,
        )
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return _snapshot_to_schema(row)

    def median_price_last_30_days(self, product_id: UUID) -> Optional[float]:
        cutoff = datetime.utcnow() - timedelta(days=30)
        prices = [
            row.current_price
            for row in self.session.query(PriceSnapshotTable)
            .filter(PriceSnapshotTable.product_id == str(product_id))
            .filter(PriceSnapshotTable.current_price.isnot(None))
            .filter(PriceSnapshotTable.collected_at >= cutoff)
            .all()
        ]
        numeric_prices = [p for p in prices if p is not None]
        if not numeric_prices:
            return None
        return median(numeric_prices)

    # User preferences
    def get_preferences(self) -> Optional[UserPreference]:
        row = self.session.query(UserPreferenceTable).first()
        return _preferences_to_schema(row) if row else None

    def upsert_preferences(self, data: UserPreferenceCreate | UserPreferenceUpdate) -> UserPreference:
        existing = self.session.query(UserPreferenceTable).first()
        payload = data.model_dump(exclude_unset=True)
        if existing:
            for key, value in payload.items():
                setattr(existing, key, value)
            existing.updated_at = datetime.utcnow()
            self.session.commit()
            self.session.refresh(existing)
            return _preferences_to_schema(existing)
        row = UserPreferenceTable(id=uuid4(), **payload)
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return _preferences_to_schema(row)


@contextmanager
def get_session() -> Iterable[Session]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


def get_repository() -> SqlRepository:
    if not getattr(get_repository, "_initialized", False):
        init_db()
        get_repository._initialized = True
    session = SessionLocal()
    return SqlRepository(session)
