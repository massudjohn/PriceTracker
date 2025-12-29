from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from .database import SqlRepository, get_repository
from .models import (
    Category,
    CategoryCreate,
    CategoryUpdate,
    Deal,
    DealFeed,
    ScanResult,
    UserPreference,
    UserPreferenceCreate,
    UserPreferenceUpdate,
)
from .services.deal_detector import DealDetector
from .services.notifications import NotificationService


class TestEmailResponse(BaseModel):
    success: bool
    message: str
    sent_at: datetime


class ScanCategoryResponse(BaseModel):
    success: bool
    message: str
    result: Optional[ScanResult] = None


router = APIRouter()


def get_repo():
    repo = get_repository()
    try:
        yield repo
    finally:
        repo.close()


# ============ Category Endpoints ============

@router.post("/categories", response_model=Category, status_code=status.HTTP_201_CREATED)
def create_category(payload: CategoryCreate, repo: SqlRepository = Depends(get_repo)) -> Category:
    """Add a new category to monitor for deals."""
    return repo.create_category(payload)


@router.get("/categories", response_model=list[Category])
def list_categories(active_only: bool = False, repo: SqlRepository = Depends(get_repo)) -> list[Category]:
    """List all monitored categories."""
    return repo.list_categories(active_only=active_only)


@router.get("/categories/{category_id}", response_model=Category)
def get_category(category_id: str, repo: SqlRepository = Depends(get_repo)) -> Category:
    """Get a specific category."""
    category = repo.get_category(UUID(category_id))
    if not category:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
    return category


@router.put("/categories/{category_id}", response_model=Category)
@router.patch("/categories/{category_id}", response_model=Category)
def update_category(category_id: str, payload: CategoryUpdate, repo: SqlRepository = Depends(get_repo)) -> Category:
    """Update a category's settings."""
    category = repo.update_category(UUID(category_id), payload)
    if not category:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
    return category


