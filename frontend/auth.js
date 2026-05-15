const Auth = (() => {
  let currentUser = null;

  const $ = id => document.getElementById(id);

  async function checkSession() {
    try {
      const res = await fetch('/api/auth/me/');
      if (res.ok) {
        const data = await res.json();
        if (data.authenticated) {
          currentUser = data.user;
          renderUser();
          return;
        }
      }
    } catch (_) {}
    currentUser = null;
    renderGuest();
  }

  function renderUser() {
    const guestEl = $('authGuest');
    const userEl = $('authUser');
    const nameEl = $('navUsername');
    const avatarEl = $('navAvatar');
    if (guestEl) guestEl.style.display = 'none';
    if (userEl) userEl.style.display = 'flex';
    if (nameEl) nameEl.textContent = currentUser.username;
    if (avatarEl) avatarEl.textContent = currentUser.username.charAt(0).toUpperCase();
  }

  function renderGuest() {
    const guestEl = $('authGuest');
    const userEl = $('authUser');
    if (guestEl) guestEl.style.display = 'flex';
    if (userEl) userEl.style.display = 'none';
  }

  function openModal(tab) {
    const modal = $('authModal');
    if (!modal) return;
    modal.classList.add('open');
    document.body.style.overflow = 'hidden';
    switchTab(tab || 'login');
    clearErrors();
  }

  function closeModal() {
    const modal = $('authModal');
    if (!modal) return;
    modal.classList.remove('open');
    document.body.style.overflow = '';
  }

  function switchTab(tab) {
    document.querySelectorAll('.auth-tab').forEach(t => {
      t.classList.toggle('active', t.dataset.tab === tab);
    });
    const loginForm = $('form-login');
    const signupForm = $('form-signup');
    if (loginForm) loginForm.style.display = tab === 'login' ? 'flex' : 'none';
    if (signupForm) signupForm.style.display = tab === 'signup' ? 'flex' : 'none';
    clearErrors();
  }

  function clearErrors() {
    document.querySelectorAll('.auth-error').forEach(el => (el.textContent = ''));
  }

  async function handleLogin(e) {
    e.preventDefault();
    const username = $('loginUsername').value.trim();
    const password = $('loginPassword').value;
    const errEl = $('loginError');
    const btn = $('loginSubmit');

    errEl.textContent = '';
    btn.disabled = true;
    const origText = btn.textContent;
    btn.textContent = '...';

    try {
      const res = await fetch('/api/auth/login/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      });
      const data = await res.json();
      if (res.ok) {
        currentUser = data.user;
        renderUser();
        closeModal();
      } else {
        errEl.textContent = data.detail || 'ログインに失敗しました';
      }
    } catch (_) {
      errEl.textContent = 'ネットワークエラーが発生しました';
    } finally {
      btn.disabled = false;
      btn.textContent = origText;
    }
  }

  async function handleRegister(e) {
    e.preventDefault();
    const username = $('signupUsername').value.trim();
    const email = $('signupEmail').value.trim();
    const password = $('signupPassword').value;
    const password2 = $('signupPassword2').value;
    const errEl = $('signupError');
    const btn = $('signupSubmit');

    errEl.textContent = '';

    if (password !== password2) {
      errEl.textContent = 'パスワードが一致しません';
      return;
    }

    btn.disabled = true;
    const origText = btn.textContent;
    btn.textContent = '...';

    try {
      const res = await fetch('/api/auth/register/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, email, password }),
      });
      const data = await res.json();
      if (res.ok) {
        currentUser = data.user;
        renderUser();
        closeModal();
      } else {
        errEl.textContent = data.detail || '登録に失敗しました';
      }
    } catch (_) {
      errEl.textContent = 'ネットワークエラーが発生しました';
    } finally {
      btn.disabled = false;
      btn.textContent = origText;
    }
  }

  async function handleLogout() {
    try {
      await fetch('/api/auth/logout/', { method: 'POST' });
    } catch (_) {}
    currentUser = null;
    renderGuest();
  }

  function init() {
    checkSession();

    const btnLogin = $('btnOpenLogin');
    const btnSignup = $('btnOpenSignup');
    const btnLogout = $('btnLogout');
    const modalClose = $('modalClose');
    const modal = $('authModal');
    const linkToSignup = $('linkToSignup');
    const linkToLogin = $('linkToLogin');
    const formLogin = $('form-login');
    const formSignup = $('form-signup');

    if (btnLogin) btnLogin.addEventListener('click', () => openModal('login'));
    if (btnSignup) btnSignup.addEventListener('click', () => openModal('signup'));
    if (btnLogout) btnLogout.addEventListener('click', handleLogout);
    if (modalClose) modalClose.addEventListener('click', closeModal);
    if (modal) modal.addEventListener('click', e => { if (e.target === modal) closeModal(); });
    if (linkToSignup) linkToSignup.addEventListener('click', () => switchTab('signup'));
    if (linkToLogin) linkToLogin.addEventListener('click', () => switchTab('login'));
    if (formLogin) formLogin.addEventListener('submit', handleLogin);
    if (formSignup) formSignup.addEventListener('submit', handleRegister);

    document.querySelectorAll('.auth-tab').forEach(t => {
      t.addEventListener('click', () => switchTab(t.dataset.tab));
    });

    document.addEventListener('keydown', e => {
      if (e.key === 'Escape') closeModal();
    });
  }

  return { init };
})();

document.addEventListener('DOMContentLoaded', Auth.init);
