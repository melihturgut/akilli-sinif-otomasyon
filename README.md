# Akilli Sinif Otomasyonu

MDB308 Cok Disiplinli Takim Projesi - 4. sinif bahar donemi.
Danisman: Muhammet Rasit Cesur

IoT tabanli akilli sinif enerji yonetim sistemi. Doluluk bazli aydinlatma ve HVAC kontrolu yapip enerji tasarrufu sagliyor. QR kod ile dijital yoklama ve etut modu var.

## Takim

- Melih Turgut - BM
- Samed Mete Ozmen - BM
- Serkan Yildirim - EEM
- Enes Tunahan Pakelli - EEM
- Kamil Uzun - END
- Irem Oz - END

## Ne yapiyor

Sistemin temel mantigi: sinifa kimse yoksa aydinlatma ve klima kapatiliyor. Kisi varsa varligi PIR + ultrasonik hibrit sensor ile algilaniyor. Ders programi ile senkron calisiyor, kullanici konforu icin esik degerleri de var (sicaklik 22-24, aydinlik minimum lux).

Ozellikler:
- Haftalik enerji simulasyonu (otomasyonlu vs otomasyonsuz karsilastirma)
- QR kod tabanli sinif girisi (her sirada ayri QR, bolgesel aydinlatma)
- Dijital yoklama (giris yapinca otomatik kayit)
- 1 saatlik etut modu (ders disi kullanim)
- Hoca paneli - haftalik ders programi yonetimi
- Yonetici paneli - istatistikler, ders bazli doluluk
- Isi haritasi (heatmap) - gun x saat
- CSV/Excel/PDF rapor cikti
- Bildirim sistemi
- PWA destegi (telefona uygulama gibi yuklenebiliyor)
- WebSocket ile gercek zamanli takip

## Calistirma

Lokalde:
```
pip install -r requirements.txt
python app.py
```

http://localhost:5000 acilir. Demo verisi yuklemek icin:
```
python seed_demo.py --clean
```

Telefondan erismek icin ayni wifi'da olup `http://192.168.x.x:5000` ile baglanmak gerek.

## Canli ortam

Render'a deploy edildi. URL: https://akilli-sinif-otomasyon.onrender.com

UptimeRobot 5 dakikada bir ping atiyor, uyumuyor.

## Varsayilan hesaplar

- admin / admin123 (yonetici)
- rasit / 123456 (danisman hocaya acildi)
- Demo ogrenciler icin sifre: demo123

## Teknik

Backend: Python 3.12 + Flask + Flask-SocketIO
DB: SQLite (kalici dosya)
Frontend: vanilla JS + Chart.js (bootstrap sadece sim sayfasinda)
PDF: reportlab
Excel: openpyxl
PWA: manifest + service worker

## Dosyalar

- app.py - flask uygulamasi, tum rotalar burada
- simulation.py - enerji simulasyon motoru
- live.py - QR check-in mantigi
- schedule_mgr.py - ders programi
- db.py - sqlite katmani
- auth.py - login mantigi (hoca + ogrenci ayri)
- export.py - csv/excel uretimi
- report.py - pdf rapor
- notifications.py - bildirim
- realtime.py - websocket pub/sub
- seed_demo.py - test verisi

## Matematik modeli

Rapordaki amac fonksiyonu (rapor 2.5):

```
min Z = sum sum (P_aydinlatma * L + P_klima * AC)
```

Kisitlar:
- Varlik: L + AC <= M * X
- Aydinlatma konforu: S_isik + L * delta >= S_min
- Termal: T_alt <= T <= T_ust
- Tasarruf: eta = (E_eski - E_yeni) / E_eski * 100

Guc degerleri simulation.py icinde (P_lighting_full=400W, HVAC=2000W vb).

## Sorunlar / TODO

- Render free tier kaldirdiginda DB sifirlaniyor, demo verisi otomatik yukleniyor ama gercek veri kalmiyor. Pi'ye gecince cozulecek.
- PWA telefonda guzel calisiyor ama iPhone Safari'de bazen install ikonu cikmiyor (Apple meselesi)
- Sim hizli calistirilirsa (300x) bazen websocket update'leri kaciriyor, henuz duzeltmedim

## Lisans

Akademik / egitim amacli. MDB308 kapsaminda gelistirildi.
