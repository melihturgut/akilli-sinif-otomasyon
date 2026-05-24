# Akilli Sinif Otomasyonu

MDB308 Cok Disiplinli Takim Projesi - 4. sinif bahar donemi.
Danisman: Muhammet Rasit Cesur

IoT tabanli akilli sinif enerji yonetim sistemi. Doluluk bazli aydinlatma ve HVAC kontrolu yapip enerji tasarrufu sagliyor. QR kod ile dijital yoklama ve etut modu var. Web tabanli, telefondan PWA olarak yuklenebiliyor.

## Canli URL

**https://akilli-sinif-otomasyon.onrender.com**

Render'a deploy edildi, UptimeRobot ile 7/24 uyaniik. DB Turso'da (kalici cloud SQLite).

## Takim

- Melih Turgut - BM
- Samed Mete Ozmen - BM
- Serkan Yildirim - EEM
- Enes Tunahan Pakelli - EEM
- Kamil Uzun - END
- Irem Oz - END

## Ozellikler

### Simulasyon
- Haftalik enerji tuketim simulasyonu (1 dk cozunurluklu)
- Hiyerarsik kontrol algoritmasi: hareket yoksa 10 dk → dim, 15 dk → kapali
- PIR + ultrasonik hibrit doluluk algilama (simulasyonda)
- DHT11 sicaklik/nem benzetimi
- Otomasyonlu vs otomasyonsuz karsilastirma
- Gun bazinda tasarruf dokumu
- Ortalama %85-89 tasarruf orani

### QR Tabanli Sinif Girisi
- 3 bolgeli aydinlatma (On/Orta/Arka) - sadece dolu bolgenin isigi yanar
- Telefon QR okutarak check-in
- 1 saatlik etut sayaci
- Otomatik yoklama kaydi

### 3 Katmanli Yoklama Korumasi (Sahtekarliga karsi)
1. **Hesap girisi zorunlu** - sadece kendi hesabindan giris atilabilir
2. **Ders saati kontrolu** - aktif ders varken normal, disinda etut modu
3. **GPS konum kontrolu** - hocanin ayarladigi sinif yariçapinda olunmali

### Hoca Paneli (sifreli)
- Haftalik ders programi CRUD
- Anlik degisiklik (ders iptal et / geri ac)
- Sinif konumu ayari (GPS koordinati)
- Sifre degistirme

### Ogrenci Paneli (sifreli)
- Profil, yoklama gecmisi
- Anlik sinif verimliligi (kac bolge acik, anlik guc)
- Haftalik ders programi
- Kisisel tasarruf katkisi gosterimi
- Hesap kayit / giris

### Yonetici Paneli (sifreli)
- Toplam yoklama istatistikleri
- Ders bazli doluluk analizi
- Ogrenci no ile yoklama arama
- Gecmis simulasyon kosmalari
- CSV / Excel / PDF rapor disa aktarma

### Analitik Sayfasi
- Gun x Saat isi haritasi (heatmap)
- Gercek doluluk vs planli ders programi karsilastirmasi
- Insights: en yogun saat, en bos saat, ortalama yogunluk

