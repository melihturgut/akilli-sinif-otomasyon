"""Hoca paneli kimlik doğrulama — session-based auth + login_required dekoratörü."""
from functools import wraps
from flask import session, redirect, url_for, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import db


def init_default_admin():
    """İlk başlatmada varsayılan admin kullanıcısı oluştur."""
    if db.user_count() == 0:
        db.create_user(
            username='admin',
            password_hash=generate_password_hash('admin123'),
            display_name='Sistem Yöneticisi',
            role='admin',
        )
        print('=' * 56)
        print('  Varsayılan giriş bilgileri:')
        print('    Kullanıcı: admin')
        print('    Şifre:     admin123')
        print('  ÖNEMLİ: İlk girişten sonra şifreyi değiştirin!')
        print('=' * 56)


def verify_login(username, password):
    user = db.get_user(username)
    if user and check_password_hash(user['password_hash'], password):
        return user
    return None


def change_password(username, old_password, new_password):
    user = db.get_user(username)
    if not user or not check_password_hash(user['password_hash'], old_password):
        return False, 'Mevcut şifre hatalı.'
    if len(new_password) < 6:
        return False, 'Yeni şifre en az 6 karakter olmalı.'
    db.update_user_password(username, generate_password_hash(new_password))
    return True, None


def current_user():
    """Aktif oturumdaki kullanıcı bilgisi (yoksa None)."""
    username = session.get('user')
    if not username:
        return None
    user = db.get_user(username)
    if not user:
        session.pop('user', None)
        return None
    # Şifre hash'ini API'ye sızdırma
    user.pop('password_hash', None)
    return user


def login_required(f):
    """Korunan rota için dekoratör — yoksa /login'e veya 401'e gönder."""
    @wraps(f)
    def wrapped(*args, **kwargs):
        if 'user' not in session:
            if request.path.startswith('/api/'):
                return jsonify({'ok': False, 'error': 'Bu işlem için giriş yapmalısınız.',
                                'login_required': True}), 401
            return redirect(url_for('login_page', next=request.path))
        return f(*args, **kwargs)
    return wrapped


# --- Öğrenci Kimlik Doğrulama

def _valid_student_no(s):
    return s.isdigit() and 5 <= len(s) <= 15


def register_student(student_no, password, name=None):
    student_no = str(student_no or '').strip()
    password = str(password or '')
    if not _valid_student_no(student_no):
        return False, 'Geçersiz öğrenci numarası (5-15 rakam).'
    if len(password) < 6:
        return False, 'Şifre en az 6 karakter olmalı.'
    if db.get_student(student_no):
        return False, 'Bu öğrenci numarası zaten kayıtlı. Giriş yapın.'
    db.create_student(student_no, generate_password_hash(password), (name or '').strip() or None)
    return True, None


def verify_student(student_no, password):
    student_no = str(student_no or '').strip()
    student = db.get_student(student_no)
    if student and check_password_hash(student['password_hash'], password or ''):
        db.update_student_last_login(student_no)
        return student
    return None


def current_student():
    student_no = session.get('student')
    if not student_no:
        return None
    student = db.get_student(student_no)
    if not student:
        session.pop('student', None)
        return None
    student.pop('password_hash', None)
    return student


def student_required(f):
    """Öğrenci girişi gerektiren rotalar için dekoratör."""
    @wraps(f)
    def wrapped(*args, **kwargs):
        if 'student' not in session:
            if request.path.startswith('/api/'):
                return jsonify({'ok': False, 'error': 'Öğrenci girişi gerekli.',
                                'login_required': True}), 401
            return redirect(url_for('ogrenci_giris', next=request.path))
        return f(*args, **kwargs)
    return wrapped
