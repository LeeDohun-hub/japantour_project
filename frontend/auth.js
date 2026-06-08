const Auth = (() => {
  let currentUser = null;

  const $ = id => document.getElementById(id);

  function getCsrfToken() {
    return document.cookie.split(';')
      .map(c => c.trim())
      .find(c => c.startsWith('csrftoken='))
      ?.split('=')[1] ?? '';
  }

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
    const name = (currentUser.display_name || currentUser.username || '').trim();
    if (nameEl) nameEl.textContent = name;
    if (avatarEl) avatarEl.textContent = name.charAt(0).toUpperCase();
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
    const username = ($('loginEmail') || $('loginUsername'))?.value.trim() || '';
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
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
        credentials: 'same-origin',
        body: JSON.stringify({ email: username, username, password }),
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
    const display_name = ($('signupDisplayName') || $('signupUsername'))?.value.trim() || '';
    const email = $('signupEmail').value.trim();
    const password = $('signupPassword').value;
    const password2 = $('signupPassword2').value;
    const terms = $('signupTerms')?.checked ?? true;
    const errEl = $('signupError');
    const btn = $('signupSubmit');

    errEl.textContent = '';

    if (!display_name) {
      errEl.textContent = '表示名を入力してください';
      return;
    }
    if (!email) {
      errEl.textContent = 'メールアドレスを入力してください';
      return;
    }
    if (password.length < 8) {
      errEl.textContent = 'パスワードは8文字以上必要です';
      return;
    }
    if (password !== password2) {
      errEl.textContent = 'パスワードが一致しません';
      return;
    }
    if ($('signupTerms') && !terms) {
      errEl.textContent = '利用規約への同意が必要です';
      return;
    }

    btn.disabled = true;
    const origText = btn.textContent;
    btn.textContent = '...';

    try {
      const res = await fetch('/api/auth/register/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
        credentials: 'same-origin',
        body: JSON.stringify({
          display_name,
          email,
          password,
          password_confirm: password2,
          terms_accepted: terms,
        }),
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
      await fetch('/api/auth/logout/', {
        method: 'POST',
        headers: { 'X-CSRFToken': getCsrfToken() },
        credentials: 'same-origin',
      });
    } catch (_) {}
    currentUser = null;
    renderGuest();
  }

  function openDeleteModal() {
    const modal = $('deleteAccountModal');
    if (!modal) return;
    const isOAuth = currentUser?.username?.startsWith('google_') || currentUser?.username?.startsWith('line_');
    const pwField = $('deletePasswordField');
    if (pwField) pwField.style.display = isOAuth ? 'none' : 'block';
    const pwInput = $('deletePasswordInput');
    if (pwInput) pwInput.value = '';
    const errEl = $('deleteAccountError');
    if (errEl) errEl.textContent = '';
    modal.style.display = 'flex';
    document.body.style.overflow = 'hidden';
  }

  function closeDeleteModal() {
    const modal = $('deleteAccountModal');
    if (!modal) return;
    modal.style.display = 'none';
    document.body.style.overflow = '';
  }

  async function handleDeleteAccount() {
    const errEl = $('deleteAccountError');
    const btn = $('btnDeleteConfirm');
    const isOAuth = currentUser?.username?.startsWith('google_') || currentUser?.username?.startsWith('line_');
    const password = isOAuth ? undefined : $('deletePasswordInput')?.value;

    if (!isOAuth && !password) {
      if (errEl) errEl.textContent = 'パスワードを入力してください';
      return;
    }

    if (errEl) errEl.textContent = '';
    btn.disabled = true;
    const origText = btn.textContent;
    btn.textContent = '...';

    try {
      const res = await fetch('/api/auth/delete-account/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
        credentials: 'same-origin',
        body: JSON.stringify(isOAuth ? {} : { password }),
      });
      const data = await res.json();
      if (res.ok) {
        closeDeleteModal();
        currentUser = null;
        renderGuest();
        // 탈퇴 완료 후 페이지 새로고침
        window.location.reload();
      } else {
        if (errEl) errEl.textContent = data.detail || '退会処理に失敗しました';
      }
    } catch (_) {
      if (errEl) errEl.textContent = 'ネットワークエラーが発生しました';
    } finally {
      btn.disabled = false;
      btn.textContent = origText;
    }
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

    const btnDeleteAccount = $('btnDeleteAccount');
    const btnDeleteConfirm = $('btnDeleteConfirm');
    const btnDeleteCancel = $('btnDeleteCancel');
    const deleteModal = $('deleteAccountModal');
    if (btnDeleteAccount) btnDeleteAccount.addEventListener('click', openDeleteModal);
    if (btnDeleteConfirm) btnDeleteConfirm.addEventListener('click', handleDeleteAccount);
    if (btnDeleteCancel) btnDeleteCancel.addEventListener('click', closeDeleteModal);
    if (deleteModal) deleteModal.addEventListener('click', e => { if (e.target === deleteModal) closeDeleteModal(); });

    document.querySelectorAll('.auth-tab').forEach(t => {
      t.addEventListener('click', () => switchTab(t.dataset.tab));
    });

    document.addEventListener('keydown', e => {
      if (e.key === 'Escape') { closeModal(); closeDeleteModal(); }
    });
  }

  return { init };
})();

document.addEventListener('DOMContentLoaded', Auth.init);
