from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from .database import SqlRepository, get_repository
from .models import (
    Alert,
    AlertCreate,
    AlertUpdate,
    PriceSnapshot,
    Product,
    ProductCreate,
    ProductUpdate,
    UserPreference,
    UserPreferenceCreate,
    UserPreferenceUpdate,
    WatchlistState,
)
from .services.notifications import NotificationService
from .services.pricing import PriceFetcher


class TestEmailResponse(BaseModel):
    success: bool
    message: str
    sent_at: datetime


class PriceFetchResponse(BaseModel):
    success: bool
    message: str
    snapshot: Optional[PriceSnapshot] = None

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


# Notification endpoints
@router.post("/notifications/test-email", response_model=TestEmailResponse)
def test_email(repo: SqlRepository = Depends(get_repo)) -> TestEmailResponse:
    """Send a test email to verify SMTP configuration."""
    notifier = NotificationService(repo)
    result = notifier.send_test_email()
    return TestEmailResponse(
        success=result.success,
        message=result.message,
        sent_at=result.sent_at,
    )


# Price fetch endpoints
@router.post("/products/{product_id}/fetch", response_model=PriceFetchResponse)
def fetch_product_price(product_id: str, repo: SqlRepository = Depends(get_repo)) -> PriceFetchResponse:
    """Manually trigger a price fetch for a specific product."""
    product = repo.get_product(UUID(product_id))
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    asin = PriceFetcher.extract_asin(str(product.url))
    if not asin:
        return PriceFetchResponse(
            success=False,
            message="Could not extract ASIN from product URL. Make sure it's a valid Amazon product URL.",
            snapshot=None,
        )

    try:
        with PriceFetcher(repo) as fetcher:
            snapshot = fetcher.fetch_and_store(asin, product.id)
            return PriceFetchResponse(
                success=True,
                message=f"Price fetched successfully. Current price: ${snapshot.current_price:.2f}" if snapshot.current_price else "Price fetched but no price found.",
                snapshot=snapshot,
            )
    except Exception as e:
        return PriceFetchResponse(
            success=False,
            message=f"Failed to fetch price: {str(e)}",
            snapshot=None,
        )


@router.get("/products/{product_id}/snapshots", response_model=list[PriceSnapshot])
def list_product_snapshots(product_id: str, repo: SqlRepository = Depends(get_repo)) -> list[PriceSnapshot]:
    """Get price history for a product."""
    product = repo.get_product(UUID(product_id))
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return repo.list_price_snapshots(UUID(product_id))


