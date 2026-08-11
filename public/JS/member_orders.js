(function () {
    const ORDER_API_BASE = 'http://127.0.0.1:5001';
    const PAID_ORDER_STATUSES = new Set(['paid', 'processing', 'shipped', 'completed']);

    function getToken() {
        return localStorage.getItem('userToken');
    }

    function formatMoney(value) {
        const amount = Number(value || 0);
        return `JPY ${amount.toLocaleString('en-US')}`;
    }

    function formatDate(value) {
        if (!value) return '-';
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) return value;
        return date.toLocaleString();
    }

    function renderOrderHistory(orders) {
        const list = document.getElementById('orderHistoryList');
        const empty = document.getElementById('orderHistoryEmpty');
        const status = document.getElementById('orderHistoryStatus');
        if (!list || !empty || !status) return;

        const paidOrders = orders.filter(order => PAID_ORDER_STATUSES.has(order.status));
        list.innerHTML = '';

        if (!paidOrders.length) {
            empty.hidden = false;
            status.textContent = '';
            return;
        }

        empty.hidden = true;
        status.textContent = '';
        list.innerHTML = paidOrders.map(order => {
            const items = (order.items || []).map(item => {
                const product = item.products || {};
                return `<div>${product.name || `Product #${item.product_id}`} x ${item.quantity} - ${formatMoney(item.line_total)}</div>`;
            }).join('') || '<div>No items</div>';

            return `
                <article class="order-history-card">
                    <div class="order-history-head">
                        <strong>Order #${order.id}</strong>
                        <span>Status: ${order.status}</span>
                        <span>Total: ${formatMoney(order.total_amount)}</span>
                        <span>${formatDate(order.created_at)}</span>
                    </div>
                    <div class="order-history-items">${items}</div>
                </article>
            `;
        }).join('');
    }

    window.initMemberOrderHistory = async function initMemberOrderHistory() {
        const status = document.getElementById('orderHistoryStatus');
        const token = getToken();
        if (!status || !token) return;

        try {
            status.textContent = 'Loading orders...';
            const response = await fetch(`${ORDER_API_BASE}/api/orders`, {
                cache: 'no-store',
                headers: { 'Authorization': `Bearer ${token}` }
            });
            const data = await response.json();

            if (!response.ok || !data.success) {
                throw new Error(data.message || 'Order history load failed');
            }

            renderOrderHistory(data.orders || []);
        } catch (error) {
            status.textContent = error.message || 'Order history load failed';
        }
    };
})();
