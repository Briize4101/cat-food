async function checkLoginStatus() {
    const token = localStorage.getItem('userToken');

    if (!token) {
        return false;
    }

    try {
        const response = await fetch('/api/check-auth', {
            method: 'GET',
            cache: 'no-store',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            }
        });

        if (!response.ok) {
            clearLoginState();
            return false;
        }

        const data = await response.json();
        if (!data.loggedIn) {
            clearLoginState();
        }

        return Boolean(data.loggedIn);
    } catch (error) {
        console.error('Check login status failed:', error);
        return false;
    }
}

function clearLoginState() {
    localStorage.removeItem('userToken');
    sessionStorage.clear();
    document.cookie = 'isLogin=; Max-Age=0; path=/;';
}

function initLoginForm() {
    const loginForm = document.getElementById('loginForm');
    if (!loginForm) return;

    loginForm.addEventListener('submit', async function(e) {
        e.preventDefault();

        const usernameVal = document.getElementById('email').value.trim();
        const passwordVal = document.getElementById('password').value;

        try {
            const response = await fetch('/api/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username: usernameVal, password: passwordVal })
            });

            const data = await response.json();

            if (data.success) {
                localStorage.setItem('userToken', data.token);
                alert('登入成功');
                window.location.replace('member.html');
            } else {
                clearLoginState();
                alert(data.message || '帳號或密碼錯誤');
            }
        } catch (error) {
            console.error('Login failed:', error);
            alert('登入時發生錯誤，請稍後再試');
        }
    });
}

async function logout() {
    const token = localStorage.getItem('userToken');

    try {
        await fetch('/api/logout', {
            method: 'POST',
            cache: 'no-store',
            headers: token ? { 'Authorization': `Bearer ${token}` } : {}
        });
    } catch (error) {
        console.error('Logout request failed:', error);
    }

    clearLoginState();
    window.location.replace('log_in.html');
}
function initMemberLink() {
    const memberLink = document.getElementById('memberLink');
    if (!memberLink) return;

    memberLink.addEventListener('click', async function(e) {
        e.preventDefault();
        const isLoggedIn = await checkLoginStatus();
        window.location.href = isLoggedIn ? 'member.html' : 'log_in.html';
    });
}

function initLoginPageRedirect() {
    const currentPage = window.location.pathname.split('/').pop() || 'log_in.html';
    if (currentPage !== 'log_in.html') return;

    checkLoginStatus().then(isLoggedIn => {
        if (isLoggedIn) {
            window.location.replace('member.html');
        }
    });
}

document.addEventListener('DOMContentLoaded', () => {
    initMemberLink();
    initLoginPageRedirect();
});
