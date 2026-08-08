const STATUSES = [
    'pending_payment',
    'paid',
    'processing',
    'shipped',
    'completed',
    'cancelled',
    'payment_failed'
];

const statusEl = document.getElementById('adminStatus');
const ordersBody = document.getElementById('ordersBody');
const refreshBtn = document.getElementById('refreshBtn');
const statusFilter = document.getElementById('statusFilter');
let orders = [];
let adminPassword = sessionStorage.getItem('orderAdminPassword') || '';

function getAdminHeaders(extraHeaders = {}) {
    return {
        ...extraHeaders,
        'X-Admin-Password': adminPassword
    };
}

function ensureAdminPassword() {
    if (adminPassword) return true;

    const password = window.prompt('Enter order admin password');
    if (!password) {
        setStatus('Admin password is required.', true);
        return false;
    }

    adminPassword = password;
    sessionStorage.setItem('orderAdminPassword', password);
    return true;
}

function setStatus(message, isError = false) {
    statusEl.textContent = message;
    statusEl.classList.toggle('error', isError);
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

function createStatusOptions(currentStatus) {
    return STATUSES.map(status => {
        const selected = status === currentStatus ? 'selected' : '';
        return `<option value="${status}" ${selected}>${status}</option>`;
    }).join('');
}

function renderStatusFilter() {
    statusFilter.innerHTML = '<option value="">All statuses</option>' + STATUSES.map(status => (
        `<option value="${status}">${status}</option>`
    )).join('');
}

function renderOrders() {
    const filter = statusFilter.value;
    const visibleOrders = filter ? orders.filter(order => order.status === filter) : orders;

    if (!visibleOrders.length) {
        ordersBody.innerHTML = '<tr><td colspan="7">No orders found.</td></tr>';
        return;
    }

    ordersBody.innerHTML = visibleOrders.map(order => {
        const member = order.member || {};
        const items = (order.items || []).map(item => {
            const product = item.products || {};
            return `
                <div class="item-line">
                    <span>${product.name || `Product #${item.product_id}`}</span>
                    <span>x ${item.quantity}</span>
                    <span>${formatMoney(item.line_total)}</span>
                </div>
            `;
        }).join('') || '<span class="muted">No items</span>';

        return `
            <tr>
                <td><span class="order-id">#${order.id}</span><br><span class="muted">${formatDate(order.created_at)}</span></td>
                <td>${member.email || `Member #${order.member_id}`}<br><span class="muted">${member.name || ''}</span></td>
                <td><div class="items">${items}</div></td>
                <td>${formatMoney(order.total_amount)}</td>
                <td><span class="badge">${order.status}</span></td>
                <td>
                    <select data-order-status="${order.id}" aria-label="Change order ${order.id} status">
                        ${createStatusOptions(order.status)}
                    </select>
                </td>
                <td>${formatDate(order.updated_at)}</td>
            </tr>
        `;
    }).join('');

    document.querySelectorAll('[data-order-status]').forEach(select => {
        select.addEventListener('change', () => updateOrderStatus(select.dataset.orderStatus, select.value, select));
    });
}

async function loadOrders() {
    if (!ensureAdminPassword()) return;

    refreshBtn.disabled = true;
    setStatus('Loading orders...');

    try {
        const response = await fetch('/api/admin/orders', {
            cache: 'no-store',
            headers: getAdminHeaders()
        });
        const data = await response.json();

        if (!response.ok || !data.success) {
            throw new Error(data.message || 'Order load failed');
        }

        orders = data.orders || [];
        renderOrders();
        setStatus(`${orders.length} orders loaded.`);
    } catch (error) {
        console.error(error);
        if (error.message === 'Invalid admin password') {
            sessionStorage.removeItem('orderAdminPassword');
            adminPassword = '';
        }
        setStatus(error.message || 'Order load failed', true);
    } finally {
        refreshBtn.disabled = false;
    }
}

async function updateOrderStatus(orderId, status, select) {
    const originalStatus = orders.find(order => String(order.id) === String(orderId))?.status;
    select.disabled = true;
    setStatus(`Updating order #${orderId}...`);

    try {
        const response = await fetch(`/api/admin/orders/${orderId}/status`, {
            method: 'PUT',
            headers: getAdminHeaders({ 'Content-Type': 'application/json' }),
            body: JSON.stringify({ status })
        });
        const data = await response.json();

        if (!response.ok || !data.success) {
            throw new Error(data.message || 'Status update failed');
        }

        const index = orders.findIndex(order => String(order.id) === String(orderId));
        if (index >= 0) {
            orders[index] = data.order;
        }
        renderOrders();
        setStatus(`Order #${orderId} updated to ${status}.`);
    } catch (error) {
        console.error(error);
        if (originalStatus) select.value = originalStatus;
        if (error.message === 'Invalid admin password') {
            sessionStorage.removeItem('orderAdminPassword');
            adminPassword = '';
        }
        setStatus(error.message || 'Status update failed', true);
    } finally {
        select.disabled = false;
    }
}

refreshBtn.addEventListener('click', loadOrders);
statusFilter.addEventListener('change', renderOrders);
renderStatusFilter();
loadOrders();