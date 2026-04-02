# Ders programi yonetimi. CRUD + toggle (anlik iptal).
# JSON dosyasinda saklanir, sim ve canli panel buradan okur.
import json
import os
import threading
import realtime

SCHEDULE_FILE = 'schedule_data.json'

DEFAULT_CLASSES = [
    {'name': 'Matematik I',      'day': 0, 'start': 9,  'duration': 2, 'students': 25},
    {'name': 'Fizik',            'day': 0, 'start': 13, 'duration': 3, 'students': 30},
    {'name': 'Programlama',      'day': 1, 'start': 10, 'duration': 2, 'students': 20},
    {'name': 'Devre Analizi',    'day': 1, 'start': 14, 'duration': 2, 'students': 22},
    {'name': 'Termodinamik',     'day': 2, 'start': 9,  'duration': 3, 'students': 28},
    {'name': 'Üretim Yönetimi',  'day': 3, 'start': 11, 'duration': 2, 'students': 18},
    {'name': 'Yapay Zeka',       'day': 4, 'start': 10, 'duration': 2, 'students': 24},
]

DAY_NAMES = ['Pazartesi', 'Salı', 'Çarşamba', 'Perşembe', 'Cuma', 'Cumartesi', 'Pazar']


class ScheduleManager:
    def __init__(self):
        self.lock = threading.Lock()
        self.classes = []
        self.next_id = 1
        self.load()

    # --- Kalıcılık
    def load(self):
        if os.path.exists(SCHEDULE_FILE):
            try:
                with open(SCHEDULE_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.classes = data.get('classes', [])
                self.next_id = data.get('next_id', 1)
                return
            except Exception:
                pass
        # Varsayılan program
        self.classes = []
        for c in DEFAULT_CLASSES:
            self.classes.append({**c, 'id': self._take_id(), 'active': True})
        self.save()

    def save(self):
        try:
            with open(SCHEDULE_FILE, 'w', encoding='utf-8') as f:
                json.dump({'classes': self.classes, 'next_id': self.next_id},
                          f, ensure_ascii=False, indent=2)
        except Exception as e:
            print('Schedule save hatası:', e)

    def _take_id(self):
        i = self.next_id
        self.next_id += 1
        return i

    # --- Doğrulama
    def _validate(self, d):
        try:
            name = str(d.get('name', '')).strip()
            day = int(d.get('day', 0))
            start = int(d.get('start', 0))
            duration = int(d.get('duration', 1))
            students = int(d.get('students', 0))
        except (ValueError, TypeError):
            return None, 'Geçersiz veri biçimi.'

        if not name: return None, 'Ders adı boş olamaz.'
        if not (0 <= day <= 6): return None, 'Gün 0-6 aralığında olmalı.'
        if not (0 <= start <= 23): return None, 'Başlangıç saati 0-23.'
        if not (1 <= duration <= 12): return None, 'Süre 1-12 saat.'
        if start + duration > 24: return None, 'Ders gün sınırını aşıyor.'
        if not (1 <= students <= 200): return None, 'Öğrenci sayısı 1-200.'
        return {'name': name, 'day': day, 'start': start,
                'duration': duration, 'students': students}, None

    # --- CRUD
    def list_all(self):
        with self.lock:
            return [dict(c) for c in self.classes]

    def _notify(self):
        realtime.emit('schedule_update', {'classes': self.list_all()})

    def add(self, data):
        clean, err = self._validate(data)
        if err: return {'ok': False, 'error': err}
        with self.lock:
            clean['id'] = self._take_id()
            clean['active'] = True
            self.classes.append(clean)
            self.save()
            result = {'ok': True, 'class': clean}
        self._notify()
        return result

    def update(self, cid, data):
        clean, err = self._validate(data)
        if err: return {'ok': False, 'error': err}
        with self.lock:
            for c in self.classes:
                if c['id'] == cid:
                    c.update(clean)
                    self.save()
                    result = {'ok': True, 'class': dict(c)}
                    break
            else:
                return {'ok': False, 'error': 'Ders bulunamadı.'}
        self._notify()
        return result

    def delete(self, cid):
        with self.lock:
            before = len(self.classes)
            self.classes = [c for c in self.classes if c['id'] != cid]
            ok = len(self.classes) < before
            if ok:
                self.save()
        if ok:
            self._notify()
            return {'ok': True}
        return {'ok': False, 'error': 'Ders bulunamadı.'}

    def toggle(self, cid):
        """Anlık değişiklik — bir dersi geçici olarak iptal et / geri aç."""
        with self.lock:
            for c in self.classes:
                if c['id'] == cid:
                    c['active'] = not c.get('active', True)
                    self.save()
                    result = {'ok': True, 'active': c['active'], 'class_name': c['name'],
                              'day': c['day'], 'start': c['start']}
                    break
            else:
                return {'ok': False, 'error': 'Ders bulunamadı.'}
        self._notify()
        # Diğer hocalara bildirim
        try:
            import notifications
            day_short = ['Pzt', 'Sal', 'Çar', 'Per', 'Cum', 'Cmt', 'Paz']
            status = 'iptal edildi' if not result['active'] else 'tekrar aktif'
            notifications.notify_all_hoca(
                f'Ders {status}',
                f'{result["class_name"]} — {day_short[result["day"]]} {result["start"]:02d}:00',
                'warning' if not result['active'] else 'info',
                icon='📅', url='/hoca')
        except Exception:
            pass
        return result

    # --- Heatmap için planlı yoğunluk
    def planned_heatmap(self, hour_min=7, hour_max=21):
        """Ders programına göre teorik yoğunluk: gün × saat → beklenen öğrenci sayısı."""
        n_hours = hour_max - hour_min + 1
        matrix = [[0] * n_hours for _ in range(7)]
        with self.lock:
            for c in self.classes:
                if not c.get('active', True):
                    continue
                day = c['day']
                if not (0 <= day <= 6):
                    continue
                for h in range(c['start'], c['start'] + c['duration']):
                    if hour_min <= h <= hour_max:
                        matrix[day][h - hour_min] += c['students']
        max_v = max((max(row) for row in matrix), default=0)
        total = sum(sum(row) for row in matrix)
        return {'matrix': matrix, 'max': max_v, 'total': total,
                'hour_min': hour_min, 'hour_max': hour_max}

    # --- Simülasyon için sorgu
    def current_class(self, day, hour):
        with self.lock:
            for c in self.classes:
                if not c.get('active', True):
                    continue
                if c['day'] == day and c['start'] <= hour < c['start'] + c['duration']:
                    return dict(c)
        return None


# Global örnek — diğer modüller bunu içe aktarır
schedule_mgr = ScheduleManager()
