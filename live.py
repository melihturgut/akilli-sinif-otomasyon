# QR tabanli sinif giris mantigi.
# Bolgesel aydinlatma + 1 saatlik etut zamanlayicisi.
# Sunucu restart olsa aktif girisler ve gecmis DB'de.
import threading
import time
import math
import db
import realtime
import notifications
from schedule_mgr import schedule_mgr

ZONES = {
    'on':   {'name': 'Ön Bölge',   'desc': '1-3. Sıralar'},
    'orta': {'name': 'Orta Bölge', 'desc': '4-6. Sıralar'},
    'arka': {'name': 'Arka Bölge', 'desc': '7-9. Sıralar'},
}

STUDY_DURATION = 3600       # 1 saatlik etüt sayacı (rapor 2.3)
ZONE_LIGHT_W = 133          # Bölge başına aydınlatma gücü (W)
CLASS_GRACE_MIN = 15        # Ders basladiktan sonra gec giris toleransi (dk)
EARLY_GRACE_MIN = 10        # Ders baslamadan onceki erken giris penceresi (dk)
DEFAULT_MAX_DISTANCE_M = 100  # GPS konum yaricapi (m)


def _haversine_m(lat1, lon1, lat2, lon2):
    """Iki GPS noktasi arasindaki mesafeyi metre olarak hesapla."""
    R = 6371000
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2 * R * math.asin(math.sqrt(a))


def _check_schedule(now_ts):
    """Aktif ders var mi kontrol. Donus: (in_class, class_or_None, mode_str)."""
    lt = time.localtime(now_ts)
    day = lt.tm_wday
    hour = lt.tm_hour
    minute = lt.tm_min

    cls = schedule_mgr.current_class(day, hour)
    if cls:
        mins_into = (hour - cls['start']) * 60 + minute
        return True, cls, ('gec' if mins_into > CLASS_GRACE_MIN else 'normal')

    # Erken giris penceresi
    for c in schedule_mgr.list_all():
        if not c.get('active', True) or c['day'] != day:
            continue
        if c['start'] - 1 == hour and (60 - minute) <= EARLY_GRACE_MIN:
            return True, c, 'erken'
        if c['start'] == hour and minute < EARLY_GRACE_MIN:
            return True, c, 'erken'
    return False, None, 'etut'


def _check_location(student_lat, student_lng):
    """Sinif konumu ayarliysa mesafe kontrolu. Donus: (ok, dist_m, error)."""
    cls_lat = db.get_setting('classroom_lat')
    cls_lng = db.get_setting('classroom_lng')
    if not cls_lat or not cls_lng:
        return True, None, None  # Konum ayarli degil, kontrolu atla
    if student_lat is None or student_lng is None:
        return False, None, 'Konum bilgisi gerekli. Tarayıcıdan konum izni verin.'
    try:
        dist = _haversine_m(float(cls_lat), float(cls_lng),
                             float(student_lat), float(student_lng))
        max_dist = float(db.get_setting('max_distance_m') or DEFAULT_MAX_DISTANCE_M)
        if dist > max_dist:
            return False, dist, f'Sınıfa çok uzaktasınız (~{int(dist)}m). Sadece sınıf içinden yoklama atılabilir.'
        return True, dist, None
    except (ValueError, TypeError):
        return False, None, 'Konum doğrulanamadı.'


