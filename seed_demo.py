# Demo verisi yukleyici - test/sunum icin
# kullanim: python seed_demo.py --clean
import sys
import io

# Windows console için UTF-8 çıktı zorla
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import argparse
import json
import random
import sqlite3
import time
from werkzeug.security import generate_password_hash

import db
from schedule_mgr import schedule_mgr


# --- Türkçe ad havuzu

FIRST_NAMES = [
    'Ahmet', 'Mehmet', 'Mustafa', 'Ali', 'Hüseyin', 'İbrahim', 'Hasan', 'Murat',
    'Emre', 'Burak', 'Mert', 'Ozan', 'Yusuf', 'Berkay', 'Kerem', 'Furkan',
    'Cem', 'Onur', 'Tarık', 'Ufuk', 'Volkan', 'Yiğit', 'Kemal', 'Çağrı',
    'Ayşe', 'Fatma', 'Zeynep', 'Elif', 'Selin', 'Esra', 'Sema', 'İrem',
    'Burcu', 'Eda', 'Tuğçe', 'Gül', 'Sıla', 'Yasemin', 'Lale', 'Nilgün',
    'Rabia', 'Deniz', 'Pınar', 'Beste', 'Defne', 'Aslı',
]

LAST_NAMES = [
    'Yılmaz', 'Kaya', 'Demir', 'Çelik', 'Şahin', 'Yıldız', 'Yıldırım', 'Öztürk',
    'Aydın', 'Özdemir', 'Arslan', 'Doğan', 'Kılıç', 'Aslan', 'Çetin', 'Kara',
    'Koç', 'Kurt', 'Özkan', 'Şimşek', 'Polat', 'Akın', 'Erdoğan', 'Korkmaz',
    'Acar', 'Güneş', 'Tunç', 'Bulut', 'Türk', 'Sezer',
]

DEMO_PASSWORD = 'demo123'  # tüm demo öğrencileri ortak şifre


# --- Temizleme

def clean_demo_data():
    """Demo verilerini temizle. Gerçek kullanıcıları (admin, rasit) korur."""
    c = db._conn()
    c.execute("DELETE FROM attendance")
    c.execute("DELETE FROM active_checkins")
    c.execute("DELETE FROM energy_runs")
    c.execute("DELETE FROM students")
    c.commit()
    c.close()
    print('Eski demo verisi temizlendi')


# --- Öğrenciler

def seed_students(n=30):
    pw_hash = generate_password_hash(DEMO_PASSWORD)
    used = set()
    created = 0
    while created < n:
        sno = f"202{random.randint(10000, 99999)}"
        if sno in used:
            continue
        used.add(sno)
        name = f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
        if db.create_student(sno, pw_hash, name):
            created += 1
    print(f'{created} öğrenci oluşturuldu (şifre: {DEMO_PASSWORD})')
    return list(used)


# --- Yoklama olayları

def seed_attendance(n=300):
    """Son 28 günde ders saatlerine denk gelen yoklama olayları oluştur."""
    c = db._conn()
    students = [r['student_no'] for r in c.execute("SELECT student_no FROM students").fetchall()]
    if not students:
        c.close()
        print('  ⚠ Öğrenci yok — önce öğrenci ekleyin')
        return

    classes = schedule_mgr.list_all()
    zones = ['on', 'orta', 'arka']
    now = time.time()
    inserted = 0
    target = n

    # Son 28 gün boyunca ders zamanlarına check-in serpiştir
    for day_offset in range(28, 0, -1):
        sample_time = now - day_offset * 86400
        local = time.localtime(sample_time)
        weekday = local.tm_wday  # 0=Pzt

        days_classes = [cls for cls in classes
                        if cls.get('active', True) and cls['day'] == weekday]
        if not days_classes:
            continue

        for cls in days_classes:
            # Her dersin %70-95'i dolu olsun
            attendance_ratio = random.uniform(0.70, 0.95)
            n_attendees = max(3, int(cls['students'] * attendance_ratio))
            attendees = random.sample(students, min(n_attendees, len(students)))

            for sno in attendees:
                # Ders başına yakın bir saat
                checkin_offset = random.randint(-5, 15)  # ders öncesi 5 dk - sonrası 15 dk
                t = sample_time - (local.tm_hour - cls['start']) * 3600
                t -= local.tm_min * 60 + local.tm_sec
                t += checkin_offset * 60
                zone = random.choices(zones, weights=[0.45, 0.35, 0.20])[0]
                action = 'giris' if random.random() > 0.05 else 'yenileme'
                c.execute("INSERT INTO attendance (student_no, zone, action, timestamp) VALUES (?,?,?,?)",
                          (sno, zone, action, t))
                inserted += 1

                # %30 ihtimal çıkış da yapsın
                if random.random() < 0.30:
                    checkout_t = t + random.randint(50, 110) * 60
                    c.execute("INSERT INTO attendance (student_no, zone, action, timestamp) VALUES (?,?,?,?)",
                              (sno, '-', 'cikis', checkout_t))
                    inserted += 1

                if inserted >= target:
                    break
            if inserted >= target:
                break
        if inserted >= target:
            break

    c.commit()
    c.close()
    print(f'{inserted} yoklama olayı oluşturuldu')


