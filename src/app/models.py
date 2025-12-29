from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, HttpUrl, field_validator


# ============ Category Models ============

class CategoryBase(BaseModel):
    name: str
    url: HttpUrl
    min_reviews: int = 100
    min_rating: float = 4.0
    max_price: Optional[float] = None
    min_discount_percent: float = 50.0  # Alert when price is X% below all-time low
    active: bool = True

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("name must not be empty")
        return value


class Category(CategoryBase):
    id: UUID
    created_at: datetime
    updated_at: datetime
    last_scanned_at: Optional[datetime] = None
    product_count: int = 0


class CategoryCreate(CategoryBase):
    pass


class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    url: Optional[HttpUrl] = None
    min_reviews: Optional[int] = None
    min_rating: Optional[float] = None
    max_price: Optional[float] = None
    min_discount_percent: Optional[float] = None
    active: Optional[bool] = None


# ============ Discovered Product Models ============

class DiscoveredProductBase(BaseModel):
    asin: str
    name: str
    url: HttpUrl
    current_price: Optional[float] = None
    list_price: Optional[float] = None
    rating: Optional[float] = None
    review_count: Optional[int] = None
    sales_rank: Optional[int] = None
    category_id: UUID
    image_url: Optional[str] = None


class DiscoveredProduct(DiscoveredProductBase):
    id: UUID
    all_time_low: Optional[float] = None
    all_time_high: Optional[float] = None
    created_at: datetime
    updated_at: datetime
    last_price_check: Optional[datetime] = None


class DiscoveredProductCreate(DiscoveredProductBase):
    pass


# ============ Deal Models ============

class DealBase(BaseModel):
    product_id: UUID
    current_price: float
    all_time_low: float
    discount_percent: float
    deal_type: str  # "all_time_low", "price_error", "extreme_discount"


class Deal(DealBase):
    id: UUID
    product_name: str
    product_url: str
    product_image: Optional[str] = None
    rating: Optional[float] = None
    review_count: Optional[int] = None
    detected_at: datetime
    notified: bool = False
    expired: bool = False


class DealCreate(DealBase):
    product_name: str
    product_url: str
    product_image: Optional[str] = None
    rating: Optional[float] = None
    review_count: Optional[int] = None


# ============ Price History Models ============

class PriceHistoryPoint(BaseModel):
    price: float
    date: datetime


class ProductPriceHistory(BaseModel):
    asin: str
    all_time_low: Optional[float] = None
    all_time_high: Optional[float] = None
    average_price: Optional[float] = None
    history: list[PriceHistoryPoint] = []


# ============ User Preference Models ============

class UserPreference(BaseModel):
    id: UUID
    email: Optional[str] = None
    smtp_host: Optional[str] = None
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None
    webhook_url: Optional[HttpUrl] = None
    slack_webhook_url: Optional[HttpUrl] = None
    instant_notifications: bool = True  # Send immediately for hot deals
    daily_digest: bool = False  # Also send daily summary
    created_at: datetime
    updated_at: datetime


class UserPreferenceCreate(BaseModel):
    email: Optional[str] = None
    smtp_host: Optional[str] = None
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None
    webhook_url: Optional[HttpUrl] = None
    slack_webhook_url: Optional[HttpUrl] = None
    instant_notifications: bool = True
    daily_digest: bool = False


class UserPreferenceUpdate(BaseModel):
    email: Optional[str] = None
    smtp_host: Optional[str] = None
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None
    webhook_url: Optional[HttpUrl] = None
    slack_webhook_url: Optional[HttpUrl] = None
    instant_notifications: Optional[bool] = None
    daily_digest: Optional[bool] = None


# ============ API Response Models ============

class DealFeed(BaseModel):
    deals: list[Deal]
    total_count: int
    categories_monitored: int


class ScanResult(BaseModel):
    category_id: UUID
    category_name: str
    products_found: int
    deals_found: int
    scan_duration_seconds: float


# ============ Legacy Models (keeping for compatibility) ============

class ProductBase(BaseModel):
    name: str
    url: HttpUrl
    desired_price: Optional[float] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("name must not be empty")
        return value


class Product(ProductBase):
    id: UUID
    current_price: Optional[float] = None
    created_at: datetime
    updated_at: datetime


class ProductCreate(ProductBase):
    current_price: Optional[float] = None


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    url: Optional[HttpUrl] = None
    desired_price: Optional[float] = None
    current_price: Optional[float] = None


class PriceSnapshot(BaseModel):
    id: UUID
    product_id: UUID
    current_price: Optional[float]
    list_price: Optional[float]
    availability: Optional[str]
    collected_at: datetime
    source: str
    extreme_discount: bool = False
    improbable_price: bool = False


class PriceSnapshotCreate(BaseModel):
    product_id: UUID
    current_price: Optional[float]
    list_price: Optional[float]
    availability: Optional[str]
    source: str = "amazon"


class AlertBase(BaseModel):
    product_id: UUID
    threshold_price: float
    active: bool = True
    channel: Optional[str] = None


class Alert(AlertBase):
    id: UUID
    created_at: datetime


class AlertCreate(AlertBase):
    pass


class AlertUpdate(BaseModel):
    threshold_price: Optional[float] = None
    active: Optional[bool] = None
    channel: Optional[str] = None


class WatchlistState(BaseModel):
    products: list[Product]
    alerts: list[Alert]


# ============ Factory Functions ============

def new_category(data: CategoryCreate) -> Category:
    now = datetime.utcnow()
    return Category(
        id=uuid4(),
        created_at=now,
        updated_at=now,
        **data.model_dump(),
    )


def new_discovered_product(data: DiscoveredProductCreate) -> DiscoveredProduct:
    now = datetime.utcnow()
    return DiscoveredProduct(
        id=uuid4(),
        created_at=now,
        updated_at=now,
        **data.model_dump(),
    )


def new_deal(data: DealCreate) -> Deal:
    return Deal(
        id=uuid4(),
        detected_at=datetime.utcnow(),
        **data.model_dump(),
    )