### Canli Panel
- 3 bolgenin anlik durumu
- Aktif ogrenci listesi (anonim chip'ler)
- Dijital yoklama kaydi
- WebSocket ile gercek zamanli guncelleme

### Bildirim Sistemi
- In-app cani simgesi (sag ust kose)
- Tarayici native bildirimleri
- Hocaya: sim tamamlandi, ders iptal vb
- Ogrenciye: yoklama alindi, sure yenilendi

### PDF Rapor
- Tek tikla 7 sayfalik profesyonel rapor
- Kapak + terimler sozlugu + KPI + son sim + ders doluluk + yoklama + sim gecmisi
- DejaVu Sans font ile Turkce karakter destegi

### CSV / Excel Disa Aktarma
- Endustri ekibi icin pandas/Minitab uyumlu cikti
- 5 sayfali Excel (ozet, yoklama, kosmalar, ders, gunluk)
- Ayri CSV'ler de mevcut

### PWA Destegi
- Telefonda "Ana Ekrana Ekle" → uygulama gibi calisir
- Service worker ile cache + offline destegi
- Maskable adaptif ikonlar

### WebSocket Gercek Zamanli
- QR check-in olur olmaz panel hemen guncellenir
- Sim calistirirken canli grafikler akar
- Hoca paneli degisiklikleri tum oturumlara aninda yansir

## Kullanilan Teknolojiler

- **Backend:** Python 3.12, Flask, Flask-SocketIO
- **DB:** Turso (cloud SQLite, kalici) + lokal SQLite (gelistirme)
- **Frontend:** Vanilla JS, Chart.js, Bootstrap 5 (sadece sim sayfasinda)
- **PDF:** ReportLab + DejaVu Sans font
- **Excel:** openpyxl
- **PWA:** Web App Manifest + Service Worker
- **Auth:** Werkzeug password hashing + Flask sessions
- **Realtime:** WebSocket (Flask-SocketIO)
- **Deploy:** Render.com (free tier)
- **Uptime:** UptimeRobot (5 dk ping)

## Calistirma

### Lokalde

```bash
pip install -r requirements.txt
python app.py
```

http://localhost:5000 acilir. Telefondan erismek icin ayni wifi'da `http://192.168.x.x:5000`.

### Demo verisi yuklemek
```bash
python seed_demo.py --clean
```

30 ogrenci + 300 yoklama olayi + 5 sim kosmasi yukler.

### Cloud (Render) icin
- Repoyu Render'a baglayinca otomatik deploy oluyor
- `render.yaml` icindeki ayarlar uygulaniyor
- DB icin TURSO_DATABASE_URL ve TURSO_AUTH_TOKEN env varsa Turso, yoksa lokal SQLite

## Varsayilan Hesaplar

- **admin / admin123** (yonetici - tam yetki)
- **rasit / 123456** (danisman hocaya acildi)
- **Demo ogrenciler:** seed_demo.py 30 ogrenci olusturur, hepsinin sifresi `demo123`

## Sayfalar

| URL | Aciklama | Yetki |
|---|---|---|
| `/` | Simulasyon dashboard | Acik |
| `/hoca` | Ders programi yonetimi + sinif konumu | Hoca girisi |
| `/admin` | Yonetici paneli + export | Hoca girisi |
| `/analitik` | Heatmap isi haritasi | Hoca girisi |
| `/panel` | Canli sinif paneli | Acik |
| `/qr` | Yazdirilabilir QR kodlari | Acik |
| `/giris?bolge=on` | QR check-in (login + GPS) | Ogrenci girisi |
| `/ogrenci` | Ogrenci profili + tasarruf | Ogrenci girisi |
| `/ogrenci/kayit` | Yeni ogrenci hesabi | Acik |
| `/ogrenci/giris` | Ogrenci girisi | Acik |
| `/login` | Hoca / yonetici girisi | Acik |

## Dosyalar

```
app.py              - Flask uygulamasi, tum rotalar
simulation.py       - Enerji simulasyon motoru
live.py             - QR check-in + 3 katmanli koruma
schedule_mgr.py     - Ders programi yonetimi
db.py               - DB katmani (lokal SQLite + Turso destegi)
auth.py             - Hoca + ogrenci login mantigi
export.py           - CSV / Excel uretimi
report.py           - PDF rapor uretimi
notifications.py    - Bildirim sistemi
realtime.py         - WebSocket pub/sub
seed_demo.py        - Demo veri yukleyici
render.yaml         - Render deploy konfigurasyonu
requirements.txt    - Python bagimliliklari
internet.bat        - Lokalde Cloudflare tunnel ile public URL
run.bat             - Windows lokal baslatici

templates/
  index.html        - Sim dashboard
  hoca.html         - Hoca paneli
  admin.html        - Yonetici paneli
  analitik.html     - Heatmap
  panel.html        - Canli sinif paneli
  qr.html           - QR kodlar
  giris.html        - QR check-in
  ogrenci.html      - Ogrenci paneli
  ogrenci_giris.html - Ogrenci kayit/giris
  login.html        - Hoca girisi

static/
  style.css         - Ortak dark tema
  manifest.json     - PWA manifest
  sw.js             - Service worker
  pwa.js            - PWA kayit + tooltip
  notifications.js  - Bildirim UI
  icons/            - PWA ikonlari (192, 512, maskable...)
  fonts/            - DejaVu Sans (PDF Turkce destegi)
```

## DB Semasi

```sql
attendance          (yoklama olaylari - kalici)
  id, student_no, zone, action, timestamp, class_id, latitude, longitude, mode

active_checkins     (su an sinifta olanlar)
  student_no, zone, checkin_time, expires_at

energy_runs         (tamamlanan sim kosmalari)
  id, finished_at, energy_auto, energy_baseline, savings_kwh, ..., daily_json

users               (hocalar)
  id, username, password_hash, display_name, role, created_at

students            (ogrenciler)
  student_no, password_hash, name, created_at, last_login

notifications       (bildirimler)
  id, user_type, user_id, title, message, severity, icon, url, read, created_at

app_settings        (sinif konumu vb. ayarlar)
  key, value
```

## Matematik Modeli (Rapor 2.5)

Amac fonksiyonu:
```
min Z = sum sum (P_aydinlatma * L + P_klima * AC)
```

Kisitlar:
- Varlik: L + AC <= M * X
- Aydinlatma konforu: S_isik + L * delta >= S_min
- Termal konfor: T_alt <= T <= T_ust

Tasarruf formulu: `eta = (E_eski - E_yeni) / E_eski * 100`

Guc degerleri `simulation.py` icinde:
- Aydinlatma tam: 400 W, dim (%30): 120 W
- HVAC: 2000 W
- Projeksiyon: 300 W
- Birim elektrik: 4.5 TL/kWh
- Karbon: 0.4 kg CO2/kWh (TR ortalamasi)

## Sorunlar / TODO

- Render free tier 15 dk inaktiflikte uyuyordu, UptimeRobot ile cozuldu
- Turso entegrasyonundan once Render her deploy'da SQLite DB siliyordu, simdi kalici
- PWA telefonda guzel calisiyor ama iPhone Safari'de install ikonu cikmiyor (Apple meselesi)
- Sim hizli calistirilirsa (300x) bazen websocket update'leri kaciriyor, henuz duzeltmedim
- GPS spoofing ile yoklama hilesi tam onlenmedi (raporda mevcut acik olarak belirtildi)

## Lisans

Akademik / egitim amacli. MDB308 kapsaminda gelistirildi.
