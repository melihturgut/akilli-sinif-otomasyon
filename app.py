from flask import Flask, render_template, jsonify, request, session, redirect, url_for, Response
from flask_socketio import SocketIO, join_room
from simulation import SmartClassroomSimulation
from live import LiveClassroom, ZONES
from schedule_mgr import schedule_mgr, DAY_NAMES
import db
import auth
import export
import report
import realtime
import notifications
from auth import login_required, student_required
import os
import threading
import time
import socket
import secrets

# Sunucu saatini Istanbul'a (UTC+3) zorla - Render Linux varsayilan UTC kullaniyor
os.environ.setdefault('TZ', 'Europe/Istanbul')
if hasattr(time, 'tzset'):
    time.tzset()

# Veritabanını başlat (kalıcı yoklama + enerji koşusu kaydı + kullanıcılar)
db.init()
auth.init_default_admin()

# Cloud deploy — ilk başlatmada DB boşsa demo verisi yükle
if 'PORT' in os.environ and db.student_count() == 0:
    try:
        import seed_demo
        seed_demo.seed_students(30)
        seed_demo.seed_attendance(300)
        seed_demo.seed_active_checkins(4)
        seed_demo.seed_runs(5)
        print('[CLOUD] Demo verisi otomatik yuklendi')
    except Exception as e:
        print('[CLOUD] Seed hatasi:', e)

app = Flask(__name__)
# Session imzası — env'den alınır, yoksa rastgele üretilir
app.secret_key = os.environ.get('SECRET_KEY') or secrets.token_hex(32)
app.permanent_session_lifetime = 60 * 60 * 8  # 8 saat

# WebSocket — threading mode (ekstra bağımlılık gerekmez)
socketio = SocketIO(app, async_mode='threading', cors_allowed_origins='*', logger=False, engineio_logger=False)
realtime.init(socketio)


@socketio.on('connect')
def ws_connect():
    """İstemci bağlanınca, oturumdaki kullanıcı bilgisine göre odalara katıl."""
    if 'user' in session:
        join_room(f"hoca:{session['user']}")
        join_room('all_hocas')
    if 'student' in session:
        join_room(f"student:{session['student']}")

sim = SmartClassroomSimulation()
live = LiveClassroom()
sim_thread = None


def run_simulation():
    last_emit = 0
    while sim.running and not sim.complete:
        sim.step()
        # Her ~500ms'de bir gerçek zamanlı durum yayını
        now = time.time()
        if now - last_emit > 0.5:
            last_emit = now
            try:
                realtime.emit('sim_update', sim.get_status())
            except Exception:
                pass
        # Hız dinamik olarak okunur — speed değiştiğinde anında etki eder
        speed = sim.speed
        time.sleep(1.0 / speed)
    sim.running = False
    # Bitiş durumunu yayınla
    realtime.emit('sim_update', sim.get_status())
    if sim.complete:
        realtime.emit('run_complete', {'message': 'Simülasyon tamamlandı'})


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/start', methods=['POST'])
def start():
    global sim_thread
    if not sim.running and not sim.complete:
        sim.running = True
        sim_thread = threading.Thread(target=run_simulation, daemon=True)
        sim_thread.start()
    return jsonify({'status': 'started'})


@app.route('/api/stop', methods=['POST'])
def stop():
    sim.running = False
    return jsonify({'status': 'stopped'})


@app.route('/api/reset', methods=['POST'])
def reset():
    sim.running = False
    time.sleep(0.15)  # thread'in durmasını bekle
    sim.reset()
    return jsonify({'status': 'reset'})


@app.route('/api/status')
def status():
    return jsonify(sim.get_status())


@app.route('/api/config', methods=['POST'])
def config():
    data = request.get_json(force=True)
    sim.configure(data)
    return jsonify({'status': 'ok'})


# --- QR Tabanlı Sınıf Giriş Sistemi

