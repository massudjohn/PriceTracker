from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import datetime, timedelta
from statistics import median
from typing import Iterable, List, Optional
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, create_engine
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

from .models import (
    Alert,
    AlertCreate,
    AlertUpdate,
    Category,
    CategoryCreate,
    CategoryUpdate,
    Deal,
    DealCreate,
    DiscoveredProduct,
    DiscoveredProductCreate,
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


# ============ Category Table ============

class CategoryTable(Base):
    __tablename__ = "categories"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True) if engine.url.get_backend_name() != "sqlite" else String, primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String, nullable=False)
    url: Mapped[str] = mapped_column(String, nullable=False)
    min_reviews: Mapped[int] = mapped_column(Integer, default=100)
    min_rating: Mapped[float] = mapped_column(Float, default=4.0)
    max_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    min_discount_percent: Mapped[float] = mapped_column(Float, default=50.0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    product_count: Mapped[int] = mapped_column(Integer, default=0)
    last_scanned_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    products: Mapped[List["DiscoveredProductTable"]] = relationship("DiscoveredProductTable", back_populates="category", cascade="all, delete-orphan")


# ============ Discovered Product Table ============

class DiscoveredProductTable(Base):
    __tablename__ = "discovered_products"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True) if engine.url.get_backend_name() != "sqlite" else String, primary_key=True, default=uuid4)
    asin: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(String, nullable=False)
    current_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    list_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    rating: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    review_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    sales_rank: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    image_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    all_time_low: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    all_time_high: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    category_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True) if engine.url.get_backend_name() != "sqlite" else String,
        ForeignKey("categories.id"),
        nullable=False
    )
    last_price_check: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    category: Mapped[CategoryTable] = relationship("CategoryTable", back_populates="products")


# ============ Deal Table ============

class DealTable(Base):
    __tablename__ = "deals"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True) if engine.url.get_backend_name() != "sqlite" else String, primary_key=True, default=uuid4)
    product_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True) if engine.url.get_backend_name() != "sqlite" else String, nullable=False)
    product_name: Mapped[str] = mapped_column(Text, nullable=False)
    product_url: Mapped[str] = mapped_column(String, nullable=False)
    product_image: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    current_price: Mapped[float] = mapped_column(Float, nullable=False)
    all_time_low: Mapped[float] = mapped_column(Float, nullable=False)
    discount_percent: Mapped[float] = mapped_column(Float, nullable=False)
    deal_type: Mapped[str] = mapped_column(String, nullable=False)
    rating: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    review_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    notified: Mapped[bool] = mapped_column(Boolean, default=False)
    expired: Mapped[bool] = mapped_column(Boolean, default=False)


# ============ Legacy Tables ============

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
    instant_notifications: Mapped[bool] = mapped_column(Boolean, default=True)
    daily_digest: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, onupdate=datetime.utcnow)


# ============ Schema Converters ============

