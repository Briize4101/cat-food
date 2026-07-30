(function () {
    let cartItems = [];

    function getToken() {
        return localStorage.getItem('userToken');
    }

    function formatPrice(price) {
        const numberPrice = Number(price || 0);
        return `JPY ${numberPrice.toLocaleString('en-US')}`;
    }

    function authHeaders() {
        return {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${getToken()}`
        };
    }

    function cartTotal(items) {
        return items.reduce((total, item) => total + Number(item.line_total || 0), 0);
    }

    function createCartItem(item) {
        const product = item.product || {};
        const row = document.createElement('div');
        row.className = 'cart-item';
        row.innerHTML = `
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
        if (!token) {
            return false;
        }
        if (typeof checkLoginStatus === 'function') {
            return checkLoginStatus();
        }
        return true;
    }

    async function requestCart(url, options) {
        const response = await fetch(url, {
            cache: 'no-store',
            ...options,
            headers: {
                ...authHeaders(),
                ...(options && options.headers ? options.headers : {})
            }
        });
        const data = await response.json();

        if (!response.ok || !data.success) {
            throw new Error(data.message || '購物車資料處理失敗');
        }

        return data;
    }

    async function loadCart() {
        const data = await requestCart('/api/cart', { method: 'GET' });
        cartItems = data.items || [];
        renderCart(data.total);
    }

    function renderCart(apiTotal) {
        const list = document.getElementById('cartList');
        const empty = document.getElementById('cartEmpty');
        const total = document.getElementById('cartTotal');

        if (!list || !empty || !total) {
            return;
        }

        list.innerHTML = '';

        if (cartItems.length === 0) {
            empty.hidden = false;
            total.textContent = formatPrice(0);
            return;
        }

        empty.hidden = true;
        cartItems.forEach((item) => list.appendChild(createCartItem(item)));
        total.textContent = formatPrice(apiTotal === undefined ? cartTotal(cartItems) : apiTotal);
    }

    function applyCartResponse(data) {
        cartItems = data.items || [];
        renderCart(data.total);
    }

    function initCartActions() {
        const list = document.getElementById('cartList');
        const clearButton = document.getElementById('clearCartBtn');
        const status = document.getElementById('cartPageStatus');

        if (list) {
            list.addEventListener('change', async (event) => {
                const input = event.target.closest('[data-cart-qty]');
                if (!input) return;

                const productId = input.dataset.cartQty;
                const quantity = Math.max(1, Number(input.value || 1));

                try {
                    if (status) status.textContent = 'Saving...';
                    const data = await requestCart(`/api/cart/items/${productId}`, {
                        method: 'PUT',
                        body: JSON.stringify({ quantity })
                    });
                    applyCartResponse(data);
                    if (status) status.textContent = '';
                } catch (error) {
                    if (status) status.textContent = error.message || '購物車更新失敗';
                }
            });

            list.addEventListener('click', async (event) => {
                const button = event.target.closest('[data-cart-remove]');
                if (!button) return;

                const productId = button.dataset.cartRemove;

                try {
                    if (status) status.textContent = 'Removing...';
                    const data = await requestCart(`/api/cart/items/${productId}`, { method: 'DELETE' });
                    applyCartResponse(data);
                    if (status) status.textContent = '';
                } catch (error) {
                    if (status) status.textContent = error.message || '購物車刪除失敗';
                }
            });
        }

        if (clearButton) {
            clearButton.addEventListener('click', async () => {
                try {
                    if (status) status.textContent = 'Clearing...';
                    const data = await requestCart('/api/cart', { method: 'DELETE' });
                    applyCartResponse(data);
                    if (status) status.textContent = '';
                } catch (error) {
                    if (status) status.textContent = error.message || '購物車清空失敗';
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
            if (status) status.textContent = '請先登入後再查看購物車。';
            window.location.href = 'log_in.html';
            return;
        }

        initCartActions();

        try {
            await loadCart();
            if (status) status.textContent = '';
        } catch (error) {
            if (status) status.textContent = error.message || '購物車讀取失敗';
        }
    });
})();
