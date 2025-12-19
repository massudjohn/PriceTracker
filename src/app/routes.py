from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse

from .database import SqlRepository, get_repository
from .models import (
    Alert,
    AlertCreate,
    AlertUpdate,
    Product,
    ProductCreate,
    ProductUpdate,
    UserPreference,
    UserPreferenceCreate,
    UserPreferenceUpdate,
    WatchlistState,
)

router = APIRouter()


def get_repo():
    repo = get_repository()
    try:
        yield repo
    finally:
        repo.close()


@router.get("/watchlist", response_model=WatchlistState)
def read_watchlist(repo: SqlRepository = Depends(get_repo)) -> WatchlistState:
    return WatchlistState(products=repo.list_products(), alerts=repo.list_alerts())


# Product endpoints
@router.post("/products", response_model=Product, status_code=status.HTTP_201_CREATED)
def create_product(payload: ProductCreate, repo: SqlRepository = Depends(get_repo)) -> Product:
    return repo.create_product(payload)


@router.get("/products", response_model=list[Product])
def list_products(repo: SqlRepository = Depends(get_repo)) -> list[Product]:
    return repo.list_products()


@router.get("/products/{product_id}", response_model=Product)
def get_product(product_id: str, repo: SqlRepository = Depends(get_repo)) -> Product:
    product = repo.get_product(UUID(product_id))
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return product


@router.put("/products/{product_id}", response_model=Product)
@router.patch("/products/{product_id}", response_model=Product)
def update_product(product_id: str, payload: ProductUpdate, repo: SqlRepository = Depends(get_repo)) -> Product:
    product = repo.update_product(UUID(product_id), payload)
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return product


@router.delete("/products/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(product_id: str, repo: SqlRepository = Depends(get_repo)) -> None:
    if not repo.delete_product(UUID(product_id)):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")


# Alert endpoints
@router.post("/alerts", response_model=Alert, status_code=status.HTTP_201_CREATED)
def create_alert(payload: AlertCreate, repo: SqlRepository = Depends(get_repo)) -> Alert:
    if not repo.get_product(payload.product_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return repo.create_alert(payload)


@router.get("/alerts", response_model=list[Alert])
def list_alerts(repo: SqlRepository = Depends(get_repo)) -> list[Alert]:
    return repo.list_alerts()


@router.put("/alerts/{alert_id}", response_model=Alert)
@router.patch("/alerts/{alert_id}", response_model=Alert)
def update_alert(alert_id: str, payload: AlertUpdate, repo: SqlRepository = Depends(get_repo)) -> Alert:
    alert = repo.update_alert(UUID(alert_id), payload)
    if not alert:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
    return alert


@router.delete("/alerts/{alert_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_alert(alert_id: str, repo: SqlRepository = Depends(get_repo)) -> None:
    if not repo.delete_alert(UUID(alert_id)):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")


# Preferences
@router.get("/preferences", response_model=UserPreference | None)
def get_preferences(repo: SqlRepository = Depends(get_repo)) -> UserPreference | None:
    return repo.get_preferences()


@router.put("/preferences", response_model=UserPreference)
def upsert_preferences(
    payload: UserPreferenceCreate | UserPreferenceUpdate, repo: SqlRepository = Depends(get_repo)
) -> UserPreference:
    return repo.upsert_preferences(payload)


# Simple UI
@router.get("/", response_class=HTMLResponse)
def dashboard() -> str:
    return """
    <html>
        <head>
            <title>Price Tracker</title>
            <style>
                body { font-family: Arial, sans-serif; margin: 2rem; }
                section { margin-bottom: 1.5rem; }
                label { display: block; margin-top: 0.5rem; }
                input { padding: 0.4rem; width: 320px; }
                button { margin-top: 0.6rem; padding: 0.5rem 1rem; }
                pre { background: #f5f5f5; padding: 1rem; }
            </style>
        </head>
        <body>
            <h1>Price Tracker</h1>
            <section>
                <h2>Add Product</h2>
                <label>Name <input id="p-name" /></label>
                <label>URL <input id="p-url" /></label>
                <label>Desired Price <input id="p-price" type="number" step="0.01" /></label>
                <button onclick="createProduct()">Save</button>
            </section>
            <section>
                <h2>Create Alert</h2>
                <label>Product ID <input id="a-product" /></label>
                <label>Threshold <input id="a-threshold" type="number" step="0.01" /></label>
                <label>Channel (email|webhook|slack) <input id="a-channel" /></label>
                <button onclick="createAlert()">Save</button>
            </section>
            <section>
                <h2>Preferences</h2>
                <label>Email <input id="pref-email" /></label>
                <label>SMTP host <input id="pref-smtp" /></label>
                <label>SMTP username <input id="pref-user" /></label>
                <label>SMTP password <input id="pref-pass" type="password" /></label>
                <label>Webhook URL <input id="pref-webhook" /></label>
                <label>Slack webhook <input id="pref-slack" /></label>
                <button onclick="savePrefs()">Update</button>
            </section>
            <section>
                <h2>Recent Alerts</h2>
                <button onclick="refresh()">Refresh Watchlist</button>
                <pre id="output"></pre>
            </section>
            <script>
                async function createProduct() {
                    await fetch('/api/products', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            name: document.getElementById('p-name').value,
                            url: document.getElementById('p-url').value,
                            desired_price: parseFloat(document.getElementById('p-price').value) || null,
                        })
                    });
                    refresh();
                }
                async function createAlert() {
                    await fetch('/api/alerts', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            product_id: document.getElementById('a-product').value,
                            threshold_price: parseFloat(document.getElementById('a-threshold').value),
                            channel: document.getElementById('a-channel').value || null,
                        })
                    });
                    refresh();
                }
                async function savePrefs() {
                    await fetch('/api/preferences', {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            email: document.getElementById('pref-email').value || null,
                            smtp_host: document.getElementById('pref-smtp').value || null,
                            smtp_username: document.getElementById('pref-user').value || null,
                            smtp_password: document.getElementById('pref-pass').value || null,
                            webhook_url: document.getElementById('pref-webhook').value || null,
                            slack_webhook_url: document.getElementById('pref-slack').value || null,
                        })
                    });
                    refresh();
                }
                async function refresh() {
                    const res = await fetch('/api/watchlist');
                    const data = await res.json();
                    document.getElementById('output').textContent = JSON.stringify(data, null, 2);
                }
                refresh();
            </script>
        </body>
    </html>
    """
