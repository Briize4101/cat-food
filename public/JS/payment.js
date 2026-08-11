(function () {
    const ORDER_API_BASE = 'http://127.0.0.1:5001';
    let currentOrderId = null;

    function getToken() {
        return localStorage.getItem('userToken');
    }

    function formatMoney(value) {
        const amount = Number(value || 0);
        return `JPY ${amount.toLocaleString('en-US')}`;
    }

    function setStatus(message, isError = false) {
        const status = document.getElementById('paymentStatus');
        if (!status) return;
        status.textContent = message;
        status.style.color = isError ? '#9d2f2f' : '#746b60';
    }

    function setRecipientFields(name, address) {
        const nameInput = document.getElementById('paymentRecipientName');
        const addressInput = document.getElementById('paymentRecipientAddress');
        if (nameInput && !nameInput.value.trim()) nameInput.value = name || '';
        if (addressInput && !addressInput.value.trim()) addressInput.value = address || '';
    }

    async function loadMemberProfileForRecipient() {
        const token = getToken();
        if (!token) return;

        try {
            const response = await fetch('/api/member/profile', {
                cache: 'no-store',
                headers: { 'Authorization': `Bearer ${token}` }
            });
            const data = await response.json();
            if (response.ok && data.success && data.profile) {
                setRecipientFields(data.profile.name, data.profile.address);
            }
        } catch (error) {
            console.warn('Member profile load failed', error);
        }
    }

    function getRecipientDetails() {
        const nameInput = document.getElementById('paymentRecipientName');
        const addressInput = document.getElementById('paymentRecipientAddress');
        const recipientName = nameInput ? nameInput.value.trim() : '';
        const recipientAddress = addressInput ? addressInput.value.trim() : '';

        if (!recipientName || !recipientAddress) {
            throw new Error('Please enter recipient name and recipient address before payment success');
        }

        return {
            recipient_name: recipientName,
            recipient_address: recipientAddress
        };
    }

    async function requestOrder(path, options = {}) {
        const token = getToken();
        if (!token) {
            window.location.replace('log_in.html');
            throw new Error('Please login first');
        }

        const response = await fetch(`${ORDER_API_BASE}${path}`, {
            cache: 'no-store',
            ...options,
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`,
                ...(options.headers || {})
            }
        });
        const data = await response.json();

        if (!response.ok || !data.success) {
            throw new Error(data.message || 'Order request failed');
        }

        return data;
    }

    function renderOrder(order) {
        const detail = document.getElementById('paymentDetail');
        const itemsRoot = document.getElementById('paymentItems');
        document.getElementById('paymentOrderId').textContent = `#${order.id}`;
        document.getElementById('paymentOrderStatus').textContent = order.status;
        document.getElementById('paymentTotal').textContent = formatMoney(order.total_amount);

        itemsRoot.innerHTML = (order.items || []).map((item) => {
            const product = item.products || {};
            return `
                <div class="payment-item">
                    <span>${product.name || `Product #${item.product_id}`}</span>
                    <span>x ${item.quantity}</span>
                    <strong>${formatMoney(item.line_total)}</strong>
                </div>
            `;
        }).join('');

        setRecipientFields(order.recipient_name, order.recipient_address);

        const canPay = order.status === 'pending_payment' || order.status === 'payment_failed';
        const canFail = order.status === 'pending_payment';
        document.getElementById('paymentSuccessBtn').disabled = !canPay;
        document.getElementById('paymentFailBtn').disabled = !canFail;
        detail.hidden = false;
        setStatus(canPay ? 'Please choose a simulated payment result.' : `This order is now ${order.status}.`);
    }

    async function loadOrder() {
        const params = new URLSearchParams(window.location.search);
        currentOrderId = params.get('id');

        if (!currentOrderId) {
            setStatus('Order ID is missing.', true);
            return;
        }

        try {
            const data = await requestOrder(`/api/orders/${currentOrderId}`);
            renderOrder(data.order);
        } catch (error) {
            setStatus(error.message || 'Order load failed', true);
        }
    }

    async function submitPayment(result) {
        if (!currentOrderId) return;

        const successBtn = document.getElementById('paymentSuccessBtn');
        const failBtn = document.getElementById('paymentFailBtn');
        successBtn.disabled = true;
        failBtn.disabled = true;
        setStatus('Processing simulated payment...');

        try {
            const payload = result === 'success'
                ? { result, ...getRecipientDetails() }
                : { result };
            const data = await requestOrder(`/api/orders/${currentOrderId}/mock-payment`, {
                method: 'POST',
                body: JSON.stringify(payload)
            });
            renderOrder(data.order);
            if (result === 'success') {
                setStatus('Payment success. Returning to cart...');
                window.setTimeout(() => {
                    window.location.replace('cart.html');
                }, 900);
            } else {
                setStatus('Payment failed, please try again', true);
            }
        } catch (error) {
            setStatus(error.message || 'Payment failed', true);
            successBtn.disabled = false;
            failBtn.disabled = false;
        }
    }

    document.addEventListener('DOMContentLoaded', async () => {
        const isLoggedIn = typeof checkLoginStatus === 'function' ? await checkLoginStatus() : Boolean(getToken());
        if (!isLoggedIn) {
            window.location.replace('log_in.html');
            return;
        }

        document.getElementById('paymentSuccessBtn').addEventListener('click', () => submitPayment('success'));
        document.getElementById('paymentFailBtn').addEventListener('click', () => submitPayment('failed'));
        await loadMemberProfileForRecipient();
        loadOrder();
    });
})();