@app.route('/giris')
def giris():
    zone = request.args.get('bolge', 'on')
    if zone not in ZONES:
        zone = 'on'
    return render_template('giris.html', zone=zone, zone_name=ZONES[zone]['name'],
                           zone_desc=ZONES[zone]['desc'])


@app.route('/qr')
def qr():
    return render_template('qr.html', zones=ZONES)


@app.route('/panel')
def panel():
    return render_template('panel.html')


@app.route('/api/checkin', methods=['POST'])
def api_checkin():
    """3 katmanli kontrolden gecen check-in.
    - Login zorunlu (session['student'])
    - student_no oturumdan alinir, body'den DEGIL (sahtekarlik onlenir)
    - Konum (lat, lng) body'den alinir, sunucu mesafeyi dogrular
    """
    data = request.get_json(force=True) or {}

    # Katman 1: Login kontrolu
    if 'student' not in session:
        return jsonify({
            'ok': False,
            'error': 'Yoklama atmak için önce öğrenci hesabınıza giriş yapın.',
            'need_login': True,
            'login_url': '/ogrenci/giris',
        }), 401

    # student_no oturumdan zorla — body'den gelirse yok say
    student_no = session['student']
    zone = data.get('zone')
    lat = data.get('lat')
    lng = data.get('lng')

    result = live.checkin(student_no, zone, lat=lat, lng=lng, authenticated=True)
    return jsonify(result)


@app.route('/api/checkout', methods=['POST'])
def api_checkout():
    if 'student' not in session:
        return jsonify({'ok': False, 'error': 'Giriş gerekli.'}), 401
    return jsonify(live.checkout(session['student']))


@app.route('/api/live')
def api_live():
    return jsonify(live.get_state())


@app.route('/api/log')
def api_log():
    return jsonify(live.get_log())


# --- Kimlik Doğrulama

@app.route('/login')
def login_page():
    if 'user' in session:
        return redirect(url_for('hoca'))
    return render_template('login.html', next=request.args.get('next', '/hoca'))


@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.get_json(force=True) or {}
    user = auth.verify_login(data.get('username', ''), data.get('password', ''))
    if user:
        session.permanent = True
        session['user'] = user['username']
        return jsonify({'ok': True, 'username': user['username'],
                        'display_name': user['display_name']})
    return jsonify({'ok': False, 'error': 'Kullanıcı adı veya şifre hatalı.'})


@app.route('/api/logout', methods=['POST'])
def api_logout():
    session.pop('user', None)
    return jsonify({'ok': True})


@app.route('/api/me')
def api_me():
    user = auth.current_user()
    return jsonify({'user': user})


@app.route('/api/change-password', methods=['POST'])
@login_required
def api_change_password():
    data = request.get_json(force=True) or {}
    ok, err = auth.change_password(session['user'],
                                    data.get('old_password', ''),
                                    data.get('new_password', ''))
    if ok:
        return jsonify({'ok': True})
    return jsonify({'ok': False, 'error': err})


# --- Öğrenci Hesabı

@app.route('/ogrenci/giris')
def ogrenci_giris():
    if 'student' in session:
        return redirect(url_for('ogrenci_panel'))
    return render_template('ogrenci_giris.html', mode='login',
                           next=request.args.get('next', '/ogrenci'))


@app.route('/ogrenci/kayit')
def ogrenci_kayit():
    if 'student' in session:
        return redirect(url_for('ogrenci_panel'))
    return render_template('ogrenci_giris.html', mode='register',
                           next=request.args.get('next', '/ogrenci'))


@app.route('/api/student/register', methods=['POST'])
def api_student_register():
    data = request.get_json(force=True) or {}
    ok, err = auth.register_student(data.get('student_no'),
                                     data.get('password'),
                                     data.get('name'))
    if ok:
        session.permanent = True
        session['student'] = str(data.get('student_no')).strip()
        return jsonify({'ok': True, 'student_no': session['student']})
    return jsonify({'ok': False, 'error': err})