# --- Aktif check-in'ler (sanki şu an sınıfta gibi)

def seed_active_checkins(n=4):
    c = db._conn()
    students = [r['student_no'] for r in c.execute("SELECT student_no FROM students LIMIT 10").fetchall()]
    if not students:
        c.close()
        return
    zones = ['on', 'orta', 'arka']
    now = time.time()
    chosen = random.sample(students, min(n, len(students)))
    for sno in chosen:
        zone = random.choice(zones)
        checkin = now - random.randint(5, 45) * 60
        expires = checkin + 3600
        c.execute("""INSERT INTO active_checkins (student_no, zone, checkin_time, expires_at)
                     VALUES (?,?,?,?)
                     ON CONFLICT(student_no) DO UPDATE SET
                       zone=excluded.zone, checkin_time=excluded.checkin_time,
                       expires_at=excluded.expires_at""",
                  (sno, zone, checkin, expires))
    c.commit()
    c.close()
    print(f'{len(chosen)} aktif check-in (sanki şu an sınıftalar)')


# --- Simülasyon koşmaları

def seed_runs(n=5):
    c = db._conn()
    now = time.time()
    day_short = ['Pzt', 'Sal', 'Çar', 'Per', 'Cum', 'Cmt', 'Paz']

    for i in range(n):
        # Her koşma 1-30 gün öncesinde
        finished = now - random.randint(1, 30) * 86400
        finished_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(finished))

        # Tasarruf %75-93 arası varyans (gerçekçi)
        savings_pct = round(random.uniform(75, 93), 1)
        baseline = round(random.uniform(180, 200), 2)
        auto = round(baseline * (1 - savings_pct / 100), 2)
        savings = round(baseline - auto, 2)
        cost = round(savings * 4.5, 2)
        carbon = round(savings * 0.4, 2)

        # Günlük dökümü (Cmt/Paz boş)
        daily = []
        for d in range(7):
            if d >= 5:
                daily.append({'day': day_short[d], 'auto': 0, 'baseline': 0, 'savings': 0})
            else:
                d_base = round(baseline / 5, 2)
                d_auto = round(d_base * (1 - savings_pct / 100) * random.uniform(0.85, 1.15), 2)
                daily.append({
                    'day': day_short[d],
                    'auto': d_auto,
                    'baseline': d_base,
                    'savings': round(d_base - d_auto, 2),
                })

        c.execute("""INSERT INTO energy_runs
            (finished_at, total_minutes, energy_auto, energy_baseline, savings_kwh,
             savings_pct, cost_saved_tl, carbon_saved_kg, daily_json)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            (finished_str, 7*24*60, auto, baseline, savings, savings_pct, cost, carbon,
             json.dumps(daily, ensure_ascii=False)))

    c.commit()
    c.close()
    print(f'{n} simülasyon koşma kaydı oluşturuldu')


# --- Ana

def main():
    parser = argparse.ArgumentParser(description='Akıllı Sınıf — Demo veri yükleyici')
    parser.add_argument('--clean', action='store_true', help='Önce mevcut veriyi sil')
    parser.add_argument('--students', type=int, default=30)
    parser.add_argument('--attendance', type=int, default=300)
    parser.add_argument('--runs', type=int, default=5)
    parser.add_argument('--active', type=int, default=4, help='Aktif (sınıfta olan) öğrenci sayısı')
    args = parser.parse_args()

    db.init()
    print('=' * 55)
    print('  Akıllı Sınıf Otomasyonu — Demo Verisi Yükleyici')
    print('=' * 55)

    if args.clean:
        clean_demo_data()

    seed_students(args.students)
    seed_attendance(args.attendance)
    seed_active_checkins(args.active)
    seed_runs(args.runs)

    # Özet
    s = db.attendance_stats()
    print()
    print('Veritabanı durumu:')
    print(f"  Öğrenci sayısı  : {db.student_count()}")
    print(f"  Yoklama olayı   : {s['total_events']}")
    print(f"  Benzersiz öğr.  : {s['unique_students']}")
    print(f"  Bugünkü giriş   : {s['today_checkins']}")
    print(f"  Sim koşma sayısı: {len(db.list_energy_runs(limit=999))}")
    print(f"  Aktif check-in  : {len(db.list_active_checkins())}")
    print()
    print('Demo verisi yuklendi. Sayfayi yenileyin.')
    print(f'Tum demo ogrencileri ortak sifre: {DEMO_PASSWORD}')


if __name__ == '__main__':
    main()
