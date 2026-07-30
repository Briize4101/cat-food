(function () {
    const PRODUCT_LINK_RULES = [
        { keywords: ['frozen fresh food'], id: 1 },
        { keywords: ['dry food', 'wild pro'], id: 2 },
        { keywords: ['pure puree', 'pure pure'], id: 3 },
        { keywords: ['care deli', 'anicom'], id: 4 },
        { keywords: ['wild snack'], id: 5 }
    ];

    function normalizeText(value) {
        return (value || '').toLowerCase().replace(/\s+/g, ' ').trim();
    }

    function findProductId(name) {
        const normalizedName = normalizeText(name);
        const rule = PRODUCT_LINK_RULES.find((item) =>
            item.keywords.some((keyword) => normalizedName.includes(keyword))
        );
        return rule ? rule.id : null;
    }

    function formatPrice(price) {
        if (price === null || price === undefined || price === '') {
            return 'Price not set';
        }
        const numberPrice = Number(price);
        if (Number.isNaN(numberPrice)) {
            return String(price);
        }
        return `JPY ${numberPrice.toLocaleString('en-US')}`;
    }

    function setText(id, value, fallback) {
        const element = document.getElementById(id);
        if (element) {
            element.textContent = value || fallback || '';
        }
    }

    async function requireLogin() {
        const token = localStorage.getItem('userToken');
        if (!token) {
            return false;
        }

        if (typeof checkLoginStatus === 'function') {
            return checkLoginStatus();
        }

        return true;
    }

    async function addProductToCart(product) {
        const token = localStorage.getItem('userToken');
        const response = await fetch('/api/cart/items', {
            method: 'POST',
            cache: 'no-store',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify({
                product_id: product.id,
                quantity: 1
            })
        });
        const data = await response.json();

        if (!response.ok || !data.success) {
            throw new Error(data.message || '加入購物車失敗');
        }

        return data;
    }

    function initAddToCart(product) {
        const addButton = document.getElementById('addToCartBtn');
        const cartStatus = document.getElementById('cartStatus');

        if (!addButton) {
            return;
        }

        addButton.disabled = false;
        addButton.addEventListener('click', async () => {
            addButton.disabled = true;
            if (cartStatus) cartStatus.textContent = 'Adding...';

            const isLoggedIn = await requireLogin();
            if (!isLoggedIn) {
                if (cartStatus) cartStatus.textContent = '請先登入後再加入購物車。';
                window.location.href = 'log_in.html';
                return;
            }

            try {
                await addProductToCart(product);
                if (cartStatus) cartStatus.textContent = '已加入購物車。';
            } catch (error) {
                if (cartStatus) cartStatus.textContent = error.message || '加入購物車失敗';
            } finally {
                addButton.disabled = false;
            }
        });
    }

    function createProductCard(product) {
        const detailUrl = `product_detail.html?id=${product.id}`;
        const card = document.createElement('div');
        card.className = 'product-col';
        card.dataset.productId = product.id;
        card.style.cursor = 'pointer';
        card.innerHTML = `
            <a href="${detailUrl}" class="img">
                <img src="${product.image_url || ''}" alt="${product.name || 'product'}" style="background-color: #FFFFF0;">
                <span class="feature">${product.feature || 'Product'}</span>
            </a>
            <div class="info">
                <div class="product-name">${product.name || 'Product'}</div>
                <div class="introduction">${product.description || ''}</div>
                <div class="tags">
                    <span class="room-tmpt">${product.category || 'product'}</span>
                    <span class="free-shp">Stock ${product.stock ?? 0}</span>
                </div>
                <p class="price">${formatPrice(product.price)}<span class="tax">/tax included~</span></p>
            </div>
            <a href="${detailUrl}" class="btn">View details</a>
        `;
        card.addEventListener('click', (event) => {
            if (event.target.closest('a')) return;
            window.location.href = detailUrl;
        });
        return card;
    }

    async function loadProductLists() {
        const lists = document.querySelectorAll('[data-products-list]');
        if (lists.length === 0) {
            return;
        }

        lists.forEach((list) => {
            list.innerHTML = '<p class="product-list-status">Loading products...</p>';
        });

        try {
            const response = await fetch('/api/products', { cache: 'no-store' });
            const data = await response.json();

            if (!response.ok || !data.success) {
                throw new Error(data.message || '商品清單讀取失敗');
            }

            lists.forEach((list) => {
                const limit = Number(list.dataset.productsLimit || 0);
                const products = limit > 0 ? data.products.slice(0, limit) : data.products;
                list.innerHTML = '';

                if (!products.length) {
                    list.innerHTML = '<p class="product-list-status">目前沒有商品資料。</p>';
                    return;
                }

                products.forEach((product) => {
                    list.appendChild(createProductCard(product));
                });
            });
        } catch (error) {
            lists.forEach((list) => {
                list.innerHTML = `<p class="product-list-status">${error.message || '商品清單讀取失敗'}</p>`;
            });
        }
    }

    function initProductLinks() {
        document.querySelectorAll('.product-col').forEach((card) => {
            const nameElement = card.querySelector('.product-name');
            const productId = card.dataset.productId || findProductId(nameElement ? nameElement.textContent : '');

            if (!productId) {
                return;
            }

            const detailUrl = `product_detail.html?id=${productId}`;
            card.dataset.productId = productId;
            card.style.cursor = 'pointer';

            card.querySelectorAll('a.img, a.btn').forEach((link) => {
                link.href = detailUrl;
            });

            card.addEventListener('click', (event) => {
                if (event.target.closest('a')) {
                    return;
                }
                window.location.href = detailUrl;
            });
        });
    }

    async function loadProductDetail() {
        const detailRoot = document.getElementById('productDetail');
        const statusElement = document.getElementById('productDetailStatus');

        if (!detailRoot || !statusElement) {
            return;
        }

        const params = new URLSearchParams(window.location.search);
        const productId = params.get('id');

        if (!productId) {
            statusElement.textContent = '找不到商品 ID，請從商品列表重新進入。';
            return;
        }

        try {
            const response = await fetch(`/api/products/${productId}`, { cache: 'no-store' });
            const data = await response.json();

            if (!response.ok || !data.success || !data.product) {
                throw new Error(data.message || '商品資料讀取失敗');
            }

            const product = data.product;
            const imageElement = document.getElementById('productImage');

            if (imageElement) {
                imageElement.src = product.image_url || '';
                imageElement.alt = product.name || 'product image';
            }

            document.title = `${product.name || 'Product'} | Product Detail`;
            setText('productName', product.name, 'Product');
            setText('productFeature', product.feature, 'No feature set');
            setText('productCategory', product.category, 'No category set');
            setText('productPrice', formatPrice(product.price));
            setText('productStock', product.stock === null || product.stock === undefined ? 'Stock not set' : `${product.stock} available`);
            setText('productDescription', product.description, 'No description yet.');

            initAddToCart(product);
            detailRoot.hidden = false;
            statusElement.textContent = '';
        } catch (error) {
            statusElement.textContent = error.message || '商品資料讀取失敗';
        }
    }

    document.addEventListener('DOMContentLoaded', async () => {
        await loadProductLists();
        initProductLinks();
        loadProductDetail();
    });
})();