@app.route('/api/student/login', methods=['POST'])
def api_student_login():
    data = request.get_json(force=True) or {}
    student = auth.verify_student(data.get('student_no'), data.get('password'))
    if student:
        session.permanent = True
        session['student'] = student['student_no']
        return jsonify({'ok': True, 'student_no': student['student_no'],
                        'name': student.get('name')})
    return jsonify({'ok': False, 'error': 'Öğrenci numarası veya şifre hatalı.'})


@app.route('/api/student/logout', methods=['POST'])
def api_student_logout():
    session.pop('student', None)
    return jsonify({'ok': True})


@app.route('/api/student/me')
def api_student_me():
    return jsonify({'student': auth.current_student()})


@app.route('/ogrenci')
@student_required
def ogrenci_panel():
    student = auth.current_student()
    return render_template('ogrenci.html', day_names=DAY_NAMES, student=student)


@app.route('/api/student/dashboard')
@student_required
def api_student_dashboard():
    """Öğrencinin kendi verisi: profil, durum, yoklama özeti, haftalık ders."""
    student_no = session['student']
    student = auth.current_student()

    # Aktif giriş durumu
    actives = db.list_active_checkins()
    current_active = next((a for a in actives if a['student_no'] == student_no), None)

    # Yoklama özeti
    history = db.get_attendance(limit=500, student_no=student_no)
    total = len(history)
    checkins = sum(1 for h in history if h['action'] == 'giris')
    unique_days = len({time.strftime('%Y-%m-%d', time.localtime(h['timestamp'])) for h in history})

    # Haftalık ders programı (sadece aktif)
    classes = [c for c in schedule_mgr.list_all() if c.get('active', True)]
    weekly = []
    for c in sorted(classes, key=lambda x: (x['day'], x['start'])):
        weekly.append({
            'name': c['name'],
            'day': c['day'],
            'day_name': DAY_NAMES[c['day']],
            'start': c['start'],
            'end': c['start'] + c['duration'],
            'students': c['students'],
        })

    # Anlık sınıf durumu
    live_state = live.get_state()

    # Son tamamlanmış simülasyonun sonuçları + kümülatif toplam
    runs = db.list_energy_runs(limit=500)
    last_run = runs[0] if runs else None
    cumulative = {
        'runs': len(runs),
        'savings_kwh': round(sum(r['savings_kwh'] for r in runs), 2),
        'cost_tl':     round(sum(r['cost_saved_tl'] for r in runs), 2),
        'carbon_kg':   round(sum(r['carbon_saved_kg'] for r in runs), 2),
    }

    return jsonify({
        'student': student,
        'current_active': {
            'zone': ZONES[current_active['zone']]['name'],
            'checkin_time': time.strftime('%H:%M', time.localtime(current_active['checkin_time'])),
            'remaining_min': max(0, int((current_active['expires_at'] - time.time()) / 60)),
        } if current_active else None,
        'summary': {
            'total_events': total,
            'total_checkins': checkins,
            'unique_days': unique_days,
        },
        'classroom_live': {
            'total_present':    live_state['total_present'],
            'lit_zones':        live_state['lit_zones'],
            'lighting_power_w': live_state['lighting_power_w'],
        },
        'last_run': {
            'savings_kwh':     last_run['savings_kwh'],
            'savings_pct':     last_run['savings_pct'],
            'cost_saved_tl':   last_run['cost_saved_tl'],
            'carbon_saved_kg': last_run['carbon_saved_kg'],
            'finished_at':     last_run['finished_at'],
        } if last_run else None,
        'cumulative': cumulative,
        'weekly_schedule': weekly,
        'recent_attendance': [{
            'zone': '-' if h['zone'] == '-' else ZONES.get(h['zone'], {}).get('name', h['zone']),
            'action': h['action'],
            'time': time.strftime('%d.%m %H:%M', time.localtime(h['timestamp'])),
        } for h in history[:20]],
    })


# --- Hoca Paneli — Ders Programı Yönetimi (rapor 2.3)

