# QR tabanli sinif giris mantigi.
# Bolgesel aydinlatma + 1 saatlik etut zamanlayicisi.
# Sunucu restart olsa aktif girisler ve gecmis DB'de.
import threading
import time
import db
import realtime
import notifications

ZONES = {
    'on':   {'name': 'Ön Bölge',   'desc': '1-3. Sıralar'},
    'orta': {'name': 'Orta Bölge', 'desc': '4-6. Sıralar'},
    'arka': {'name': 'Arka Bölge', 'desc': '7-9. Sıralar'},
}

STUDY_DURATION = 3600   # 1 saatlik etüt sayacı (rapor 2.3)
ZONE_LIGHT_W = 133      # Bölge başına aydınlatma gücü (W)


class LiveClassroom:
    def __init__(self):
        self.lock = threading.Lock()

    def checkin(self, student_no, zone):
        student_no = str(student_no or '').strip()
        if not student_no.isdigit() or not (5 <= len(student_no) <= 15):
            return {'ok': False, 'error': 'Geçersiz öğrenci numarası. Sadece rakam giriniz.'}
        if zone not in ZONES:
            return {'ok': False, 'error': 'Geçersiz bölge kodu.'}

        with self.lock:
            db.cleanup_expired()
            renewed = db.has_checkin(student_no)
            now = time.time()
            expires_at = now + STUDY_DURATION
            db.upsert_checkin(student_no, zone, now, expires_at)
            db.log_attendance(student_no, zone, 'yenileme' if renewed else 'giris', now)
            result = {
                'ok': True,
                'renewed': renewed,
                'student_no': student_no,
                'zone': zone,
                'zone_name': ZONES[zone]['name'],
                'expires_at': expires_at,
            }

        # Lock dışında yayınla
        realtime.emit('live_update', self.get_state())
        realtime.emit('attendance_event', {
            'action': 'yenileme' if renewed else 'giris',
            'student_no': student_no, 'zone': ZONES[zone]['name'],
        })
        # Öğrenciye kişisel bildirim
        zone_name = ZONES[zone]['name']
        if renewed:
            notifications.notify_student(student_no,
                'Süre yenilendi',
                f'{zone_name} · Etüt süreniz 1 saat uzatıldı.',
                'info', icon='⏱️')
        else:
            notifications.notify_student(student_no,
                'Yoklamanız alındı',
                f'{zone_name}\'e başarıyla giriş yaptınız.',
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