class LiveClassroom:
    def __init__(self):
        self.lock = threading.Lock()

    def checkin(self, student_no, zone, lat=None, lng=None, authenticated=False):
        """3 katmanli kontrol:
        1. Hesap girisi (authenticated=True olmali)
        2. Ders saati (aktif ders veya etut)
        3. GPS konumu (sinif yariçapinda)
        """
        student_no = str(student_no or '').strip()
        if not student_no.isdigit() or not (5 <= len(student_no) <= 15):
            return {'ok': False, 'error': 'Geçersiz öğrenci numarası.'}
        if zone not in ZONES:
            return {'ok': False, 'error': 'Geçersiz bölge kodu.'}

        # KATMAN 1: Login zorunlu
        if not authenticated:
            return {'ok': False, 'error': 'Yoklama için hesabınıza giriş yapmanız gerekir.',
                    'need_login': True}

        # KATMAN 2: Ders saati kontrolu
        now = time.time()
        in_class, current_cls, sched_mode = _check_schedule(now)
        class_id = current_cls['id'] if current_cls else None
        # Ders saatleri disinda etut moduna izin ver (mode='etut' olarak isaretle)
        # Hoca isterse "strict" yapilabilir ama default esnek

        # KATMAN 3: GPS konum kontrolu (sinif konumu ayarliysa)
        loc_ok, distance, loc_err = _check_location(lat, lng)
        if not loc_ok:
            return {'ok': False, 'error': loc_err, 'need_location': True}

        with self.lock:
            db.cleanup_expired()
            renewed = db.has_checkin(student_no)
            expires_at = now + STUDY_DURATION
            db.upsert_checkin(student_no, zone, now, expires_at)
            db.log_attendance(
                student_no, zone,
                'yenileme' if renewed else 'giris',
                now,
                class_id=class_id,
                latitude=lat, longitude=lng,
                mode=sched_mode,
            )
            result = {
                'ok': True,
                'renewed': renewed,
                'student_no': student_no,
                'zone': zone,
                'zone_name': ZONES[zone]['name'],
                'expires_at': expires_at,
                'class_name': current_cls['name'] if current_cls else None,
                'mode': sched_mode,
                'distance_m': int(distance) if distance is not None else None,
            }

        realtime.emit('live_update', self.get_state())
        realtime.emit('attendance_event', {
            'action': 'yenileme' if renewed else 'giris',
            'student_no': student_no, 'zone': ZONES[zone]['name'],
        })
        zone_name = ZONES[zone]['name']
        if renewed:
            notifications.notify_student(student_no,
                'Süre yenilendi',
                f'{zone_name} · Etüt süreniz 1 saat uzatıldı.',
                'info', icon='⏱️')
        else:
            mode_label = {
                'normal': 'ders saatinde',
                'gec':    'derse geç giriş',
                'erken':  'derse erken giriş',
                'etut':   'etüt modu',
            }.get(sched_mode, '')
            cls_part = f' ({current_cls["name"]})' if current_cls else ''
            notifications.notify_student(student_no,
                'Yoklamanız alındı',
                f'{zone_name} · {mode_label}{cls_part}',
                'success', icon='✓')
        return result

    def checkout(self, student_no):
        student_no = str(student_no or '').strip()
        with self.lock:
            if db.delete_checkin(student_no):
                db.log_attendance(student_no, '-', 'cikis')
                ok = True
            else:
                ok = False
        if ok:
            realtime.emit('live_update', self.get_state())
            realtime.emit('attendance_event', {
                'action': 'cikis', 'student_no': student_no, 'zone': '-',
            })
            return {'ok': True}
        return {'ok': False, 'error': 'Aktif giriş bulunamadı.'}

    def get_state(self):
        with self.lock:
            db.cleanup_expired()
            actives = db.list_active_checkins()
            now = time.time()

            zones = {}
            for zid, zinfo in ZONES.items():
                occ = [a for a in actives if a['zone'] == zid]
                zones[zid] = {
                    'name': zinfo['name'],
                    'desc': zinfo['desc'],
                    'lit': len(occ) > 0,
                    'count': len(occ),
                    'students': sorted(a['student_no'] for a in occ),
                }

            attendees = []
            for a in sorted(actives, key=lambda x: x['checkin_time']):
                attendees.append({
                    'student_no': a['student_no'],
                    'zone': ZONES[a['zone']]['name'],
                    'checkin': time.strftime('%H:%M', time.localtime(a['checkin_time'])),
                    'remaining_min': max(0, int((a['expires_at'] - now) / 60)),
                })

            lit_zones = sum(1 for z in zones.values() if z['lit'])
            return {
                'zones': zones,
                'total_present': len(actives),
                'attendees': attendees,
                'lit_zones': lit_zones,
                'lighting_power_w': lit_zones * ZONE_LIGHT_W,
            }

    def get_log(self, limit=100, student_no=None):
        rows = db.get_attendance(limit=limit, student_no=student_no)
        out = []
        for r in rows:
            zone = '-' if r['zone'] == '-' else ZONES.get(r['zone'], {}).get('name', r['zone'])
            out.append({
                'student_no': r['student_no'],
                'zone': zone,
                'time': time.strftime('%d.%m %H:%M', time.localtime(r['timestamp'])),
                'action': r['action'],
            })
        return out
