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


async function getSupabaseClient() {
    if (!window.supabase) {
        throw new Error('Supabase JS 撠頛');
    }

    const response = await fetch('/api/supabase-config', { cache: 'no-store' });
    const config = await response.json();

    if (!response.ok || !config.success) {
        throw new Error(config.message || 'Supabase config load failed');
    }

    return window.supabase.createClient(config.supabaseUrl, config.supabaseAnonKey);
}

async function finishGoogleLogin(session) {
    if (!session || !session.access_token) {
        return false;
    }

    const response = await fetch('/api/auth/google', {
        method: 'POST',
        cache: 'no-store',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ access_token: session.access_token })
    });

    const data = await response.json();

    if (!response.ok || !data.success) {
        throw new Error(data.message || 'Google ?餃憭望?');
    }

    localStorage.setItem('userToken', data.token);
    window.history.replaceState({}, document.title, 'log_in.html');
    window.location.replace('member.html');
    return true;
}

async function handleGoogleOAuthCallback() {
    const currentPage = window.location.pathname.split('/').pop() || 'log_in.html';
    const hasOAuthData = window.location.hash.includes('access_token') || window.location.search.includes('code=');

    if (currentPage !== 'log_in.html' || !hasOAuthData) {
        return false;
    }

    try {
        const client = await getSupabaseClient();
        let session = null;

        if (window.location.search.includes('code=')) {
            const exchangeResult = await client.auth.exchangeCodeForSession(window.location.href);
            if (exchangeResult.error) {
                throw exchangeResult.error;
            }
            session = exchangeResult.data ? exchangeResult.data.session : null;
        } else {
            const sessionResult = await client.auth.getSession();
            session = sessionResult.data ? sessionResult.data.session : null;
        }

        return await finishGoogleLogin(session);
    } catch (error) {
        console.error('Google OAuth callback failed:', error);
        clearLoginState();
        alert(error.message || 'Google ?餃憭望?嚗?蝔??岫');
        return false;
    }
}

function initGoogleLogin() {
    const googleLoginBtn = document.getElementById('googleLoginBtn');
    if (!googleLoginBtn) return;

    googleLoginBtn.addEventListener('click', async function() {
        googleLoginBtn.disabled = true;

        try {
            const client = await getSupabaseClient();
            const redirectTo = `${window.location.origin}/log_in.html`;
            const result = await client.auth.signInWithOAuth({
                provider: 'google',
                options: {
                    redirectTo,
                    queryParams: {
                        prompt: 'select_account'
                    }
                }
            });

            if (result.error) {
                throw result.error;
            }
        } catch (error) {
            console.error('Google login failed:', error);
            alert(error.message || 'Google ?餃憭望?嚗?蝔??岫');
            googleLoginBtn.disabled = false;
        }
    });
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
                alert('Login success');
                window.location.replace('member.html');
            } else {
                clearLoginState();
                alert(data.message || 'Invalid email or password');
            }
        } catch (error) {
            console.error('Login failed:', error);
            alert('Login failed. Please try again.');
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

document.addEventListener('DOMContentLoaded', async () => {
    initMemberLink();
    initGoogleLogin();
    const handledGoogleLogin = await handleGoogleOAuthCallback();
    if (!handledGoogleLogin) {
        initLoginPageRedirect();
    }
});
async function loadMemberProfile() {
    const token = localStorage.getItem('userToken');
    if (!token) return;

    try {
        const response = await fetch('/api/member/profile', {
            method: 'GET',
            cache: 'no-store',
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });

        if (!response.ok) {
            if (response.status === 401) {
                clearLoginState();
                window.location.replace('log_in.html');
            }
            return;
        }

        const data = await response.json();
        if (!data.success || !data.profile) return;

        const profile = data.profile;
        const emailInput = document.getElementById('profileEmail');
        const nameInput = document.getElementById('profileName');
        const phoneInput = document.getElementById('profilePhone');
        const addressInput = document.getElementById('profileAddress');

        if (emailInput) emailInput.value = profile.email || '';
        if (nameInput) nameInput.value = profile.name || '';
        if (phoneInput) phoneInput.value = profile.phone || '';
        if (addressInput) addressInput.value = profile.address || '';
    } catch (error) {
        console.error('Load member profile failed:', error);
    }
}

function initMemberProfileForm() {
    const profileForm = document.getElementById('profileForm');
    if (!profileForm) return;

    loadMemberProfile();

    profileForm.addEventListener('submit', async function(e) {
        e.preventDefault();

        const token = localStorage.getItem('userToken');
        if (!token) {
            window.location.replace('log_in.html');
            return;
        }

        const statusEl = document.getElementById('profileStatus');
        const saveBtn = document.getElementById('profileSaveBtn');
        const payload = {
            name: document.getElementById('profileName').value.trim(),
            phone: document.getElementById('profilePhone').value.trim(),
            address: document.getElementById('profileAddress').value.trim()
        };

        if (saveBtn) saveBtn.disabled = true;
        if (statusEl) statusEl.textContent = 'Saving...';

        try {
            const response = await fetch('/api/member/profile', {
                method: 'PUT',
                cache: 'no-store',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`
                },
                body: JSON.stringify(payload)
            });

            const data = await response.json();

            if (response.ok && data.success) {
                if (statusEl) statusEl.textContent = 'Saved';
            } else {
                if (response.status === 401) {
                    clearLoginState();
                    window.location.replace('log_in.html');
                    return;
                }
                if (statusEl) statusEl.textContent = data.message || 'Save failed';
            }
        } catch (error) {
            console.error('Save member profile failed:', error);
            if (statusEl) statusEl.textContent = 'Save failed';
        } finally {
            if (saveBtn) saveBtn.disabled = false;
        }
    });
}

