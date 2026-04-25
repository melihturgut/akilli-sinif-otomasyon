/* PWA Kayıt + Yükleme Komutu */
(function () {
  // 1) Service worker kaydı
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
      navigator.serviceWorker.register('/static/sw.js', { scope: '/' })
        .catch((err) => console.warn('SW kayıt hatası:', err));
    });
  }

  // 2) "Uygulamayı Yükle" davet bandı (Android/Chrome)
  let deferredPrompt = null;
  const SUPPRESS_KEY = 'pwa_install_dismissed';

  window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault();
    deferredPrompt = e;
    if (localStorage.getItem(SUPPRESS_KEY)) return;
    showInstallBanner();
  });

  function showInstallBanner() {
    if (document.getElementById('pwa-install-bar')) return;
    const bar = document.createElement('div');
    bar.id = 'pwa-install-bar';
    bar.style.cssText = `
      position: fixed; bottom: 14px; left: 14px; right: 14px;
      background: #111827; border: 1px solid #38bdf8;
      border-radius: 12px; padding: 12px 14px;
      display: flex; align-items: center; gap: 10px;
      box-shadow: 0 10px 30px rgba(0,0,0,.5); z-index: 9999;
      color: #e2e8f0; font-family: system-ui, sans-serif; font-size: 13px;
    `;
    bar.innerHTML = `
      <div style="font-size:1.5rem">📱</div>
      <div style="flex:1">
        <div style="font-weight:700">Telefonunuza ekleyin</div>
        <div style="font-size:11px;color:#6b7280">App gibi tam ekran çalışsın</div>
      </div>
      <button id="pwa-install-btn" style="background:#34d399;color:#021;
        border:none;border-radius:8px;padding:8px 14px;font-weight:700;cursor:pointer;font-size:12px">
        Ekle
      </button>
      <button id="pwa-dismiss-btn" style="background:transparent;color:#6b7280;
        border:none;font-size:18px;cursor:pointer;padding:4px 8px">✕</button>
    `;
    document.body.appendChild(bar);

    document.getElementById('pwa-install-btn').onclick = async () => {
      if (!deferredPrompt) return;
      bar.remove();
      deferredPrompt.prompt();
      const { outcome } = await deferredPrompt.userChoice;
      deferredPrompt = null;
      if (outcome !== 'accepted') localStorage.setItem(SUPPRESS_KEY, '1');
    };
    document.getElementById('pwa-dismiss-btn').onclick = () => {
      bar.remove();
      localStorage.setItem(SUPPRESS_KEY, '1');
    };
  }

  window.addEventListener('appinstalled', () => {
    console.log('Akıllı Sınıf uygulama olarak yüklendi.');
    const bar = document.getElementById('pwa-install-bar');
    if (bar) bar.remove();
  });
})();
