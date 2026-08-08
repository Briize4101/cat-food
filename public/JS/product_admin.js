const productsBody = document.getElementById('productsBody');
const statusEl = document.getElementById('productAdminStatus');
const form = document.getElementById('productForm');
const refreshBtn = document.getElementById('refreshProductsBtn');
const newBtn = document.getElementById('newProductBtn');
let products = [];
let adminPassword = sessionStorage.getItem('orderAdminPassword') || '';

function setStatus(message, isError = false) {
    statusEl.textContent = message;
    statusEl.classList.toggle('error', isError);
}

function ensureAdminPassword() {
    if (adminPassword) return true;
    const password = window.prompt('Enter admin password');
    if (!password) {
        setStatus('Admin password is required.', true);
        return false;
    }
    adminPassword = password;
    sessionStorage.setItem('orderAdminPassword', password);
    return true;
}

function adminHeaders(extra = {}) {
    return { ...extra, 'X-Admin-Password': adminPassword };
}

function money(value) {
    return `JPY ${Number(value || 0).toLocaleString('en-US')}`;
}

async function adminFetch(url, options = {}) {
    if (!ensureAdminPassword()) throw new Error('Admin password is required');

    const response = await fetch(url, {
        cache: 'no-store',
        ...options,
        headers: adminHeaders({
            'Content-Type': 'application/json',
            ...(options.headers || {})
        })
    });
    const data = await response.json();

    if (!response.ok || !data.success) {
        if (data.message === 'Invalid admin password') {
            sessionStorage.removeItem('orderAdminPassword');
            adminPassword = '';
        }
        throw new Error(data.message || 'Request failed');
    }

    return data;
}

function resetForm() {
    form.reset();
    document.getElementById('productId').value = '';
    document.getElementById('productPrice').value = 0;
    document.getElementById('productStock').value = 0;
    document.getElementById('productActive').checked = true;
    document.getElementById('formTitle').textContent = 'New Product';
}

function fillForm(product) {
    document.getElementById('productId').value = product.id;
    document.getElementById('productName').value = product.name || '';
    document.getElementById('productCategory').value = product.category || '';
    document.getElementById('productFeature').value = product.feature || '';
    document.getElementById('productPrice').value = product.price || 0;
    document.getElementById('productStock').value = product.stock || 0;
    document.getElementById('productImageUrl').value = product.image_url || '';
    document.getElementById('productDescription').value = product.description || '';
    document.getElementById('productActive').checked = Boolean(product.is_active);
    document.getElementById('formTitle').textContent = `Edit Product #${product.id}`;
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

function productPayload() {
    return {
        name: document.getElementById('productName').value.trim(),
        category: document.getElementById('productCategory').value.trim(),
        feature: document.getElementById('productFeature').value.trim(),
        price: Number(document.getElementById('productPrice').value || 0),
        stock: Number(document.getElementById('productStock').value || 0),
        image_url: document.getElementById('productImageUrl').value.trim(),
        description: document.getElementById('productDescription').value.trim(),
        is_active: document.getElementById('productActive').checked
    };
}

function renderProducts() {
    if (!products.length) {
        productsBody.innerHTML = '<tr><td colspan="7">No products found.</td></tr>';
        return;
    }

    productsBody.innerHTML = products.map(product => `
        <tr>
            <td>${product.id}</td>
            <td><img class="thumb" src="${product.image_url || ''}" alt="${product.name || 'product'}"></td>
            <td><strong>${product.name || 'Product'}</strong><br><span class="muted">${product.category || ''}</span></td>
            <td>${money(product.price)}</td>
            <td>${product.stock ?? 0}</td>
            <td><span class="badge">${product.is_active ? 'Active' : 'Hidden'}</span></td>
            <td><button type="button" class="secondary" data-edit-product="${product.id}">Edit</button></td>
        </tr>
    `).join('');

    document.querySelectorAll('[data-edit-product]').forEach(button => {
        button.addEventListener('click', () => {
            const product = products.find(item => String(item.id) === String(button.dataset.editProduct));
            if (product) fillForm(product);
        });
    });
}

async function loadProducts() {
    refreshBtn.disabled = true;
    setStatus('Loading products...');
    try {
        const data = await adminFetch('/api/admin/products');
        products = data.products || [];
        renderProducts();
        setStatus(`${products.length} products loaded.`);
    } catch (error) {
        setStatus(error.message || 'Product load failed', true);
    } finally {
        refreshBtn.disabled = false;
    }
}

async function saveProduct(event) {
    event.preventDefault();
    const saveBtn = document.getElementById('saveProductBtn');
    const productId = document.getElementById('productId').value;
    const method = productId ? 'PUT' : 'POST';
    const url = productId ? `/api/admin/products/${productId}` : '/api/admin/products';

    saveBtn.disabled = true;
    setStatus('Saving product...');
    try {
        await adminFetch(url, {
            method,
            body: JSON.stringify(productPayload())
        });
        resetForm();
        await loadProducts();
        setStatus('Product saved.');
    } catch (error) {
        setStatus(error.message || 'Product save failed', true);
    } finally {
        saveBtn.disabled = false;
    }
}

form.addEventListener('submit', saveProduct);
refreshBtn.addEventListener('click', loadProducts);
newBtn.addEventListener('click', resetForm);
loadProducts();