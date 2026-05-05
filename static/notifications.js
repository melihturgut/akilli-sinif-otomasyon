/* Bildirim Sistemi — UI + WebSocket + Tarayıcı bildirimleri.
 * Bu script yüklendiğinde otomatik olarak:
 *  - Sayfaya çan ikonu enjekte eder (sağ üst)
 *  - /api/notifications çağırıp listeyi doldurur
 *  - WebSocket 'notification' eventini dinler
 *  - Tarayıcı native bildirimi (tab arkadaysa) gönderir
 */
(function () {
  'use strict';

  const SEVERITY_COLORS = {
    info:    '#38bdf8',
    success: '#34d399',
    warning: '#fbbf24',
    danger:  '#f87171',
  };

  // ── DOM: çan + dropdown ────────────────────────────────────────
  function injectStyles() {
    if (document.getElementById('notif-styles')) return;
    const style = document.createElement('style');
    style.id = 'notif-styles';
    style.textContent = `
      #notif-bell {
        position: fixed; top: 14px; right: 14px; z-index: 9000;
        background: rgba(15, 23, 42, .85); backdrop-filter: blur(8px);
        border: 1px solid #1f2a40; border-radius: 50%;
        width: 40px; height: 40px;
        display: flex; align-items: center; justify-content: center;
        cursor: pointer; box-shadow: 0 4px 14px rgba(0,0,0,.4);
        font-size: 1.2rem; user-select: none;
        transition: transform .15s, background .15s;
      }
      #notif-bell:hover { transform: scale(1.08); background: rgba(15, 23, 42, 1); }
      #notif-bell.has-unread { animation: bellShake 1.5s ease-in-out 2; }
      @keyframes bellShake {
        0%, 100% { transform: rotate(0); }
        15% { transform: rotate(-15deg); }
        30% { transform: rotate(12deg); }
        45% { transform: rotate(-8deg); }
        60% { transform: rotate(5deg); }
        75% { transform: rotate(-2deg); }
      }
      #notif-badge {
        position: absolute; top: -4px; right: -4px;
        background: #dc2626; color: #fff;
        font-size: 10px; font-weight: 800;
        min-width: 18px; height: 18px; padding: 0 4px;
        border-radius: 9px; display: none;
        align-items: center; justify-content: center;
        border: 2px solid #080c14;
      }
      #notif-badge.show { display: flex; }
      #notif-panel {
        position: fixed; top: 60px; right: 14px;
        width: min(360px, calc(100vw - 28px));
        max-height: calc(100vh - 80px);
        background: #111827; border: 1px solid #1f2a40; border-radius: 12px;
        box-shadow: 0 12px 36px rgba(0,0,0,.55);
        z-index: 8999; display: none;
        flex-direction: column; overflow: hidden;
        font-family: 'Segoe UI', system-ui, sans-serif;
      }
      #notif-panel.open { display: flex; }
      .notif-header {
        padding: 12px 14px;
        border-bottom: 1px solid #1f2a40;
        display: flex; justify-content: space-between; align-items: center;
      }
      .notif-header b { font-size: .9rem; color: #e2e8f0; }
      .notif-header button {
        background: transparent; border: 0; color: #6b7280;
        font-size: .72rem; cursor: pointer;
      }
      .notif-header button:hover { color: #38bdf8; }
      .notif-list {
        overflow-y: auto; flex: 1; padding: 4px 0;
      }
      .notif-item {
        padding: 10px 14px; cursor: pointer;
        border-left: 3px solid transparent;
        border-bottom: 1px solid #1f2a40;
        transition: background .12s;
      }
      .notif-item:hover { background: rgba(255,255,255,.025); }
      .notif-item.unread { background: rgba(56,189,248,.05); }
      .notif-title {
        font-weight: 700; font-size: .82rem; color: #e2e8f0;
        display: flex; align-items: center; gap: 6px;
      }
      .notif-msg { font-size: .72rem; color: #9ca3af; margin-top: 3px; }
      .notif-time { font-size: .62rem; color: #6b7280; margin-top: 3px; }
      .notif-empty { padding: 30px 14px; text-align: center; color: #6b7280; font-size: .82rem; }
      .notif-toast {
        position: fixed; top: 14px; right: 64px; z-index: 9100;
        background: #111827; border-left: 3px solid #38bdf8;
        border-radius: 8px; padding: 10px 14px;
        max-width: 320px;
        box-shadow: 0 12px 36px rgba(0,0,0,.6);
        font-family: 'Segoe UI', system-ui, sans-serif;
        color: #e2e8f0; font-size: .82rem;
        animation: toastSlide .35s ease-out;
        cursor: pointer;
      }
      @keyframes toastSlide {
        from { transform: translateX(40px); opacity: 0; }
        to   { transform: translateX(0); opacity: 1; }
      }
      .notif-toast .t { font-weight: 700; }
      .notif-toast .m { color: #9ca3af; font-size: .72rem; margin-top: 2px; }
    `;
    document.head.appendChild(style);
  }

  function buildBell() {
    if (document.getElementById('notif-bell')) return;
    const bell = document.createElement('div');
    bell.id = 'notif-bell';
    bell.innerHTML = '🔔<span id="notif-badge">0</span>';
    bell.onclick = togglePanel;
    document.body.appendChild(bell);

    const panel = document.createElement('div');
    panel.id = 'notif-panel';
    panel.innerHTML = `
      <div class="notif-header">
        <b>Bildirimler</b>
        <button onclick="window.__notifMarkAllRead()">Hepsini okundu say</button>
      </div>
      <div class="notif-list" id="notif-list">
        <div class="notif-empty">Yükleniyor...</div>
      </div>`;
    document.body.appendChild(panel);

    // Panel dışına tıklayınca kapansın
    document.addEventListener('click', (e) => {
      if (!panel.contains(e.target) && !bell.contains(e.target)) {
        panel.classList.remove('open');
      }
    });
  }

  // ── Veri çekme ─────────────────────────────────────────────────
  function fetchAndRender() {
    fetch('/api/notifications?limit=30')
      .then(r => r.status === 401 ? null : r.json())
      .then(d => {
        if (!d || !d.ok) return;
        renderList(d.items);
        updateBadge(d.unread);
      })
      .catch(() => {});
  }

  function updateBadge(count) {
    const badge = document.getElementById('notif-badge');
    if (!badge) return;
    badge.textContent = count > 99 ? '99+' : count;
    badge.classList.toggle('show', count > 0);
    document.getElementById('notif-bell').classList.toggle('has-unread', count > 0);
    // Tab title'a sayı ekle
    const base = document.title.replace(/^\(\d+\)\s*/, '');
    document.title = count > 0 ? `(${count}) ${base}` : base;
  }

  function escapeHtml(s) {
    return String(s ?? '').replace(/[&<>"']/g,
      c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  }

  function fmtTime(ts) {
    const d = new Date(ts * 1000);
    const now = new Date();
    const diff = (now - d) / 1000;
    if (diff < 60)    return Math.floor(diff) + ' sn önce';
    if (diff < 3600)  return Math.floor(diff / 60) + ' dk önce';
    if (diff < 86400) return Math.floor(diff / 3600) + ' saat önce';
    return d.toLocaleDateString('tr-TR') + ' ' +
           d.toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' });
  }

  function renderList(items) {
    const list = document.getElementById('notif-list');
    if (!items || !items.length) {
      list.innerHTML = '<div class="notif-empty">📭 Henüz bildirim yok</div>';
      return;
    }
    list.innerHTML = items.map(n => {
      const color = SEVERITY_COLORS[n.severity] || SEVERITY_COLORS.info;
      const icon = n.icon ? escapeHtml(n.icon) : '🔔';
      return `<div class="notif-item ${n.read ? '' : 'unread'}"
                   style="border-left-color:${color}"
                   data-id="${n.id}" data-url="${escapeHtml(n.url || '')}">
        <div class="notif-title">
          <span>${icon}</span>
          <span>${escapeHtml(n.title)}</span>
        </div>
        ${n.message ? `<div class="notif-msg">${escapeHtml(n.message)}</div>` : ''}
        <div class="notif-time">${fmtTime(n.created_at)}</div>
      </div>`;
    }).join('');

    // Tıklama: okundu işaretle + url varsa yönlendir
    list.querySelectorAll('.notif-item').forEach(el => {
      el.onclick = () => {
        const id = el.dataset.id;
        const url = el.dataset.url;
        fetch(`/api/notifications/${id}/read`, { method: 'POST' }).then(() => fetchAndRender());
        if (url) setTimeout(() => { window.location.href = url; }, 100);
      };
    });
  }

  function togglePanel() {
    const panel = document.getElementById('notif-panel');
    panel.classList.toggle('open');
    if (panel.classList.contains('open')) fetchAndRender();
  }

  window.__notifMarkAllRead = function () {
    fetch('/api/notifications/read-all', { method: 'POST' }).then(() => fetchAndRender());
  };

  // ── Anlık bildirim — toast + browser native ────────────────────
  function showToast(n) {
    const color = SEVERITY_COLORS[n.severity] || SEVERITY_COLORS.info;
    const toast = document.createElement('div');
    toast.className = 'notif-toast';
    toast.style.borderLeftColor = color;
    toast.innerHTML = `
      <div class="t">${n.icon || '🔔'} ${escapeHtml(n.title)}</div>
      ${n.message ? `<div class="m">${escapeHtml(n.message)}</div>` : ''}
    `;
    toast.onclick = () => {
      if (n.url) window.location.href = n.url;
      toast.remove();
    };
    document.body.appendChild(toast);
    setTimeout(() => { toast.style.opacity = '0'; toast.style.transition = 'opacity .4s'; }, 4500);
    setTimeout(() => toast.remove(), 5000);
  }

  function showBrowserNotif(n) {
    if (!('Notification' in window)) return;
    if (Notification.permission !== 'granted') return;
    if (!document.hidden) return;  // Tab açıksa toast yeterli
    try {
      const notif = new Notification(`${n.icon || '🔔'} ${n.title}`, {
        body: n.message || '',
        icon: '/static/icons/icon-192.png',
        badge: '/static/icons/icon-192.png',
        tag: 'akilli-sinif-' + n.id,
      });
      notif.onclick = () => {
        window.focus();
        if (n.url) window.location.href = n.url;
        notif.close();
      };
    } catch (e) {}
  }

  function requestPermission() {
    if (!('Notification' in window)) return;
    if (Notification.permission === 'default') {
      // Sayfa ilk yüklendiğinde değil, kullanıcı çana tıkladığında iste
      const bell = document.getElementById('notif-bell');
      if (!bell) return;
      bell.addEventListener('click', () => {
        if (Notification.permission === 'default') Notification.requestPermission();
      }, { once: true });
    }
  }

  // ── WebSocket dinleyici ────────────────────────────────────────
  function setupWebSocket() {
    if (!window.io) return;
    const sock = window.io();
    sock.on('notification', (n) => {
      // Anlık görsel
      showToast(n);
      showBrowserNotif(n);
      // Listeyi tazele
      fetchAndRender();
    });
  }

  // ── Başlat ─────────────────────────────────────────────────────
  function init() {
    // Sadece giriş yapmış kullanıcılar için
    fetch('/api/notifications?limit=1')
      .then(r => {
        if (r.status === 401) return null;
        return r.json();
      })
      .then(d => {
        if (!d || !d.ok) return;
        injectStyles();
        buildBell();
        fetchAndRender();
        setupWebSocket();
        requestPermission();
        // Periyodik tazeleme (WS yedeklemesi)
        setInterval(fetchAndRender, 60000);
      })
      .catch(() => {});
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
