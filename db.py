# SQLite katmani.
# Tablolar: attendance (yoklama), active_checkins (aktif girisler),
# energy_runs (sim ozetleri), users (hocalar), students, notifications.
# Not: cloud'da SQLite dosyasi gecici, restart'da silinir.
import sqlite3
import threading
import time
import json
import os

DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'smartclass.db')

_lock = threading.Lock()


def _conn():
    c = sqlite3.connect(DB_FILE, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


def init():
    with _lock:
        c = _conn()
        c.executescript("""
        CREATE TABLE IF NOT EXISTS attendance (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            student_no  TEXT NOT NULL,
            zone        TEXT NOT NULL,
            action      TEXT NOT NULL,
            timestamp   REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_att_student ON attendance(student_no);
        CREATE INDEX IF NOT EXISTS idx_att_time    ON attendance(timestamp);

        CREATE TABLE IF NOT EXISTS active_checkins (
            student_no    TEXT PRIMARY KEY,
            zone          TEXT NOT NULL,
            checkin_time  REAL NOT NULL,
            expires_at    REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS energy_runs (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            finished_at     TEXT DEFAULT CURRENT_TIMESTAMP,
            total_minutes   INTEGER NOT NULL,
            energy_auto     REAL NOT NULL,
            energy_baseline REAL NOT NULL,
            savings_kwh     REAL NOT NULL,
            savings_pct     REAL NOT NULL,
            cost_saved_tl   REAL NOT NULL,
            carbon_saved_kg REAL NOT NULL,
            daily_json      TEXT
        );

        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            username      TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            display_name  TEXT,
            role          TEXT DEFAULT 'hoca',
            created_at    TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS students (
            student_no    TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            name          TEXT,
            created_at    TEXT DEFAULT CURRENT_TIMESTAMP,
            last_login    TEXT
        );

        CREATE TABLE IF NOT EXISTS notifications (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_type  TEXT NOT NULL,
            user_id    TEXT NOT NULL,
            title      TEXT NOT NULL,
            message    TEXT,
            severity   TEXT DEFAULT 'info',
            icon       TEXT,
            url        TEXT,
            read       INTEGER DEFAULT 0,
            created_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_notif_user ON notifications(user_type, user_id);
        CREATE INDEX IF NOT EXISTS idx_notif_read ON notifications(read);

        CREATE TABLE IF NOT EXISTS app_settings (
            key   TEXT PRIMARY KEY,
            value TEXT
        );
        """)
        # Eski attendance tablosuna yeni kolonlar (varsa atla)
        for col_def in [
            "class_id INTEGER",
            "latitude REAL",
            "longitude REAL",
            "mode TEXT",
        ]:
            try:
                col_name = col_def.split()[0]
                c.execute(f"ALTER TABLE attendance ADD COLUMN {col_def}")
            except Exception:
                pass
        c.commit()
        c.close()


# --- Yoklama

def log_attendance(student_no, zone, action, ts=None,
                    class_id=None, latitude=None, longitude=None, mode=None):
    ts = ts if ts is not None else time.time()
    with _lock:
        c = _conn()
        c.execute("""INSERT INTO attendance
            (student_no, zone, action, timestamp, class_id, latitude, longitude, mode)
            VALUES (?,?,?,?,?,?,?,?)""",
            (student_no, zone, action, ts, class_id, latitude, longitude, mode))
        c.commit()
        c.close()


def get_attendance(limit=100, student_no=None, since=None):
    with _lock:
        c = _conn()
        q = "SELECT * FROM attendance WHERE 1=1"
        args = []
        if student_no:
            q += " AND student_no = ?"; args.append(student_no)
        if since:
            q += " AND timestamp >= ?"; args.append(since)
        q += " ORDER BY timestamp DESC LIMIT ?"; args.append(limit)
        rows = c.execute(q, args).fetchall()
        c.close()
        return [dict(r) for r in rows]


def attendance_stats():
    """Toplam kayıt, benzersiz öğrenci, bugünkü giriş sayısı."""
    today_start = time.mktime(time.strptime(time.strftime('%Y-%m-%d') + ' 00:00:00', '%Y-%m-%d %H:%M:%S'))
    with _lock:
        c = _conn()
        total = c.execute("SELECT COUNT(*) FROM attendance").fetchone()[0]
        unique = c.execute("SELECT COUNT(DISTINCT student_no) FROM attendance").fetchone()[0]
        today = c.execute("SELECT COUNT(*) FROM attendance WHERE timestamp >= ? AND action='giris'",
                           (today_start,)).fetchone()[0]
        c.close()
        return {'total_events': total, 'unique_students': unique, 'today_checkins': today}


# --- Aktif Giriş

def upsert_checkin(student_no, zone, checkin_time, expires_at):
    with _lock:
        c = _conn()
        c.execute("""INSERT INTO active_checkins (student_no, zone, checkin_time, expires_at)
                     VALUES (?,?,?,?)
                     ON CONFLICT(student_no) DO UPDATE SET
                       zone=excluded.zone,
                       checkin_time=excluded.checkin_time,
                       expires_at=excluded.expires_at""",
                  (student_no, zone, checkin_time, expires_at))
        c.commit()
        c.close()


def has_checkin(student_no):
    with _lock:
        c = _conn()
        r = c.execute("SELECT 1 FROM active_checkins WHERE student_no=?", (student_no,)).fetchone()
        c.close()
        return r is not None


def delete_checkin(student_no):
    with _lock:
        c = _conn()
        cur = c.execute("DELETE FROM active_checkins WHERE student_no=?", (student_no,))
        c.commit()
        affected = cur.rowcount
        c.close()
        return affected > 0


def list_active_checkins():
    with _lock:
        c = _conn()
        rows = c.execute("SELECT * FROM active_checkins").fetchall()
        c.close()
        return [dict(r) for r in rows]


def cleanup_expired():
    """Süresi dolan girişleri sil (1 saatlik etüt sonu)."""
    with _lock:
        c = _conn()
        cur = c.execute("DELETE FROM active_checkins WHERE expires_at <= ?", (time.time(),))
        c.commit()
        n = cur.rowcount
        c.close()
        return n


# --- Enerji Koşusu Özeti

def save_energy_run(data):
    with _lock:
        c = _conn()
        c.execute("""INSERT INTO energy_runs
                     (total_minutes, energy_auto, energy_baseline, savings_kwh, savings_pct,
                      cost_saved_tl, carbon_saved_kg, daily_json)
                     VALUES (?,?,?,?,?,?,?,?)""",
                  (data['total_minutes'], data['energy_auto'], data['energy_baseline'],
                   data['savings_kwh'], data['savings_pct'], data['cost_saved_tl'],
                   data['carbon_saved_kg'], json.dumps(data.get('daily', []), ensure_ascii=False)))
        c.commit()
        c.close()


# --- Kullanıcılar

def get_user(username):
    with _lock:
        c = _conn()
        r = c.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        c.close()
        return dict(r) if r else None


def create_user(username, password_hash, display_name=None, role='hoca'):
    with _lock:
        c = _conn()
        try:
            c.execute("INSERT INTO users (username, password_hash, display_name, role) VALUES (?,?,?,?)",
                      (username, password_hash, display_name or username, role))
            c.commit()
            ok = True
        except sqlite3.IntegrityError:
            ok = False
        c.close()
        return ok


def update_user_password(username, new_hash):
    with _lock:
        c = _conn()
        cur = c.execute("UPDATE users SET password_hash=? WHERE username=?", (new_hash, username))
        c.commit()
        affected = cur.rowcount
        c.close()
        return affected > 0


def user_count():
    with _lock:
        c = _conn()
        n = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        c.close()
        return n


# --- Öğrenciler

def get_student(student_no):
    with _lock:
        c = _conn()
        r = c.execute("SELECT * FROM students WHERE student_no = ?", (student_no,)).fetchone()
        c.close()
        return dict(r) if r else None


def create_student(student_no, password_hash, name=None):
    with _lock:
        c = _conn()
        try:
            c.execute("INSERT INTO students (student_no, password_hash, name) VALUES (?,?,?)",
                      (student_no, password_hash, name))
            c.commit()
            ok = True
        except sqlite3.IntegrityError:
            ok = False
        c.close()
        return ok


def update_student_password(student_no, new_hash):
    with _lock:
        c = _conn()
        cur = c.execute("UPDATE students SET password_hash=? WHERE student_no=?", (new_hash, student_no))
        c.commit()
        affected = cur.rowcount
        c.close()
        return affected > 0


def update_student_last_login(student_no):
    with _lock:
        c = _conn()
        c.execute("UPDATE students SET last_login = datetime('now') WHERE student_no = ?", (student_no,))
        c.commit()
        c.close()


def student_count():
    with _lock:
        c = _conn()
        n = c.execute("SELECT COUNT(*) FROM students").fetchone()[0]
        c.close()
        return n


# --- Bildirimler

def add_notification(user_type, user_id, title, message=None,
                      severity='info', icon=None, url=None):
    import time as _t
    with _lock:
        c = _conn()
        cur = c.execute("""INSERT INTO notifications
            (user_type, user_id, title, message, severity, icon, url, created_at)
            VALUES (?,?,?,?,?,?,?,?)""",
            (user_type, user_id, title, message, severity, icon, url, _t.time()))
        c.commit()
        nid = cur.lastrowid
        c.close()
        return nid


def list_notifications(user_type, user_id, limit=50, unread_only=False):
    with _lock:
        c = _conn()
        q = "SELECT * FROM notifications WHERE user_type=? AND user_id=?"
        args = [user_type, user_id]
        if unread_only:
            q += " AND read=0"
        q += " ORDER BY created_at DESC LIMIT ?"
        args.append(limit)
        rows = c.execute(q, args).fetchall()
        c.close()
        return [dict(r) for r in rows]


def count_unread(user_type, user_id):
    with _lock:
        c = _conn()
        n = c.execute("SELECT COUNT(*) FROM notifications WHERE user_type=? AND user_id=? AND read=0",
                       (user_type, user_id)).fetchone()[0]
        c.close()
        return n


def mark_notification_read(nid, user_type, user_id):
    with _lock:
        c = _conn()
        cur = c.execute("UPDATE notifications SET read=1 WHERE id=? AND user_type=? AND user_id=?",
                         (nid, user_type, user_id))
        c.commit()
        affected = cur.rowcount
        c.close()
        return affected > 0


def mark_all_read(user_type, user_id):
    with _lock:
        c = _conn()
        cur = c.execute("UPDATE notifications SET read=1 WHERE user_type=? AND user_id=? AND read=0",
                         (user_type, user_id))
        c.commit()
        affected = cur.rowcount
        c.close()
        return affected


# --- Ayarlar (sinif konumu, esik degerler vb.)

def set_setting(key, value):
    with _lock:
        c = _conn()
        c.execute("""INSERT INTO app_settings (key, value) VALUES (?,?)
                     ON CONFLICT(key) DO UPDATE SET value=excluded.value""",
                  (key, str(value) if value is not None else None))
        c.commit()
        c.close()


def get_setting(key, default=None):
    with _lock:
        c = _conn()
        r = c.execute("SELECT value FROM app_settings WHERE key=?", (key,)).fetchone()
        c.close()
        return r['value'] if r else default


def list_all_hoca_usernames():
    with _lock:
        c = _conn()
        rows = c.execute("SELECT username FROM users").fetchall()
        c.close()
        return [r['username'] for r in rows]


# --- Geçmiş Koşmalar

def list_energy_runs(limit=30):
    with _lock:
        c = _conn()
        rows = c.execute("SELECT * FROM energy_runs ORDER BY finished_at DESC LIMIT ?", (limit,)).fetchall()
        c.close()
        out = []
        for r in rows:
            d = dict(r)
            d['daily'] = json.loads(d.pop('daily_json') or '[]')
            out.append(d)
        return out


# --- Çapraz Analiz — Ders Bazlı Yoklama İstatistiği

def attendance_heatmap(hour_min=7, hour_max=21):
    """Gün × Saat ısı haritası verisi — gerçek check-in sayıları.

    Dönüş: {'matrix': 7x(hour_max-hour_min+1) liste, 'max': en yüksek değer, 'total': toplam}
    Matrix[gün][saat_index] = o saat dilimindeki giriş sayısı.
    Günler: 0=Pzt, 6=Paz (sistemin gün konvansiyonu).
    """
    with _lock:
        c = _conn()
        rows = c.execute("""
            SELECT
                CAST(strftime('%w', datetime(timestamp, 'unixepoch', 'localtime')) AS INT) AS sqlite_dow,
                CAST(strftime('%H', datetime(timestamp, 'unixepoch', 'localtime')) AS INT) AS hour,
                COUNT(*) AS cnt
            FROM attendance
            WHERE action = 'giris'
            GROUP BY sqlite_dow, hour
        """).fetchall()
        c.close()

    n_hours = hour_max - hour_min + 1
    matrix = [[0] * n_hours for _ in range(7)]
    total = 0
    for r in rows:
        # SQLite: 0=Pazar, 6=Cumartesi → bizim: 0=Pzt, 6=Paz
        our_dow = (r['sqlite_dow'] + 6) % 7
        h = r['hour']
        if hour_min <= h <= hour_max:
            matrix[our_dow][h - hour_min] = r['cnt']
            total += r['cnt']
    max_v = max((max(row) for row in matrix), default=0)
    return {'matrix': matrix, 'max': max_v, 'total': total,
            'hour_min': hour_min, 'hour_max': hour_max}


def class_attendance_stats(classes):
    """Her ders için kaç öğrenci giriş yapmış.

    Attendance timestamp'inden haftanın günü ve saat çıkarılıp ders zamanıyla
    eşleştirilir. SQLite strftime: '%w' → 0=Pazar, 6=Cumartesi (bizim 0=Pzt'den farklı).
    """
    out = []
    with _lock:
        c = _conn()
        for cls in classes:
            sqlite_day = (cls['day'] + 1) % 7  # 0=Pzt → 1=Mon (SQLite)
            start_h = cls['start']
            end_h = cls['start'] + cls['duration']
            r = c.execute("""
                SELECT
                    COUNT(*) AS total_events,
                    COUNT(DISTINCT student_no) AS unique_students
                FROM attendance
                WHERE action = 'giris'
                  AND CAST(strftime('%w', datetime(timestamp, 'unixepoch', 'localtime')) AS INT) = ?
                  AND CAST(strftime('%H', datetime(timestamp, 'unixepoch', 'localtime')) AS INT) >= ?
                  AND CAST(strftime('%H', datetime(timestamp, 'unixepoch', 'localtime')) AS INT) < ?
            """, (sqlite_day, start_h, end_h)).fetchone()
            unique = r['unique_students'] or 0
            expected = cls.get('students', 0) or 0
            occ_rate = round(unique / expected * 100, 1) if expected else 0.0
            out.append({
                'class_id': cls['id'],
                'class_name': cls['name'],
                'day': cls['day'],
                'time': f"{start_h:02d}:00-{end_h:02d}:00",
                'expected': expected,
                'checkins': r['total_events'] or 0,
                'unique_students': unique,
                'occupancy_rate': occ_rate,
                'active': cls.get('active', True),
            })
        c.close()
    return out