@app.route('/hoca')
@login_required
def hoca():
    user = auth.current_user()
    return render_template('hoca.html', day_names=DAY_NAMES, user=user)


@app.route('/api/schedule', methods=['GET'])
def api_schedule_list():
    return jsonify({'classes': schedule_mgr.list_all(), 'day_names': DAY_NAMES})


@app.route('/api/schedule', methods=['POST'])
@login_required
def api_schedule_add():
    return jsonify(schedule_mgr.add(request.get_json(force=True)))


@app.route('/api/schedule/<int:cid>', methods=['PUT'])
@login_required
def api_schedule_update(cid):
    return jsonify(schedule_mgr.update(cid, request.get_json(force=True)))


@app.route('/api/schedule/<int:cid>', methods=['DELETE'])
@login_required
def api_schedule_delete(cid):
    return jsonify(schedule_mgr.delete(cid))


@app.route('/api/schedule/<int:cid>/toggle', methods=['POST'])
@login_required
def api_schedule_toggle(cid):
    return jsonify(schedule_mgr.toggle(cid))


# --- Sinif konumu (yoklama dogrulama icin) ---

@app.route('/api/settings/classroom-location', methods=['GET'])
def api_get_classroom_location():
    """Mevcut sinif konumunu dondur (herkese acik, frontend ihtiyaci icin)."""
    lat = db.get_setting('classroom_lat')
    lng = db.get_setting('classroom_lng')
    max_d = db.get_setting('max_distance_m') or 100
    return jsonify({
        'lat': float(lat) if lat else None,
        'lng': float(lng) if lng else None,
        'max_distance_m': float(max_d),
        'is_set': lat is not None and lng is not None,
    })


@app.route('/api/settings/classroom-location', methods=['POST'])
@login_required
def api_set_classroom_location():
    """Hoca paneli — su anki GPS koordinatini sinif konumu olarak kaydet."""
    data = request.get_json(force=True) or {}
    try:
        lat = float(data['lat'])
        lng = float(data['lng'])
        max_d = float(data.get('max_distance_m', 100))
    except (KeyError, ValueError, TypeError):
        return jsonify({'ok': False, 'error': 'Geçersiz konum verisi.'}), 400
    db.set_setting('classroom_lat', lat)
    db.set_setting('classroom_lng', lng)
    db.set_setting('max_distance_m', max_d)
    return jsonify({'ok': True, 'lat': lat, 'lng': lng, 'max_distance_m': max_d})


@app.route('/api/settings/classroom-location', methods=['DELETE'])
@login_required
def api_clear_classroom_location():
    """Sinif konumu ayarini temizle (konum kontrolu pasif olur)."""
    db.set_setting('classroom_lat', None)
    db.set_setting('classroom_lng', None)
    return jsonify({'ok': True})


# --- Veritabanı Sorguları (geçmiş yoklama + enerji koşuları)

@app.route('/api/db/stats')
def api_db_stats():
    return jsonify(db.attendance_stats())


@app.route('/api/db/attendance')
def api_db_attendance():
    limit = min(int(request.args.get('limit', 100)), 500)
    student_no = request.args.get('student_no')
    return jsonify(live.get_log(limit=limit, student_no=student_no))


@app.route('/api/db/runs')
def api_db_runs():
    return jsonify(db.list_energy_runs(limit=30))


@app.route('/api/db/class-stats')
def api_db_class_stats():
    return jsonify(db.class_attendance_stats(schedule_mgr.list_all()))


# --- Admin / Yönetici Paneli

@app.route('/admin')
@login_required
def admin_page():
    user = auth.current_user()
    return render_template('admin.html', day_names=DAY_NAMES, user=user)


@app.route('/analitik')
@login_required
def analitik_page():
    user = auth.current_user()
    return render_template('analitik.html', day_names=DAY_NAMES, user=user)


# --- Bildirimler

def _notif_session():
    """Mevcut oturumdan (user_type, user_id) çıkar."""
    if 'user' in session:
        return ('hoca', session['user'])
    if 'student' in session:
        return ('student', session['student'])
    return (None, None)


