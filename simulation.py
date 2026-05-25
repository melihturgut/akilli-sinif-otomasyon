import random
import math
import threading
from schedule_mgr import schedule_mgr


class SmartClassroomSimulation:
    def __init__(self):
        self.lock = threading.Lock()
        self.speed = 60  # sim dakika / gerçek saniye
        self._reset_state()

    def _reset_state(self):
        self.current_minute = 0
        self.total_minutes = 7 * 24 * 60  # 1 hafta

        # Ders programı schedule_mgr modülünden okunur (rapor 2.3 — Hoca Paneli)

        # Sensör durumu
        self.temperature = 21.0
        self.humidity = 50.0
        self.motion_detected = False
        self.last_motion_minute = -999

        # Sistem durumu
        self.occupancy = 0
        self.lighting_level = 0   # 0, 30, 60, 100 (%)
        self.hvac_on = False
        self.projector_on = False
        self.projector_sleep = False  # Uyku modu (%15 guc)
        self.natural_light = 0.0      # LDR sensor (0-1)

        # Güç değerleri (Watt) — rapordaki bileşenlerle uyumlu
        self.P_lighting_full = 400
        self.P_lighting_dim = 120
        self.P_hvac = 2000
        self.P_projector = 300

        # Enerji takibi (kWh)
        self.energy_auto = 0.0
        self.energy_baseline = 0.0
        self.cost_saved_tl_tariff = 0.0  # TR 3 zamanli tarifeli kazanc

        # Günlük enerji takibi (kWh) — index 0=Pzt ... 6=Paz
        self.daily_auto = [0.0] * 7
        self.daily_baseline = [0.0] * 7

        # Grafik için geçmiş (her 30 dakikada bir nokta)
        self.history = []

        # Kontrol parametreleri (rapordaki hiyerarşik algoritma)
        self.motion_timeout = 10   # dk — dim seviyesine düş
        self.power_timeout = 15    # dk — tamamen kapat

        # Durum bayrakları
        self.running = False
        self.complete = False
        self.run_saved = False  # tamamlandığında DB'ye bir kez yazılsın

    def reset(self):
        with self.lock:
            self._reset_state()

    def step(self):
        with self.lock:
            if self.current_minute >= self.total_minutes:
                self.complete = True
                self.running = False
                return

            day = self.current_minute // (24 * 60)
            hour = (self.current_minute % (24 * 60)) // 60
            minute_in_hour = self.current_minute % 60

            current_cls = schedule_mgr.current_class(day, hour)
            in_class = current_cls is not None

            # --- Doluluk Simülasyonu ---
            if in_class:
                sh = current_cls['start']
                expected = current_cls['students']
                minutes_into_class = (hour - sh) * 60 + minute_in_hour
                if minutes_into_class < 10:
                    self.occupancy = max(1, int(expected * minutes_into_class / 10 + random.randint(-2, 2)))
                else:
                    self.occupancy = max(1, expected + random.randint(-5, 5))
            elif 8 <= hour <= 20 and day < 5:
                self.occupancy = 2 if random.random() < 0.04 else 0  # etüt
            else:
                self.occupancy = 0

            # --- PIR Sensörü Simülasyonu ---
            if self.occupancy > 0:
                self.motion_detected = random.random() > 0.05  # %95 doğruluk
                if self.motion_detected:
                    self.last_motion_minute = self.current_minute
            else:
                # Hibrit PIR + ultrasonik yapı yanlış pozitifi minimize eder
                self.motion_detected = random.random() < 0.0005
                if self.motion_detected:
                    self.last_motion_minute = self.current_minute

            # --- DHT11 Sıcaklık Simülasyonu ---
            if 6 <= hour <= 22:
                base_temp = 18 + 5 * math.sin(math.pi * (hour - 6) / 16)
            else:
                base_temp = 16.0
            heat_from_people = self.occupancy * 0.08
            if self.hvac_on:
                self.temperature += (23.0 - self.temperature) * 0.08
            else:
                self.temperature += (base_temp + heat_from_people - self.temperature) * 0.03
            self.temperature += random.uniform(-0.05, 0.05)
            self.temperature = round(max(14.0, min(36.0, self.temperature)), 1)

            # Nem
            self.humidity = 45 + self.occupancy * 0.3 + random.uniform(-1.0, 1.0)
            self.humidity = round(max(20.0, min(90.0, self.humidity)), 1)

            # --- Doğal Aydınlatma (LDR Sensör Simülasyonu) ---
            # Gündüz dışarısı parlaksa iç aydınlatma kademeli kısılır.
            # Saat bazlı doğal ışık yoğunluğu (0-1 arası): 06-18 saatlerinde parabol
            if 6 <= hour <= 18:
                # Öğleyin (12:00) zirve, sabah/akşam azalır
                natural_light = max(0.0, 1.0 - abs(hour + minute_in_hour/60 - 12) / 6.0)
            else:
                natural_light = 0.0
            # %20 hava şartı varyansı (bulutluluk simülasyonu)
            natural_light *= random.uniform(0.7, 1.0)
            self.natural_light = round(natural_light, 2)

            # --- Gece / Hafta Sonu Tam Kapatma ---
            # 22:00-06:00 arası ve hafta sonu (Cmt/Paz) — etüt modu hariç tüm yükler kapali
            is_night = hour >= 22 or hour < 6
            is_weekend = day >= 5
            force_off = (is_night or is_weekend) and self.occupancy == 0

            # --- Hiyerarşik Kontrol Algoritması ---
            minutes_since_motion = self.current_minute - self.last_motion_minute

            if force_off:
                # Gece veya hafta sonu, kimse yok -> hepsi kapali
                self.lighting_level = 0
                self.hvac_on = False
                self.projector_on = False
                self.projector_sleep = False
            elif self.occupancy > 0 or (self.motion_detected and minutes_since_motion < self.motion_timeout):
                # Aktif kullanim - dogal isiga gore aydinlatma seviyesi
                if natural_light >= 0.7:
                    self.lighting_level = 30   # Cok parlak gun -> dim yeterli
                elif natural_light >= 0.4:
                    self.lighting_level = 60   # Orta gun -> orta aydinlatma
                else:
                    self.lighting_level = 100  # Karanlik / gece dersi -> tam
                self.hvac_on = not (20.0 <= self.temperature <= 25.0)
                self.projector_on = in_class
                self.projector_sleep = False
            elif minutes_since_motion >= self.power_timeout:
                # 15. dakika — tamamen kapat
                self.lighting_level = 0
                self.hvac_on = False
                self.projector_on = False
                self.projector_sleep = False
            elif minutes_since_motion >= self.motion_timeout:
                # 10. dakika — %30 dim + projektor uyku
                self.lighting_level = 30
                self.hvac_on = False
                self.projector_sleep = self.projector_on  # Uyku modu
                self.projector_on = False

            # --- Anlık Güç Hesabı (Otomasyonlu) ---
            P_auto = 0
            if self.lighting_level == 100:
                P_auto += self.P_lighting_full
            elif self.lighting_level == 60:
                P_auto += int(self.P_lighting_full * 0.6)
            elif self.lighting_level == 30:
                P_auto += self.P_lighting_dim
            if self.hvac_on:
                P_auto += self.P_hvac
            if self.projector_on:
                P_auto += self.P_projector
            elif self.projector_sleep:
                P_auto += int(self.P_projector * 0.15)  # Uyku modu = %15 güç

            # --- Baz Hat (Otomasyon Yok): Hft içi 07-21 saatleri arası her şey açık ---
            P_baseline = 0
            if day < 5 and 7 <= hour < 21:
                P_baseline = self.P_lighting_full + self.P_hvac + self.P_projector

            # --- Enerji Birikimi (kWh = W * (1/60 saat)) ---
            e_auto_min = P_auto / (1000.0 * 60)
            e_base_min = P_baseline / (1000.0 * 60)
            self.energy_auto += e_auto_min
            self.energy_baseline += e_base_min
            self.daily_auto[day] += e_auto_min
            self.daily_baseline[day] += e_base_min

            # --- TR Tarifeli Maliyet (3 zamanlı: gunduz/puant/gece) ---
            # 06-17 gunduz: 4.0 TL/kWh
            # 17-22 puant:  6.0 TL/kWh (en pahali)
            # 22-06 gece:   2.0 TL/kWh
            if 6 <= hour < 17:
                tariff = 4.0
            elif 17 <= hour < 22:
                tariff = 6.0
            else:
                tariff = 2.0
            saved_min = e_base_min - e_auto_min
            self.cost_saved_tl_tariff += saved_min * tariff

            # --- Geçmiş Kaydı (her 30 dakikada bir) ---
            if self.current_minute % 30 == 0:
                day_short = ['Pzt', 'Sal', 'Çar', 'Per', 'Cum', 'Cmt', 'Paz'][day]
                savings_now = self.energy_baseline - self.energy_auto
                self.history.append({
                    'label': f"{day_short} {hour:02d}:{minute_in_hour:02d}",
                    'hour': hour,
                    'occupancy': self.occupancy,
                    'lighting': self.lighting_level,
                    'hvac': 1 if self.hvac_on else 0,
                    'temperature': self.temperature,
                    'power_auto': round(P_auto / 1000.0, 3),
                    'power_baseline': round(P_baseline / 1000.0, 3),
                    'energy_auto': round(self.energy_auto, 2),
                    'energy_baseline': round(self.energy_baseline, 2),
                    'savings': round(savings_now, 2),
                })

            self.current_minute += 1
            if self.current_minute >= self.total_minutes:
                self.complete = True
                self.running = False
                self._save_run_summary()

    def _save_run_summary(self):
        """Tamamlanan koşunun özetini SQLite'a yaz (kalıcı kayıt)."""
        if self.run_saved:
            return
        self.run_saved = True
        try:
            import db
            savings = self.energy_baseline - self.energy_auto
            pct = (savings / self.energy_baseline * 100) if self.energy_baseline > 0 else 0.0
            day_short = ['Pzt', 'Sal', 'Çar', 'Per', 'Cum', 'Cmt', 'Paz']
            daily = []
            for i in range(7):
                d_sav = self.daily_baseline[i] - self.daily_auto[i]
                daily.append({
                    'day': day_short[i],
                    'auto': round(self.daily_auto[i], 2),
                    'baseline': round(self.daily_baseline[i], 2),
                    'savings': round(d_sav, 2),
                })
            db.save_energy_run({
                'total_minutes': self.total_minutes,
                'energy_auto': round(self.energy_auto, 2),
                'energy_baseline': round(self.energy_baseline, 2),
                'savings_kwh': round(savings, 2),
                'savings_pct': round(pct, 1),
                'cost_saved_tl': round(savings * 4.5, 2),
                'carbon_saved_kg': round(savings * 0.4, 2),
                'daily': daily,
            })
            # Tüm hocalara bildirim
            try:
                import notifications
                notifications.notify_all_hoca(
                    'Simülasyon Tamamlandı',
                    f'%{pct:.1f} enerji tasarrufu ({savings:.1f} kWh / {savings * 4.5:.0f} TL)',
                    'success', icon='⚡', url='/admin')
            except Exception:
                pass
        except Exception as e:
            print('Run özet kaydı hatası:', e)

    def get_status(self):
        with self.lock:
            day = min(self.current_minute, self.total_minutes - 1) // (24 * 60)
            hour = (self.current_minute % (24 * 60)) // 60
            minute_in_hour = self.current_minute % 60

            savings_kwh = self.energy_baseline - self.energy_auto
            savings_pct = (savings_kwh / self.energy_baseline * 100) if self.energy_baseline > 0 else 0.0
            carbon_saved_kg = savings_kwh * 0.4    # Türkiye ortalama: 0.4 kg CO₂/kWh
            cost_saved_tl = savings_kwh * 4.5      # Ortalama birim elektrik fiyatı

            day_names = ['Pazartesi', 'Salı', 'Çarşamba', 'Perşembe', 'Cuma', 'Cumartesi', 'Pazar']
            day_short = ['Pzt', 'Sal', 'Çar', 'Per', 'Cum', 'Cmt', 'Paz']

            daily = []
            for i in range(7):
                d_sav = self.daily_baseline[i] - self.daily_auto[i]
                d_pct = (d_sav / self.daily_baseline[i] * 100) if self.daily_baseline[i] > 0 else 0.0
                daily.append({
                    'day': day_names[i],
                    'day_short': day_short[i],
                    'auto': round(self.daily_auto[i], 2),
                    'baseline': round(self.daily_baseline[i], 2),
                    'savings': round(d_sav, 2),
                    'savings_pct': round(d_pct, 1),
                    'cost_saved_tl': round(d_sav * 4.5, 2),
                    'carbon_saved_kg': round(d_sav * 0.4, 2),
                })

            return {
                'running': self.running,
                'complete': self.complete,
                'progress': round((self.current_minute / self.total_minutes) * 100, 1),
                'current_day': day_names[min(day, 6)],
                'current_time': f"{hour:02d}:{minute_in_hour:02d}",
                'occupancy': self.occupancy,
                'lighting_level': self.lighting_level,
                'hvac_on': self.hvac_on,
                'projector_on': self.projector_on,
                'projector_sleep': self.projector_sleep,
                'natural_light': self.natural_light,
                'temperature': self.temperature,
                'humidity': self.humidity,
                'motion_detected': self.motion_detected,
                'energy_auto': round(self.energy_auto, 2),
                'energy_baseline': round(self.energy_baseline, 2),
                'savings_kwh': round(savings_kwh, 2),
                'savings_pct': round(savings_pct, 1),
                'carbon_saved_kg': round(carbon_saved_kg, 2),
                'cost_saved_tl': round(cost_saved_tl, 2),
                'cost_saved_tl_tariff': round(self.cost_saved_tl_tariff, 2),
                'speed': self.speed,
                'history': self.history[-200:],
                'daily': daily,
            }

    def configure(self, config):
        with self.lock:
            if 'speed' in config:
                self.speed = max(1, min(300, int(config['speed'])))
            if 'motion_timeout' in config:
                self.motion_timeout = max(1, int(config['motion_timeout']))
            if 'power_timeout' in config:
                self.power_timeout = max(1, int(config['power_timeout']))