@router.delete("/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(category_id: str, repo: SqlRepository = Depends(get_repo)) -> None:
    """Delete a category."""
    if not repo.delete_category(UUID(category_id)):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")


@router.post("/categories/{category_id}/scan", response_model=ScanCategoryResponse)
def scan_category(category_id: str, repo: SqlRepository = Depends(get_repo)) -> ScanCategoryResponse:
    """Manually trigger a scan of a category for deals."""
    import time

    category = repo.get_category(UUID(category_id))
    if not category:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")

    start_time = time.time()
    products_found = 0
    deals_found = 0

    def on_product_found(product):
        nonlocal products_found
        products_found += 1
        repo.upsert_discovered_product(product)

    def on_deal_found(deal):
        nonlocal deals_found
        deals_found += 1
        repo.create_deal(deal)
        # Send instant notification
        prefs = repo.get_preferences()
        if prefs and prefs.instant_notifications and prefs.email:
            notifier = NotificationService(repo)
            notifier.send_deal_notification(deal)
            repo.mark_deal_notified(deal.id)

    try:
        with DealDetector() as detector:
            detector.scan_category(
                category,
                on_product_found=on_product_found,
                on_deal_found=on_deal_found,
            )

        repo.update_category_scan_time(category.id, products_found)
        elapsed = time.time() - start_time

        return ScanCategoryResponse(
            success=True,
            message=f"Scan complete: {products_found} products, {deals_found} deals found",
            result=ScanResult(
                category_id=category.id,
                category_name=category.name,
                products_found=products_found,
                deals_found=deals_found,
                scan_duration_seconds=elapsed,
            ),
        )
    except Exception as e:
        return ScanCategoryResponse(
            success=False,
            message=f"Scan failed: {str(e)}",
            result=None,
        )


# ============ Deal Endpoints ============

@router.get("/deals", response_model=DealFeed)
def list_deals(include_expired: bool = False, limit: int = 50, repo: SqlRepository = Depends(get_repo)) -> DealFeed:
    """Get the deal feed."""
    deals = repo.list_deals(include_expired=include_expired, limit=limit)
    categories = repo.list_categories(active_only=True)
    return DealFeed(
        deals=deals,
        total_count=len(deals),
        categories_monitored=len(categories),
    )


@router.post("/deals/expire-old", response_model=dict)
def expire_old_deals(hours: int = 24, repo: SqlRepository = Depends(get_repo)) -> dict:
    """Mark old deals as expired."""
    count = repo.expire_old_deals(hours=hours)
    return {"expired_count": count}


# ============ Preferences Endpoints ============

@router.get("/preferences", response_model=UserPreference | None)
def get_preferences(repo: SqlRepository = Depends(get_repo)) -> UserPreference | None:
    return repo.get_preferences()


@router.put("/preferences", response_model=UserPreference)
def upsert_preferences(
    payload: UserPreferenceCreate | UserPreferenceUpdate, repo: SqlRepository = Depends(get_repo)
) -> UserPreference:
    return repo.upsert_preferences(payload)


# ============ Notification Endpoints ============

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


# ============ Dashboard UI ============

@router.get("/", response_class=HTMLResponse)
def dashboard() -> str:
    return """
    <html>
        <head>
            <title>Deal Hunter</title>
            <style>
                * { box-sizing: border-box; margin: 0; padding: 0; }
                body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #e2e8f0; min-height: 100vh; }
                .container { max-width: 1400px; margin: 0 auto; padding: 2rem; }
                h1 { font-size: 2rem; margin-bottom: 0.5rem; color: #38bdf8; }
                h2 { font-size: 1.25rem; margin-bottom: 1rem; color: #94a3b8; font-weight: 500; }
                .subtitle { color: #64748b; margin-bottom: 2rem; }
                .grid { display: grid; grid-template-columns: 350px 1fr; gap: 2rem; }
                .sidebar { display: flex; flex-direction: column; gap: 1.5rem; }
                .card { background: #1e293b; border-radius: 12px; padding: 1.5rem; border: 1px solid #334155; }
                .card h3 { font-size: 1rem; color: #f1f5f9; margin-bottom: 1rem; display: flex; align-items: center; gap: 0.5rem; }
                label { display: block; margin-bottom: 0.5rem; font-size: 0.875rem; color: #94a3b8; }
                input, select { width: 100%; padding: 0.625rem; background: #0f172a; border: 1px solid #334155; border-radius: 6px; color: #e2e8f0; margin-bottom: 0.75rem; }
                input:focus, select:focus { outline: none; border-color: #38bdf8; }
                button { padding: 0.625rem 1.25rem; border: none; border-radius: 6px; cursor: pointer; font-weight: 500; transition: all 0.2s; }
                .btn-primary { background: #0ea5e9; color: white; }
                .btn-primary:hover { background: #0284c7; }
                .btn-success { background: #22c55e; color: white; }
                .btn-success:hover { background: #16a34a; }
                .btn-warning { background: #f59e0b; color: black; }
                .btn-warning:hover { background: #d97706; }
                .btn-danger { background: #ef4444; color: white; }
                .btn-danger:hover { background: #dc2626; }
                .btn-secondary { background: #334155; color: #e2e8f0; }
                .btn-secondary:hover { background: #475569; }
                .btn-group { display: flex; gap: 0.5rem; flex-wrap: wrap; margin-top: 0.5rem; }
                .deal-grid { display: grid; gap: 1rem; }
                .deal-card { background: #1e293b; border-radius: 12px; padding: 1.25rem; border: 1px solid #334155; display: grid; grid-template-columns: 100px 1fr auto; gap: 1rem; align-items: center; transition: border-color 0.2s; }
                .deal-card:hover { border-color: #38bdf8; }
                .deal-card.price-error { border-color: #f59e0b; }
                .deal-card.all-time-low { border-color: #22c55e; }
                .deal-img { width: 100px; height: 100px; object-fit: contain; background: white; border-radius: 8px; }
                .deal-info h4 { font-size: 1rem; color: #f1f5f9; margin-bottom: 0.5rem; line-height: 1.4; }
                .deal-info h4 a { color: inherit; text-decoration: none; }
                .deal-info h4 a:hover { color: #38bdf8; }
                .deal-meta { font-size: 0.875rem; color: #64748b; display: flex; gap: 1rem; flex-wrap: wrap; }
                .deal-price { text-align: right; }
                .current-price { font-size: 1.5rem; font-weight: bold; color: #22c55e; }
                .old-price { font-size: 0.875rem; color: #64748b; text-decoration: line-through; }
                .discount-badge { display: inline-block; background: #22c55e; color: black; padding: 0.25rem 0.5rem; border-radius: 4px; font-weight: bold; font-size: 0.875rem; margin-top: 0.5rem; }
                .discount-badge.warning { background: #f59e0b; }
                .category-item { background: #0f172a; padding: 1rem; border-radius: 8px; margin-bottom: 0.75rem; }
                .category-item h4 { color: #f1f5f9; margin-bottom: 0.5rem; }
                .category-meta { font-size: 0.875rem; color: #64748b; }
                .status { padding: 0.75rem; border-radius: 6px; margin-top: 1rem; font-size: 0.875rem; }
                .status.success { background: rgba(34, 197, 94, 0.2); color: #22c55e; }
                .status.error { background: rgba(239, 68, 68, 0.2); color: #ef4444; }
                .status.info { background: rgba(14, 165, 233, 0.2); color: #38bdf8; }
                .empty-state { text-align: center; padding: 3rem; color: #64748b; }
                .stats { display: flex; gap: 2rem; margin-bottom: 1.5rem; }
                .stat { text-align: center; }
                .stat-value { font-size: 2rem; font-weight: bold; color: #38bdf8; }
                .stat-label { font-size: 0.875rem; color: #64748b; }
                @media (max-width: 900px) { .grid { grid-template-columns: 1fr; } }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>Deal Hunter</h1>
                <p class="subtitle">Automatic deal detection with 50%+ off all-time low alerts</p>

                <div class="stats">
                    <div class="stat">
                        <div class="stat-value" id="stat-deals">0</div>
                        <div class="stat-label">Active Deals</div>
                    </div>
                    <div class="stat">
                        <div class="stat-value" id="stat-categories">0</div>
                        <div class="stat-label">Categories Monitored</div>
                    </div>
                </div>

                <div class="grid">
                    <div class="sidebar">
                        <div class="card">
                            <h3>Search for Products to Monitor</h3>
                            <label>What are you looking for?</label>
                            <input id="cat-search" placeholder="e.g., wireless headphones, mechanical keyboard" />
                            <label>Max Price (optional)</label>
                            <input id="cat-maxprice" type="number" step="0.01" placeholder="Leave empty for no limit" />
                            <label>Min Reviews</label>
                            <input id="cat-reviews" type="number" value="100" />
                            <label>Min Rating</label>
                            <input id="cat-rating" type="number" step="0.1" value="4.0" />
                            <label>Min Discount % (below all-time low)</label>
                            <input id="cat-discount" type="number" value="50" />
                            <button class="btn-primary" onclick="addCategory()">Start Monitoring</button>
                            <p style="margin-top: 0.75rem; font-size: 0.8rem; color: #64748b;">
                                Or paste an Amazon URL directly:
                            </p>
                            <input id="cat-url" placeholder="https://amazon.com/s?k=..." style="font-size: 0.85rem;" />
                        </div>

                        <div class="card">
                            <h3>Monitored Categories</h3>
                            <div id="categories-list">
                                <div class="empty-state">No categories yet</div>
                            </div>
                        </div>

                        <div class="card">
                            <h3>Email Notifications</h3>
                            <label>Email Address</label>
                            <input id="pref-email" type="email" placeholder="you@example.com" />
                            <label>SMTP Host</label>
                            <input id="pref-smtp" placeholder="smtp.gmail.com" />
                            <label>SMTP Username</label>
                            <input id="pref-user" placeholder="your-email@gmail.com" />
                            <label>SMTP Password</label>
                            <input id="pref-pass" type="password" placeholder="App password" />
                            <div class="btn-group">
                                <button class="btn-primary" onclick="savePrefs()">Save</button>
                                <button class="btn-success" onclick="testEmail()">Test Email</button>
                            </div>
                            <div id="email-status"></div>
                        </div>
                    </div>

                    <div class="main">
                        <div class="card">
                            <h3>Deal Feed</h3>
                            <div class="btn-group" style="margin-bottom: 1rem;">
                                <button class="btn-primary" onclick="refreshDeals()">Refresh Deals</button>
                                <button class="btn-warning" onclick="scanAllCategories()">Scan All Categories</button>
                            </div>
                            <div id="deals-list" class="deal-grid">
                                <div class="empty-state">No deals found yet. Add a category and scan for deals!</div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <script>
                async function addCategory() {
                    const search = document.getElementById('cat-search').value.trim();
                    const directUrl = document.getElementById('cat-url').value.trim();
                    const maxPrice = parseFloat(document.getElementById('cat-maxprice').value) || null;

                    let url, name;

                    if (directUrl) {
                        // Use direct URL if provided
                        url = directUrl;
                        name = search || 'Custom Search';
                    } else if (search) {
                        // Build Amazon search URL from search term
                        const encodedSearch = encodeURIComponent(search);
                        url = `https://www.amazon.com/s?k=${encodedSearch}`;
                        name = search;
                    } else {
                        alert('Please enter a search term or paste an Amazon URL');
                        return;
                    }

                    const res = await fetch('/api/categories', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            name: name,
                            url: url,
                            max_price: maxPrice,
                            min_reviews: parseInt(document.getElementById('cat-reviews').value) || 100,
                            min_rating: parseFloat(document.getElementById('cat-rating').value) || 4.0,
                            min_discount_percent: parseFloat(document.getElementById('cat-discount').value) || 50,
                        })
                    });
                    if (res.ok) {
                        document.getElementById('cat-search').value = '';
                        document.getElementById('cat-url').value = '';
                        document.getElementById('cat-maxprice').value = '';
                        refreshCategories();
                        // Optionally auto-scan the new category
                        const category = await res.json();
                        if (confirm('Category added! Would you like to scan for deals now?')) {
                            await fetch('/api/categories/' + category.id + '/scan', { method: 'POST' });
                            refreshDeals();
                            refreshCategories();
                        }
                    } else {
                        alert('Failed to add category. Check the URL is valid.');
                    }
                }

                async function deleteCategory(id) {
                    if (!confirm('Delete this category?')) return;
                    await fetch('/api/categories/' + id, { method: 'DELETE' });
                    refreshCategories();
                }

                async function scanCategory(id, btn) {
                    btn.disabled = true;
                    btn.textContent = 'Scanning...';
                    const res = await fetch('/api/categories/' + id + '/scan', { method: 'POST' });
                    const data = await res.json();
                    btn.disabled = false;
                    btn.textContent = 'Scan';
                    if (data.success) {
                        alert(data.message);
                        refreshDeals();
                        refreshCategories();
                    } else {
                        alert('Error: ' + data.message);
                    }
                }

                async function scanAllCategories() {
                    const res = await fetch('/api/categories');
                    const categories = await res.json();
                    for (const cat of categories) {
                        if (cat.active) {
                            await fetch('/api/categories/' + cat.id + '/scan', { method: 'POST' });
                        }
                    }
                    refreshDeals();
                    refreshCategories();
                }

                async function refreshCategories() {
                    const res = await fetch('/api/categories');
                    const categories = await res.json();
                    document.getElementById('stat-categories').textContent = categories.length;
                    const container = document.getElementById('categories-list');
                    if (categories.length === 0) {
                        container.innerHTML = '<div class="empty-state">No categories yet</div>';
                        return;
                    }
                    container.innerHTML = categories.map(c => `
                        <div class="category-item">
                            <h4>${c.name}</h4>
                            <div class="category-meta">
                                ${c.product_count} products | ${c.min_discount_percent}% off ATL
                                ${c.max_price ? ` | Max $${c.max_price}` : ''}<br>
                                ${c.min_reviews}+ reviews | ${c.min_rating}+ rating<br>
                                Last scan: ${c.last_scanned_at ? new Date(c.last_scanned_at).toLocaleString() : 'Never'}
                            </div>
                            <div class="btn-group">
                                <button class="btn-warning" onclick="scanCategory('${c.id}', this)">Scan</button>
                                <button class="btn-danger" onclick="deleteCategory('${c.id}')">Delete</button>
                            </div>
                        </div>
                    `).join('');
                }

                async function refreshDeals() {
                    const res = await fetch('/api/deals');
                    const data = await res.json();
                    document.getElementById('stat-deals').textContent = data.total_count;
                    const container = document.getElementById('deals-list');
                    if (data.deals.length === 0) {
                        container.innerHTML = '<div class="empty-state">No deals found yet. Add a category and scan for deals!</div>';
                        return;
                    }
                    container.innerHTML = data.deals.map(d => `
                        <div class="deal-card ${d.deal_type}">
                            <img class="deal-img" src="${d.product_image || 'https://via.placeholder.com/100?text=No+Image'}" alt="" />
                            <div class="deal-info">
                                <h4><a href="${d.product_url}" target="_blank">${d.product_name.substring(0, 100)}${d.product_name.length > 100 ? '...' : ''}</a></h4>
                                <div class="deal-meta">
                                    ${d.rating ? `<span>Rating: ${d.rating.toFixed(1)}</span>` : ''}
                                    ${d.review_count ? `<span>${d.review_count.toLocaleString()} reviews</span>` : ''}
                                    <span>${d.deal_type.replace('_', ' ')}</span>
                                </div>
                            </div>
                            <div class="deal-price">
                                <div class="current-price">$${d.current_price.toFixed(2)}</div>
                                <div class="old-price">ATL: $${d.all_time_low.toFixed(2)}</div>
                                <div class="discount-badge ${d.deal_type === 'price_error' ? 'warning' : ''}">${d.discount_percent.toFixed(0)}% below ATL</div>
                            </div>
                        </div>
                    `).join('');
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
                            instant_notifications: true,
                        })
                    });
                    const statusEl = document.getElementById('email-status');
                    statusEl.innerHTML = res.ok
                        ? '<div class="status success">Settings saved!</div>'
                        : '<div class="status error">Failed to save settings.</div>';
                    setTimeout(() => statusEl.innerHTML = '', 3000);
                }

                async function testEmail() {
                    const statusEl = document.getElementById('email-status');
                    statusEl.innerHTML = '<div class="status info">Sending test email...</div>';
                    const res = await fetch('/api/notifications/test-email', { method: 'POST' });
                    const data = await res.json();
                    statusEl.innerHTML = data.success
                        ? '<div class="status success">' + data.message + '</div>'
                        : '<div class="status error">' + data.message + '</div>';
                }

                async function loadPrefs() {
                    const res = await fetch('/api/preferences');
                    if (res.ok) {
                        const data = await res.json();
                        if (data) {
                            document.getElementById('pref-email').value = data.email || '';
                            document.getElementById('pref-smtp').value = data.smtp_host || '';
                            document.getElementById('pref-user').value = data.smtp_username || '';
                        }
                    }
                }

                // Initial load
                refreshCategories();
                refreshDeals();
                loadPrefs();
            </script>
        </body>
    </html>
    """
