from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from .database import InMemoryRepository, get_repository
from .models import (
    Alert,
    AlertCreate,
    AlertUpdate,
    Product,
    ProductCreate,
    ProductUpdate,
    WatchlistState,
)

router = APIRouter()


def get_repo() -> InMemoryRepository:
    return get_repository()


@router.get("/watchlist", response_model=WatchlistState)
def read_watchlist(repo: InMemoryRepository = Depends(get_repo)) -> WatchlistState:
    return WatchlistState(products=repo.list_products(), alerts=repo.list_alerts())


# Product endpoints
@router.post("/products", response_model=Product, status_code=status.HTTP_201_CREATED)
def create_product(
    payload: ProductCreate, repo: InMemoryRepository = Depends(get_repo)
) -> Product:
    return repo.create_product(payload)


@router.get("/products", response_model=list[Product])
def list_products(repo: InMemoryRepository = Depends(get_repo)) -> list[Product]:
    return repo.list_products()


@router.get("/products/{product_id}", response_model=Product)
def get_product(product_id: str, repo: InMemoryRepository = Depends(get_repo)) -> Product:
    product = repo.get_product(UUID(product_id))
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return product


@router.put("/products/{product_id}", response_model=Product)
@router.patch("/products/{product_id}", response_model=Product)
def update_product(
    product_id: str, payload: ProductUpdate, repo: InMemoryRepository = Depends(get_repo)
) -> Product:
    product = repo.update_product(UUID(product_id), payload)
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return product


@router.delete("/products/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(product_id: str, repo: InMemoryRepository = Depends(get_repo)) -> None:
    if not repo.delete_product(UUID(product_id)):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")


# Alert endpoints
@router.post("/alerts", response_model=Alert, status_code=status.HTTP_201_CREATED)
def create_alert(payload: AlertCreate, repo: InMemoryRepository = Depends(get_repo)) -> Alert:
    if not repo.get_product(payload.product_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return repo.create_alert(payload)


@router.get("/alerts", response_model=list[Alert])
def list_alerts(repo: InMemoryRepository = Depends(get_repo)) -> list[Alert]:
    return repo.list_alerts()


@router.put("/alerts/{alert_id}", response_model=Alert)
@router.patch("/alerts/{alert_id}", response_model=Alert)
def update_alert(alert_id: str, payload: AlertUpdate, repo: InMemoryRepository = Depends(get_repo)) -> Alert:
    alert = repo.update_alert(UUID(alert_id), payload)
    if not alert:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
    return alert


@router.delete("/alerts/{alert_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_alert(alert_id: str, repo: InMemoryRepository = Depends(get_repo)) -> None:
    if not repo.delete_alert(UUID(alert_id)):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
