from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, HttpUrl, field_validator


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

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and not value.strip():
            raise ValueError("name must not be empty")
        return value


class PriceRecord(BaseModel):
    id: UUID
    product_id: UUID
    price: float
    collected_at: datetime
    source: str


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


def new_product(data: ProductCreate) -> Product:
    now = datetime.utcnow()
    return Product(
        id=uuid4(),
        name=data.name,
        url=data.url,
        current_price=data.current_price,
        desired_price=data.desired_price,
        created_at=now,
        updated_at=now,
    )


def new_alert(data: AlertCreate) -> Alert:
    return Alert(
        id=uuid4(),
        created_at=datetime.utcnow(),
        **data.model_dump(),
    )


def new_price_record(product_id: UUID, price: float, source: str) -> PriceRecord:
    return PriceRecord(
        id=uuid4(),
        product_id=product_id,
        price=price,
        source=source,
        collected_at=datetime.utcnow(),
    )


def new_price_snapshot(
    data: PriceSnapshotCreate,
    *,
    extreme_discount: bool = False,
    improbable_price: bool = False,
) -> PriceSnapshot:
    return PriceSnapshot(
        id=uuid4(),
        collected_at=datetime.utcnow(),
        extreme_discount=extreme_discount,
        improbable_price=improbable_price,
        **data.model_dump(),
    )
