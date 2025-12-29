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
                .subtitle { color: #64748b; margin-bottom: 2rem; }
                .tabs { display: flex; gap: 0.5rem; margin-bottom: 1.5rem; border-bottom: 1px solid #334155; padding-bottom: 1rem; }
                .tab { padding: 0.75rem 1.5rem; border: none; border-radius: 8px 8px 0 0; cursor: pointer; font-weight: 500; font-size: 1rem; transition: all 0.2s; background: transparent; color: #64748b; }
                .tab:hover { color: #e2e8f0; }
                .tab.active { background: #1e293b; color: #38bdf8; }
                .tab-content { display: none; }
                .tab-content.active { display: block; }
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
                .deal-card { background: #1e293b; border-radius: 12px; padding: 1.25rem; border: 2px solid #334155; display: grid; grid-template-columns: 120px 1fr auto; gap: 1.25rem; align-items: center; transition: all 0.2s; }
                .deal-card:hover { border-color: #38bdf8; transform: translateY(-2px); box-shadow: 0 4px 20px rgba(0,0,0,0.3); }
                .deal-card.price_error { border-color: #f59e0b; background: linear-gradient(135deg, #1e293b 0%, #422006 100%); }
                .deal-card.all_time_low { border-color: #22c55e; background: linear-gradient(135deg, #1e293b 0%, #052e16 100%); }
                .deal-img { width: 120px; height: 120px; object-fit: contain; background: white; border-radius: 8px; }
                .deal-info { min-width: 0; }
                .deal-info h4 { font-size: 1rem; color: #f1f5f9; margin-bottom: 0.5rem; line-height: 1.4; }
                .deal-info h4 a { color: inherit; text-decoration: none; }
                .deal-info h4 a:hover { color: #38bdf8; }
                .deal-meta { font-size: 0.875rem; color: #94a3b8; display: flex; gap: 1rem; flex-wrap: wrap; margin-top: 0.5rem; }
                .deal-meta span { display: flex; align-items: center; gap: 0.25rem; }
                .deal-time { font-size: 0.75rem; color: #64748b; margin-top: 0.5rem; }
                .deal-price { text-align: right; min-width: 140px; }
                .current-price { font-size: 1.75rem; font-weight: bold; color: #22c55e; }
                .old-price { font-size: 0.875rem; color: #64748b; text-decoration: line-through; margin-bottom: 0.25rem; }
                .discount-badge { display: inline-block; background: #22c55e; color: black; padding: 0.375rem 0.75rem; border-radius: 6px; font-weight: bold; font-size: 1rem; margin-top: 0.5rem; }
                .discount-badge.warning { background: #f59e0b; }
                .deal-type-badge { display: inline-block; font-size: 0.7rem; padding: 0.2rem 0.5rem; border-radius: 4px; text-transform: uppercase; letter-spacing: 0.5px; margin-top: 0.25rem; }
                .deal-type-badge.price_error { background: rgba(245, 158, 11, 0.2); color: #f59e0b; }
                .deal-type-badge.all_time_low { background: rgba(34, 197, 94, 0.2); color: #22c55e; }
                .category-item { background: #0f172a; padding: 1rem; border-radius: 8px; margin-bottom: 0.75rem; }
                .category-item h4 { color: #f1f5f9; margin-bottom: 0.5rem; }
                .category-meta { font-size: 0.875rem; color: #64748b; }
                .status { padding: 0.75rem; border-radius: 6px; margin-top: 1rem; font-size: 0.875rem; }
                .status.success { background: rgba(34, 197, 94, 0.2); color: #22c55e; }
                .status.error { background: rgba(239, 68, 68, 0.2); color: #ef4444; }
                .status.info { background: rgba(14, 165, 233, 0.2); color: #38bdf8; }
                .empty-state { text-align: center; padding: 3rem; color: #64748b; }
                .stats { display: flex; gap: 2rem; margin-bottom: 1.5rem; }
                .stat { text-align: center; padding: 1rem 2rem; background: #1e293b; border-radius: 12px; border: 1px solid #334155; }
                .stat-value { font-size: 2.5rem; font-weight: bold; color: #38bdf8; }
                .stat-label { font-size: 0.875rem; color: #64748b; margin-top: 0.25rem; }
                .auto-refresh { display: flex; align-items: center; gap: 0.5rem; font-size: 0.875rem; color: #64748b; }
                .auto-refresh input { width: auto; margin: 0; }
                .toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem; flex-wrap: wrap; gap: 1rem; }
                .sort-select { width: auto; min-width: 150px; margin: 0; }
                .deals-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem; }
                .deals-count { font-size: 0.875rem; color: #64748b; }
                @media (max-width: 900px) {
                    .grid { grid-template-columns: 1fr; }
                    .deal-card { grid-template-columns: 80px 1fr; }
                    .deal-price { grid-column: 1 / -1; text-align: left; display: flex; align-items: center; gap: 1rem; }
                }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>Deal Hunter</h1>
                <p class="subtitle">Automatic deal detection - alerts when prices drop 50%+ below all-time low</p>

                <div class="stats">
                    <div class="stat">
                        <div class="stat-value" id="stat-deals">0</div>
                        <div class="stat-label">Active Deals</div>
                    </div>
                    <div class="stat">
                        <div class="stat-value" id="stat-categories">0</div>
                        <div class="stat-label">Categories Monitored</div>
                    </div>
                    <div class="stat">
                        <div class="stat-value" id="stat-best-discount">0%</div>
                        <div class="stat-label">Best Discount</div>
                    </div>
                </div>

                <div class="tabs">
                    <button class="tab active" onclick="switchTab('deals')">Deals</button>
                    <button class="tab" onclick="switchTab('categories')">Categories</button>
                    <button class="tab" onclick="switchTab('settings')">Settings</button>
                </div>

                <!-- DEALS TAB -->
                <div id="tab-deals" class="tab-content active">
                    <div class="toolbar">
                        <div class="btn-group">
                            <button class="btn-primary" onclick="refreshDeals()">Refresh</button>
                            <button class="btn-warning" onclick="scanAllCategories()">Scan All Categories</button>
                        </div>
                        <div style="display: flex; gap: 1rem; align-items: center;">
                            <select id="sort-deals" class="sort-select" onchange="refreshDeals()">
                                <option value="newest">Newest First</option>
                                <option value="discount">Biggest Discount</option>
                                <option value="price-low">Lowest Price</option>
                                <option value="price-high">Highest Price</option>
                            </select>
                            <label class="auto-refresh">
                                <input type="checkbox" id="auto-refresh" onchange="toggleAutoRefresh()" />
                                Auto-refresh (30s)
                            </label>
                        </div>
                    </div>
                    <div class="deals-header">
                        <span class="deals-count" id="deals-count">Loading deals...</span>
                    </div>
                    <div id="deals-list" class="deal-grid">
                        <div class="empty-state">Loading deals...</div>
                    </div>
                </div>

                <!-- CATEGORIES TAB -->
                <div id="tab-categories" class="tab-content">
                    <div class="grid">
                        <div class="sidebar">
                            <div class="card">
                                <h3>Add Category to Monitor</h3>
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
                        </div>
                        <div class="main">
                            <div class="card">
                                <h3>Monitored Categories</h3>
                                <div id="categories-list">
                                    <div class="empty-state">No categories yet</div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- SETTINGS TAB -->
                <div id="tab-settings" class="tab-content">
                    <div class="grid">
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
                                <button class="btn-primary" onclick="savePrefs()">Save Settings</button>
                                <button class="btn-success" onclick="testEmail()">Send Test Email</button>
                            </div>
                            <div id="email-status"></div>
                        </div>
                    </div>
                </div>
            </div>

            <script>
                let autoRefreshInterval = null;

                function switchTab(tabName) {
                    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
                    document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
                    document.querySelector(`[onclick="switchTab('${tabName}')"]`).classList.add('active');
                    document.getElementById('tab-' + tabName).classList.add('active');
                }

                function toggleAutoRefresh() {
                    if (document.getElementById('auto-refresh').checked) {
                        autoRefreshInterval = setInterval(refreshDeals, 30000);
                    } else {
                        clearInterval(autoRefreshInterval);
                        autoRefreshInterval = null;
                    }
                }

                function timeAgo(dateStr) {
                    const date = new Date(dateStr);
                    const now = new Date();
                    const seconds = Math.floor((now - date) / 1000);
                    if (seconds < 60) return 'just now';
                    if (seconds < 3600) return Math.floor(seconds / 60) + ' min ago';
                    if (seconds < 86400) return Math.floor(seconds / 3600) + ' hours ago';
                    return Math.floor(seconds / 86400) + ' days ago';
                }

                async function addCategory() {
                    const search = document.getElementById('cat-search').value.trim();
                    const directUrl = document.getElementById('cat-url').value.trim();
                    const maxPrice = parseFloat(document.getElementById('cat-maxprice').value) || null;

                    let url, name;

                    if (directUrl) {
                        url = directUrl;
                        name = search || 'Custom Search';
                    } else if (search) {
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
                        const category = await res.json();
                        if (confirm('Category added! Scan for deals now?')) {
                            await fetch('/api/categories/' + category.id + '/scan', { method: 'POST' });
                            refreshDeals();
                            refreshCategories();
                            switchTab('deals');
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
                    const btn = event.target;
                    btn.disabled = true;
                    btn.textContent = 'Scanning...';
                    const res = await fetch('/api/categories');
                    const categories = await res.json();
                    for (const cat of categories) {
                        if (cat.active) {
                            await fetch('/api/categories/' + cat.id + '/scan', { method: 'POST' });
                        }
                    }
                    btn.disabled = false;
                    btn.textContent = 'Scan All Categories';
                    refreshDeals();
                    refreshCategories();
                }

                async function refreshCategories() {
                    const res = await fetch('/api/categories');
                    const categories = await res.json();
                    document.getElementById('stat-categories').textContent = categories.length;
                    const container = document.getElementById('categories-list');
                    if (categories.length === 0) {
                        container.innerHTML = '<div class="empty-state">No categories yet. Add one above!</div>';
                        return;
                    }
                    container.innerHTML = categories.map(c => `
                        <div class="category-item">
                            <h4>${c.name}</h4>
                            <div class="category-meta">
                                ${c.product_count} products | ${c.min_discount_percent}% off ATL
                                ${c.max_price ? ` | Max $${c.max_price}` : ''}<br>
                                ${c.min_reviews}+ reviews | ${c.min_rating}+ rating<br>
                                Last scan: ${c.last_scanned_at ? timeAgo(c.last_scanned_at) : 'Never'}
                            </div>
                            <div class="btn-group">
                                <button class="btn-warning" onclick="scanCategory('${c.id}', this)">Scan</button>
                                <button class="btn-danger" onclick="deleteCategory('${c.id}')">Delete</button>
                            </div>
                        </div>
                    `).join('');
                }

                async function refreshDeals() {
                    const res = await fetch('/api/deals?limit=100');
                    const data = await res.json();

                    let deals = data.deals || [];
                    const sortBy = document.getElementById('sort-deals').value;

                    // Sort deals
                    switch(sortBy) {
                        case 'discount':
                            deals.sort((a, b) => b.discount_percent - a.discount_percent);
                            break;
                        case 'price-low':
                            deals.sort((a, b) => a.current_price - b.current_price);
                            break;
                        case 'price-high':
                            deals.sort((a, b) => b.current_price - a.current_price);
                            break;
                        default: // newest
                            deals.sort((a, b) => new Date(b.detected_at) - new Date(a.detected_at));
                    }

                    document.getElementById('stat-deals').textContent = deals.length;
                    document.getElementById('deals-count').textContent = `${deals.length} deal${deals.length !== 1 ? 's' : ''} found`;

                    // Find best discount
                    const bestDiscount = deals.length > 0 ? Math.max(...deals.map(d => d.discount_percent)) : 0;
                    document.getElementById('stat-best-discount').textContent = bestDiscount.toFixed(0) + '%';

                    const container = document.getElementById('deals-list');
                    if (deals.length === 0) {
                        container.innerHTML = '<div class="empty-state">No deals found yet. Add a category and scan for deals!</div>';
                        return;
                    }
                    container.innerHTML = deals.map(d => `
                        <div class="deal-card ${d.deal_type}">
                            <img class="deal-img" src="${d.product_image || 'data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%22120%22 height=%22120%22><rect fill=%22%23334155%22 width=%22120%22 height=%22120%22/><text fill=%22%2364748b%22 font-size=%2212%22 x=%2250%25%22 y=%2250%25%22 text-anchor=%22middle%22 dy=%22.3em%22>No Image</text></svg>'}" alt="" onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%22120%22 height=%22120%22><rect fill=%22%23334155%22 width=%22120%22 height=%22120%22/><text fill=%22%2364748b%22 font-size=%2212%22 x=%2250%25%22 y=%2250%25%22 text-anchor=%22middle%22 dy=%22.3em%22>No Image</text></svg>'" />
                            <div class="deal-info">
                                <h4><a href="${d.product_url}" target="_blank">${d.product_name.substring(0, 120)}${d.product_name.length > 120 ? '...' : ''}</a></h4>
                                <div class="deal-meta">
                                    ${d.rating ? `<span>★ ${d.rating.toFixed(1)}</span>` : ''}
                                    ${d.review_count ? `<span>${d.review_count.toLocaleString()} reviews</span>` : ''}
                                </div>
                                <div class="deal-type-badge ${d.deal_type}">${d.deal_type === 'price_error' ? 'PRICE ERROR!' : 'ALL-TIME LOW'}</div>
                                <div class="deal-time">Found ${timeAgo(d.detected_at)}</div>
                            </div>
                            <div class="deal-price">
                                <div class="old-price">Was: $${d.all_time_low.toFixed(2)}</div>
                                <div class="current-price">$${d.current_price.toFixed(2)}</div>
                                <div class="discount-badge ${d.deal_type === 'price_error' ? 'warning' : ''}">${d.discount_percent.toFixed(0)}% OFF</div>
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