def _category_to_schema(row: CategoryTable) -> Category:
    return Category(
        id=row.id if isinstance(row.id, UUID) else UUID(row.id),
        name=row.name,
        url=row.url,
        min_reviews=row.min_reviews,
        min_rating=row.min_rating,
        max_price=row.max_price,
        min_discount_percent=row.min_discount_percent,
        active=row.active,
        product_count=row.product_count,
        last_scanned_at=row.last_scanned_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _discovered_product_to_schema(row: DiscoveredProductTable) -> DiscoveredProduct:
    return DiscoveredProduct(
        id=row.id if isinstance(row.id, UUID) else UUID(row.id),
        asin=row.asin,
        name=row.name,
        url=row.url,
        current_price=row.current_price,
        list_price=row.list_price,
        rating=row.rating,
        review_count=row.review_count,
        sales_rank=row.sales_rank,
        image_url=row.image_url,
        all_time_low=row.all_time_low,
        all_time_high=row.all_time_high,
        category_id=row.category_id if isinstance(row.category_id, UUID) else UUID(row.category_id),
        last_price_check=row.last_price_check,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _deal_to_schema(row: DealTable) -> Deal:
    return Deal(
        id=row.id if isinstance(row.id, UUID) else UUID(row.id),
        product_id=row.product_id if isinstance(row.product_id, UUID) else UUID(row.product_id),
        product_name=row.product_name,
        product_url=row.product_url,
        product_image=row.product_image,
        current_price=row.current_price,
        all_time_low=row.all_time_low,
        discount_percent=row.discount_percent,
        deal_type=row.deal_type,
        rating=row.rating,
        review_count=row.review_count,
        detected_at=row.detected_at,
        notified=row.notified,
        expired=row.expired,
    )


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
        instant_notifications=row.instant_notifications,
        daily_digest=row.daily_digest,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


# ============ Repository ============

class SqlRepository:
    def __init__(self, session: Session):
        self.session = session

    def close(self) -> None:
        self.session.close()

    # ---- Category CRUD ----

    def list_categories(self, active_only: bool = False) -> List[Category]:
        query = self.session.query(CategoryTable)
        if active_only:
            query = query.filter(CategoryTable.active.is_(True))
        return [_category_to_schema(row) for row in query.all()]

    def get_category(self, category_id: UUID) -> Optional[Category]:
        row = self.session.get(CategoryTable, str(category_id))
        return _category_to_schema(row) if row else None

    def create_category(self, data: CategoryCreate) -> Category:
        row = CategoryTable(
            id=uuid4(),
            name=data.name,
            url=str(data.url),
            min_reviews=data.min_reviews,
            min_rating=data.min_rating,
            max_price=data.max_price,
            min_discount_percent=data.min_discount_percent,
            active=data.active,
        )
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return _category_to_schema(row)

    def update_category(self, category_id: UUID, data: CategoryUpdate) -> Optional[Category]:
        row = self.session.get(CategoryTable, str(category_id))
        if not row:
            return None
        for key, value in data.model_dump(exclude_unset=True).items():
            if key == "url" and value:
                value = str(value)
            setattr(row, key, value)
        row.updated_at = datetime.utcnow()
        self.session.commit()
        self.session.refresh(row)
        return _category_to_schema(row)

    def delete_category(self, category_id: UUID) -> bool:
        row = self.session.get(CategoryTable, str(category_id))
        if not row:
            return False
        self.session.delete(row)
        self.session.commit()
        return True

    def update_category_scan_time(self, category_id: UUID, product_count: int) -> None:
        row = self.session.get(CategoryTable, str(category_id))
        if row:
            row.last_scanned_at = datetime.utcnow()
            row.product_count = product_count
            self.session.commit()

    # ---- Discovered Products ----

    def upsert_discovered_product(self, product: DiscoveredProduct) -> DiscoveredProduct:
        # Check if product exists by ASIN
        existing = self.session.query(DiscoveredProductTable).filter(
            DiscoveredProductTable.asin == product.asin
        ).first()

        if existing:
            existing.current_price = product.current_price
            existing.list_price = product.list_price
            existing.rating = product.rating
            existing.review_count = product.review_count
            existing.all_time_low = product.all_time_low
            existing.all_time_high = product.all_time_high
            existing.last_price_check = datetime.utcnow()
            existing.updated_at = datetime.utcnow()
            self.session.commit()
            self.session.refresh(existing)
            return _discovered_product_to_schema(existing)

        row = DiscoveredProductTable(
            id=product.id,
            asin=product.asin,
            name=product.name,
            url=str(product.url),
            current_price=product.current_price,
            list_price=product.list_price,
            rating=product.rating,
            review_count=product.review_count,
            sales_rank=product.sales_rank,
            image_url=product.image_url,
            all_time_low=product.all_time_low,
            all_time_high=product.all_time_high,
            category_id=product.category_id,
        )
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return _discovered_product_to_schema(row)

    def get_discovered_product_by_asin(self, asin: str) -> Optional[DiscoveredProduct]:
        row = self.session.query(DiscoveredProductTable).filter(
            DiscoveredProductTable.asin == asin
        ).first()
        return _discovered_product_to_schema(row) if row else None

    # ---- Deals ----

    def create_deal(self, deal: Deal) -> Deal:
        row = DealTable(
            id=deal.id,
            product_id=deal.product_id,
            product_name=deal.product_name,
            product_url=deal.product_url,
            product_image=deal.product_image,
            current_price=deal.current_price,
            all_time_low=deal.all_time_low,
            discount_percent=deal.discount_percent,
            deal_type=deal.deal_type,
            rating=deal.rating,
            review_count=deal.review_count,
            detected_at=deal.detected_at,
            notified=deal.notified,
            expired=deal.expired,
        )
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return _deal_to_schema(row)

    def list_deals(self, include_expired: bool = False, limit: int = 50) -> List[Deal]:
        query = self.session.query(DealTable)
        if not include_expired:
            query = query.filter(DealTable.expired.is_(False))
        query = query.order_by(DealTable.detected_at.desc()).limit(limit)
        return [_deal_to_schema(row) for row in query.all()]

    def list_unnotified_deals(self) -> List[Deal]:
        rows = self.session.query(DealTable).filter(
            DealTable.notified.is_(False),
            DealTable.expired.is_(False),
        ).all()
        return [_deal_to_schema(row) for row in rows]

    def mark_deal_notified(self, deal_id: UUID) -> None:
        row = self.session.get(DealTable, str(deal_id))
        if row:
            row.notified = True
            self.session.commit()

    def expire_old_deals(self, hours: int = 24) -> int:
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        result = self.session.query(DealTable).filter(
            DealTable.detected_at < cutoff,
            DealTable.expired.is_(False),
        ).update({"expired": True})
        self.session.commit()
        return result

    # ---- Legacy Product CRUD ----

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

    # ---- Alert CRUD ----

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

    # ---- Pricing snapshots ----

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

    # ---- User preferences ----

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
