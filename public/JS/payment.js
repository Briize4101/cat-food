(function () {
    let currentOrderId = null;
    let statusPollTimer = null;

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

    function stopStatusPolling() {
        if (statusPollTimer) {
            window.clearInterval(statusPollTimer);
            statusPollTimer = null;
        }
    }

    function handlePaidOrder() {
        stopStatusPolling();
        setStatus('Payment success. Returning to cart...');
        window.setTimeout(() => {
            window.location.replace('cart.html');
        }, 1200);
    }

    function startStatusPolling() {
        stopStatusPolling();
        statusPollTimer = window.setInterval(async () => {
            if (!currentOrderId) return;
            try {
                const data = await requestOrder(`/api/orders/${currentOrderId}`);
                renderOrder(data.order);
                if (data.order && data.order.status === 'paid') {
                    handlePaidOrder();
                }
            } catch (error) {
                console.warn('Order status polling failed', error);
            }
        }, 3000);
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
            throw new Error('Please enter recipient name and recipient address');
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

        const response = await fetch(path, {
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
        const submitBtn = document.getElementById('submitPaymentInfoBtn');

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

        const canSubmit = order.status === 'pending_payment' || order.status === 'payment_failed';
        submitBtn.disabled = !canSubmit;
        detail.hidden = false;

        if (order.status === 'paid') {
            handlePaidOrder();
        } else if (canSubmit) {
            setStatus('Submit payment, then wait for admin confirmation.');
        } else {
            setStatus(`This order is now ${order.status}.`);
        }
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

    async function submitPaymentInfo() {
        if (!currentOrderId) return;

        const submitBtn = document.getElementById('submitPaymentInfoBtn');
        submitBtn.disabled = true;
        setStatus('Submitting payment information...');

        try {
            const data = await requestOrder(`/api/orders/${currentOrderId}/recipient`, {
                method: 'PUT',
                body: JSON.stringify(getRecipientDetails())
            });
            renderOrder(data.order);
            setStatus(data.message || 'Payment submitted. Please wait for admin confirmation.');
            startStatusPolling();
        } catch (error) {
            setStatus(error.message || 'Payment information submit failed', true);
            submitBtn.disabled = false;
        }
    }

    document.addEventListener('DOMContentLoaded', async () => {
        const isLoggedIn = typeof checkLoginStatus === 'function' ? await checkLoginStatus() : Boolean(getToken());
        if (!isLoggedIn) {
            window.location.replace('log_in.html');
            return;
        }

        document.getElementById('submitPaymentInfoBtn').addEventListener('click', submitPaymentInfo);
        await loadMemberProfileForRecipient();
        loadOrder();
        startStatusPolling();
    });
})();