@app.route('/api/notifications')
def api_notifications():
    user_type, user_id = _notif_session()
    if not user_type:
        return jsonify({'ok': False, 'error': 'Giriş gerekli', 'login_required': True}), 401
    limit = min(int(request.args.get('limit', 50)), 200)
    unread_only = request.args.get('unread') == '1'
    items = db.list_notifications(user_type, user_id, limit=limit, unread_only=unread_only)
    unread = db.count_unread(user_type, user_id)
    return jsonify({'ok': True, 'items': items, 'unread': unread})


@app.route('/api/notifications/<int:nid>/read', methods=['POST'])
def api_notif_mark_read(nid):
    user_type, user_id = _notif_session()
    if not user_type:
        return jsonify({'ok': False}), 401
    ok = db.mark_notification_read(nid, user_type, user_id)
    return jsonify({'ok': ok})


@app.route('/api/notifications/read-all', methods=['POST'])
def api_notif_read_all():
    user_type, user_id = _notif_session()
    if not user_type:
        return jsonify({'ok': False}), 401
    n = db.mark_all_read(user_type, user_id)
    return jsonify({'ok': True, 'count': n})


@app.route('/api/db/heatmap')
@login_required
def api_db_heatmap():
    mode = request.args.get('mode', 'gerçek')
    if mode == 'planli':
        data = schedule_mgr.planned_heatmap()
    else:
        data = db.attendance_heatmap()
    return jsonify(data)


# --- Dışa Aktarma (CSV / Excel)

def _csv_response(data, filename):
    return Response(data,
                    mimetype='text/csv; charset=utf-8',
                    headers={'Content-Disposition': f'attachment; filename="{filename}"'})


def _xlsx_response(data, filename):
    return Response(data,
                    mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    headers={'Content-Disposition': f'attachment; filename="{filename}"'})


@app.route('/api/export/attendance.csv')
@login_required
def export_attendance_csv():
    student_no = request.args.get('student_no')
    return _csv_response(export.attendance_csv(student_no), 'yoklama.csv')


@app.route('/api/export/runs.csv')
@login_required
def export_runs_csv():
    return _csv_response(export.runs_csv(), 'sim_kosmalari.csv')


@app.route('/api/export/class-stats.csv')
@login_required
def export_class_stats_csv():
    return _csv_response(export.class_stats_csv(), 'ders_doluluk.csv')


@app.route('/api/export/full.xlsx')
@login_required
def export_full_xlsx():
    return _xlsx_response(export.full_xlsx(), 'akilli_sinif_rapor.xlsx')


@app.route('/api/export/full.pdf')
@login_required
def export_full_pdf():
    pdf = report.generate_full_report()
    filename = f"akilli_sinif_rapor_{time.strftime('%Y%m%d_%H%M')}.pdf"
    return Response(pdf, mimetype='application/pdf',
                    headers={'Content-Disposition': f'attachment; filename="{filename}"'})


def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return 'localhost'


if __name__ == '__main__':
    # Render gibi cloud servisler PORT env değişkeni atar
    port = int(os.environ.get('PORT', 5000))
    is_cloud = 'PORT' in os.environ  # Cloud'da çalışıyor mu

    if not is_cloud:
        ip = get_local_ip()
        print('\n' + '=' * 52)
        print('  Akilli Sinif Otomasyonu — IoT Simulasyonu')
        print('=' * 52)
        print(f'  Bilgisayarda : http://localhost:{port}')
        print(f'  Telefonda    : http://{ip}:{port}')
        print('  (Telefon ve bilgisayar ayni Wi-Fi aginda olmali)')
        print('  WebSocket: gercek zamanli senkronizasyon aktif')
        print('=' * 52 + '\n')
    else:
        print(f'[CLOUD] Akilli Sinif sunucusu port {port} dinliyor')

    socketio.run(app, host='0.0.0.0', port=port, debug=False, allow_unsafe_werkzeug=True)
