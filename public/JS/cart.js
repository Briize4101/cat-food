(function () {
    let cartItems = [];
    let unpaidOrders = [];
    const selectedProductIds = new Set();
    const ORDER_API_BASE = 'http://127.0.0.1:5001';

    function getToken() {
        return localStorage.getItem('userToken');
    }

    function formatPrice(price) {
        const numberPrice = Number(price || 0);
        return `JPY ${numberPrice.toLocaleString('en-US')}`;
    }

    function formatDate(value) {
        if (!value) return '';
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) return value;
        return date.toLocaleString();
    }

    function authHeaders() {
        return {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${getToken()}`
        };
    }

    function selectedTotal() {
        return cartItems
            .filter((item) => selectedProductIds.has(Number(item.product_id)))
            .reduce((total, item) => total + Number(item.line_total || 0), 0);
    }

    function syncSelectedItems() {
        const availableIds = new Set(cartItems.map((item) => Number(item.product_id)));
        Array.from(selectedProductIds).forEach((productId) => {
            if (!availableIds.has(productId)) {
                selectedProductIds.delete(productId);
            }
        });
    }

    function createCartItem(item) {
        const product = item.product || {};
        const productId = Number(item.product_id);
        const checked = selectedProductIds.has(productId) ? 'checked' : '';
        const row = document.createElement('div');
        row.className = 'cart-item';
        row.innerHTML = `
            <label class="cart-item-select">
                <input type="checkbox" data-cart-select="${item.product_id}" ${checked}>
            </label>
            <img src="${product.image_url || ''}" alt="${product.name || 'product'}">
            <div class="cart-item-info">
                <h3>${product.name || 'Product'}</h3>
                <p>${formatPrice(product.price)}</p>
                <label>
                    Quantity
                    <input type="number" min="1" value="${item.quantity || 1}" data-cart-qty="${item.product_id}">
                </label>
            </div>
            <div class="cart-item-actions">
                <strong>${formatPrice(item.line_total)}</strong>
                <button type="button" class="btn" data-cart-remove="${item.product_id}">Remove</button>
            </div>
        `;
        return row;
    }

    async function ensureLoggedIn() {
        const token = getToken();
        if (!token) return false;
        if (typeof checkLoginStatus === 'function') {
            return checkLoginStatus();
        }
        return true;
    }

    async function requestCart(url, options = {}) {
        const response = await fetch(url, {
            cache: 'no-store',
            ...options,
            headers: {
                ...authHeaders(),
                ...(options.headers || {})
            }
        });
        const data = await response.json();

        if (!response.ok || !data.success) {
            throw new Error(data.message || 'Request failed');
        }

        return data;
    }

    async function loadUnpaidOrders() {
        const data = await requestCart(`${ORDER_API_BASE}/api/orders`, { method: 'GET' });
        unpaidOrders = (data.orders || []).filter((order) => (
            order.status === 'pending_payment' || order.status === 'payment_failed'
        ));
        renderUnpaidOrders();
    }

    function renderUnpaidOrders() {
        const section = document.getElementById('unpaidOrders');
        const list = document.getElementById('unpaidOrdersList');
        if (!section || !list) return;

        if (!unpaidOrders.length) {
            section.hidden = true;
            list.innerHTML = '';
            return;
        }

        section.hidden = false;
        list.innerHTML = unpaidOrders.map((order) => `
            <div class="unpaid-order">
                <div>
                    <strong>Order #${order.id} - ${formatPrice(order.total_amount)}</strong>
                    <span>${order.status} ${formatDate(order.created_at)}</span>
                </div>
                <div class="unpaid-order-actions">
                    <a class="btn" href="payment.html?id=${order.id}">Continue payment</a>
                    <button type="button" class="btn secondary" data-order-cancel="${order.id}">Cancel order</button>
                </div>
            </div>
        `).join('');
    }

    async function loadCart() {
        const data = await requestCart('/api/cart', { method: 'GET' });
        cartItems = data.items || [];
        syncSelectedItems();
        renderCart();
    }

    function renderCart() {
        const list = document.getElementById('cartList');
        const empty = document.getElementById('cartEmpty');
        const total = document.getElementById('cartTotal');
        const checkoutButton = document.getElementById('checkoutBtn');

        if (!list || !empty || !total) return;

        list.innerHTML = '';

        if (cartItems.length === 0) {
            empty.hidden = false;
            total.textContent = formatPrice(0);
            if (checkoutButton) checkoutButton.disabled = true;
            return;
        }

        empty.hidden = true;
        cartItems.forEach((item) => list.appendChild(createCartItem(item)));
        total.textContent = formatPrice(selectedTotal());
        if (checkoutButton) checkoutButton.disabled = selectedProductIds.size === 0;
    }

    function applyCartResponse(data) {
        cartItems = data.items || [];
        syncSelectedItems();
        renderCart();
    }

    function initCartActions() {
        const list = document.getElementById('cartList');
        const clearButton = document.getElementById('clearCartBtn');
        const checkoutButton = document.getElementById('checkoutBtn');
        const unpaidOrdersList = document.getElementById('unpaidOrdersList');
        const status = document.getElementById('cartPageStatus');

        if (unpaidOrdersList) {
            unpaidOrdersList.addEventListener('click', async (event) => {
                const button = event.target.closest('[data-order-cancel]');
                if (!button) return;

                const orderId = button.dataset.orderCancel;
                const confirmed = window.confirm(`Cancel order #${orderId}?`);
                if (!confirmed) return;

                try {
                    button.disabled = true;
                    if (status) status.textContent = `Cancelling order #${orderId}...`;
                    await requestCart(`${ORDER_API_BASE}/api/orders/${orderId}/cancel`, { method: 'POST' });
                    await loadUnpaidOrders();
                    if (status) status.textContent = `Order #${orderId} cancelled.`;
                } catch (error) {
                    if (status) status.textContent = error.message || 'Cancel order failed';
                    button.disabled = false;
                }
            });
        }

        if (list) {
            list.addEventListener('change', async (event) => {
                const selectInput = event.target.closest('[data-cart-select]');
                if (selectInput) {
                    const productId = Number(selectInput.dataset.cartSelect);
                    if (selectInput.checked) {
                        selectedProductIds.add(productId);
                    } else {
                        selectedProductIds.delete(productId);
                    }
                    renderCart();
                    return;
                }

                const quantityInput = event.target.closest('[data-cart-qty]');
                if (!quantityInput) return;

                const productId = quantityInput.dataset.cartQty;
                const quantity = Math.max(1, Number(quantityInput.value || 1));

                try {
                    if (status) status.textContent = 'Saving...';
                    const data = await requestCart(`/api/cart/items/${productId}`, {
                        method: 'PUT',
                        body: JSON.stringify({ quantity })
                    });
                    applyCartResponse(data);
                    if (status) status.textContent = '';
                } catch (error) {
                    if (status) status.textContent = error.message || 'Quantity update failed';
                }
            });

            list.addEventListener('click', async (event) => {
                const button = event.target.closest('[data-cart-remove]');
                if (!button) return;

                const productId = Number(button.dataset.cartRemove);

                try {
                    if (status) status.textContent = 'Removing...';
                    const data = await requestCart(`/api/cart/items/${productId}`, { method: 'DELETE' });
                    selectedProductIds.delete(productId);
                    applyCartResponse(data);
                    if (status) status.textContent = '';
                } catch (error) {
                    if (status) status.textContent = error.message || 'Remove item failed';
                }
            });
        }

        if (checkoutButton) {
            checkoutButton.addEventListener('click', async () => {
                if (selectedProductIds.size === 0) {
                    if (status) status.textContent = 'Please select at least one product';
                    return;
                }

                try {
                    checkoutButton.disabled = true;
                    if (status) status.textContent = 'Creating order...';
                    const data = await requestCart(`${ORDER_API_BASE}/api/orders`, {
                        method: 'POST',
                        body: JSON.stringify({ product_ids: Array.from(selectedProductIds) })
                    });
                    selectedProductIds.clear();
                    applyCartResponse(data.cart || { items: [], total: 0 });
                    if (status) status.textContent = `Order created: #${data.order.id}`;
                    window.location.href = `payment.html?id=${data.order.id}`;
                } catch (error) {
                    if (status) status.textContent = error.message || 'Order creation failed';
                    checkoutButton.disabled = selectedProductIds.size === 0;
                }
            });
        }

        if (clearButton) {
            clearButton.addEventListener('click', async () => {
                try {
                    if (status) status.textContent = 'Clearing...';
                    const data = await requestCart('/api/cart', { method: 'DELETE' });
                    selectedProductIds.clear();
                    applyCartResponse(data);
                    if (status) status.textContent = '';
                } catch (error) {
                    if (status) status.textContent = error.message || 'Clear cart failed';
                }
            });
        }
    }

    document.addEventListener('DOMContentLoaded', async () => {
        const page = document.getElementById('cartPage');
        const status = document.getElementById('cartPageStatus');
        if (!page) return;

        const isLoggedIn = await ensureLoggedIn();
        if (!isLoggedIn) {
            if (status) status.textContent = 'Please login before opening cart';
            window.location.href = 'log_in.html';
            return;
        }

        initCartActions();

        try {
            await loadUnpaidOrders();
            await loadCart();
            if (status) status.textContent = '';
        } catch (error) {
            if (status) status.textContent = error.message || 'Cart load failed';
        }
    });
})();