# Simple UI
@router.get("/", response_class=HTMLResponse)
def dashboard() -> str:
    return """
    <html>
        <head>
            <title>Price Tracker</title>
            <style>
                * { box-sizing: border-box; }
                body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 2rem; background: #f5f7fa; }
                h1 { color: #2c3e50; margin-bottom: 0.5rem; }
                h2 { color: #34495e; font-size: 1.2rem; margin-bottom: 1rem; border-bottom: 2px solid #3498db; padding-bottom: 0.5rem; }
                .container { max-width: 1200px; margin: 0 auto; }
                .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(350px, 1fr)); gap: 1.5rem; }
                .card { background: white; border-radius: 8px; padding: 1.5rem; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
                label { display: block; margin-top: 0.75rem; font-weight: 500; color: #555; font-size: 0.9rem; }
                input { padding: 0.5rem; width: 100%; border: 1px solid #ddd; border-radius: 4px; margin-top: 0.25rem; }
                input:focus { outline: none; border-color: #3498db; }
                button { margin-top: 1rem; padding: 0.6rem 1.2rem; background: #3498db; color: white; border: none; border-radius: 4px; cursor: pointer; font-weight: 500; }
                button:hover { background: #2980b9; }
                button.secondary { background: #95a5a6; }
                button.secondary:hover { background: #7f8c8d; }
                button.success { background: #27ae60; }
                button.success:hover { background: #219a52; }
                button.warning { background: #e67e22; }
                button.warning:hover { background: #d35400; }
                .btn-group { display: flex; gap: 0.5rem; flex-wrap: wrap; }
                pre { background: #2c3e50; color: #ecf0f1; padding: 1rem; border-radius: 4px; overflow-x: auto; font-size: 0.85rem; max-height: 400px; overflow-y: auto; }
                .status { padding: 0.75rem; border-radius: 4px; margin-top: 1rem; }
                .status.success { background: #d4edda; color: #155724; }
                .status.error { background: #f8d7da; color: #721c24; }
                .status.info { background: #d1ecf1; color: #0c5460; }
                .product-list { list-style: none; padding: 0; }
                .product-item { background: #f8f9fa; padding: 1rem; border-radius: 4px; margin-bottom: 0.75rem; }
                .product-item h4 { margin: 0 0 0.5rem 0; color: #2c3e50; }
                .product-item .price { font-size: 1.25rem; font-weight: bold; color: #27ae60; }
                .product-item .actions { margin-top: 0.75rem; }
                .product-item button { margin-top: 0; margin-right: 0.5rem; padding: 0.4rem 0.8rem; font-size: 0.85rem; }
                .small-text { font-size: 0.8rem; color: #7f8c8d; }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>Price Tracker Dashboard</h1>
                <p class="small-text">Track Amazon product prices and get notified when deals appear.</p>

                <div class="grid">
                    <div class="card">
                        <h2>Add Product</h2>
                        <label>Product Name <input id="p-name" placeholder="e.g., Sony WH-1000XM5" /></label>
                        <label>Amazon URL <input id="p-url" placeholder="https://amazon.com/dp/..." /></label>
                        <label>Target Price ($) <input id="p-price" type="number" step="0.01" placeholder="99.99" /></label>
                        <button onclick="createProduct()">Add Product</button>
                    </div>

                    <div class="card">
                        <h2>Create Price Alert</h2>
                        <label>Product ID <input id="a-product" placeholder="Select from products below" /></label>
                        <label>Alert When Price Below ($) <input id="a-threshold" type="number" step="0.01" placeholder="50.00" /></label>
                        <label>Notification Channel <input id="a-channel" placeholder="email, webhook, or slack" /></label>
                        <button onclick="createAlert()">Create Alert</button>
                    </div>

                    <div class="card">
                        <h2>Email Notification Settings</h2>
                        <label>Notification Email <input id="pref-email" type="email" placeholder="you@example.com" /></label>
                        <label>SMTP Host <input id="pref-smtp" placeholder="smtp.gmail.com" /></label>
                        <label>SMTP Username <input id="pref-user" placeholder="your-email@gmail.com" /></label>
                        <label>SMTP Password <input id="pref-pass" type="password" placeholder="App password" /></label>
                        <label>Webhook URL (optional) <input id="pref-webhook" placeholder="https://..." /></label>
                        <label>Slack Webhook (optional) <input id="pref-slack" placeholder="https://hooks.slack.com/..." /></label>
                        <div class="btn-group">
                            <button onclick="savePrefs()">Save Settings</button>
                            <button class="success" onclick="testEmail()">Send Test Email</button>
                        </div>
                        <div id="email-status"></div>
                    </div>

                    <div class="card">
                        <h2>Tracked Products</h2>
                        <ul id="products-list" class="product-list">
                            <li class="small-text">Loading...</li>
                        </ul>
                    </div>
                </div>

                <div class="card" style="margin-top: 1.5rem;">
                    <h2>Watchlist Data</h2>
                    <div class="btn-group">
                        <button onclick="refresh()">Refresh</button>
                        <button class="secondary" onclick="loadPrefs()">Reload Settings</button>
                    </div>
                    <pre id="output">Loading...</pre>
                </div>
            </div>

            <script>
                async function createProduct() {
                    const res = await fetch('/api/products', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            name: document.getElementById('p-name').value,
                            url: document.getElementById('p-url').value,
                            desired_price: parseFloat(document.getElementById('p-price').value) || null,
                        })
                    });
                    if (res.ok) {
                        document.getElementById('p-name').value = '';
                        document.getElementById('p-url').value = '';
                        document.getElementById('p-price').value = '';
                    }
                    refresh();
                }

                async function createAlert() {
                    const res = await fetch('/api/alerts', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            product_id: document.getElementById('a-product').value,
                            threshold_price: parseFloat(document.getElementById('a-threshold').value),
                            channel: document.getElementById('a-channel').value || null,
                        })
                    });
                    if (res.ok) {
                        document.getElementById('a-product').value = '';
                        document.getElementById('a-threshold').value = '';
                        document.getElementById('a-channel').value = '';
                    }
                    refresh();
                }

                async function savePrefs() {
                    const res = await fetch('/api/preferences', {
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
                    const statusEl = document.getElementById('email-status');
                    if (res.ok) {
                        statusEl.innerHTML = '<div class="status success">Settings saved successfully!</div>';
                    } else {
                        statusEl.innerHTML = '<div class="status error">Failed to save settings.</div>';
                    }
                    setTimeout(() => statusEl.innerHTML = '', 3000);
                }

                async function testEmail() {
                    const statusEl = document.getElementById('email-status');
                    statusEl.innerHTML = '<div class="status info">Sending test email...</div>';

                    const res = await fetch('/api/notifications/test-email', { method: 'POST' });
                    const data = await res.json();

                    if (data.success) {
                        statusEl.innerHTML = '<div class="status success">' + data.message + '</div>';
                    } else {
                        statusEl.innerHTML = '<div class="status error">' + data.message + '</div>';
                    }
                }

                async function fetchPrice(productId) {
                    const btn = event.target;
                    btn.disabled = true;
                    btn.textContent = 'Fetching...';

                    const res = await fetch('/api/products/' + productId + '/fetch', { method: 'POST' });
                    const data = await res.json();

                    btn.disabled = false;
                    btn.textContent = 'Fetch Price';

                    if (data.success) {
                        alert(data.message);
                    } else {
                        alert('Error: ' + data.message);
                    }
                    refresh();
                }

                async function deleteProduct(productId) {
                    if (!confirm('Delete this product and all its alerts?')) return;
                    await fetch('/api/products/' + productId, { method: 'DELETE' });
                    refresh();
                }

                async function loadPrefs() {
                    const res = await fetch('/api/preferences');
                    if (res.ok) {
                        const data = await res.json();
                        if (data) {
                            document.getElementById('pref-email').value = data.email || '';
                            document.getElementById('pref-smtp').value = data.smtp_host || '';
                            document.getElementById('pref-user').value = data.smtp_username || '';
                            document.getElementById('pref-webhook').value = data.webhook_url || '';
                            document.getElementById('pref-slack').value = data.slack_webhook_url || '';
                        }
                    }
                }

                async function refresh() {
                    const res = await fetch('/api/watchlist');
                    const data = await res.json();
                    document.getElementById('output').textContent = JSON.stringify(data, null, 2);

                    // Update products list
                    const listEl = document.getElementById('products-list');
                    if (data.products && data.products.length > 0) {
                        listEl.innerHTML = data.products.map(p => `
                            <li class="product-item">
                                <h4>${p.name}</h4>
                                <div class="price">${p.current_price ? '$' + p.current_price.toFixed(2) : 'No price yet'}</div>
                                <div class="small-text">ID: ${p.id}</div>
                                <div class="small-text">Target: ${p.desired_price ? '$' + p.desired_price.toFixed(2) : 'Not set'}</div>
                                <div class="actions">
                                    <button class="warning" onclick="fetchPrice('${p.id}')">Fetch Price</button>
                                    <button class="secondary" onclick="deleteProduct('${p.id}')">Delete</button>
                                    <button class="secondary" onclick="document.getElementById('a-product').value='${p.id}'">Create Alert</button>
                                </div>
                            </li>
                        `).join('');
                    } else {
                        listEl.innerHTML = '<li class="small-text">No products tracked yet. Add one above!</li>';
                    }
                }

                // Initial load
                refresh();
                loadPrefs();
            </script>
        </body>
    </html>
    """
