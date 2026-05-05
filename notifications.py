# Bildirim sistemi. DB'ye kaydeder + websocket ile push.
# severity: info / success / warning / danger
import time
import db
import realtime


def _emit_with_payload(nid, user_type, user_id, title, message, severity, icon, url):
    payload = {
        'id': nid,
        'user_type': user_type,
        'user_id': user_id,
        'title': title,
        'message': message,
        'severity': severity,
        'icon': icon,
        'url': url,
        'created_at': time.time(),
        'read': 0,
    }
    # Hedef odaya yayınla (rooms ile kullanıcıya özel push)
    realtime.emit_to(f'{user_type}:{user_id}', 'notification', payload)


def notify(user_type, user_id, title, message=None,
            severity='info', icon=None, url=None):
    nid = db.add_notification(user_type, user_id, title, message, severity, icon, url)
    _emit_with_payload(nid, user_type, user_id, title, message, severity, icon, url)
    return nid


def notify_hoca(username, title, message=None, severity='info', icon=None, url=None):
    return notify('hoca', username, title, message, severity, icon, url)


def notify_student(student_no, title, message=None, severity='info', icon=None, url=None):
    return notify('student', student_no, title, message, severity, icon, url)


def notify_all_hoca(title, message=None, severity='info', icon=None, url=None):
    """Sistemdeki tüm hoca/admin hesaplarına bildirim gönder."""
    nids = []
    for username in db.list_all_hoca_usernames():
        nids.append(notify('hoca', username, title, message, severity, icon, url))
    # Tüm hocalar odasına da yayınla (UI anında güncellensin)
    realtime.emit('hoca_broadcast', {
        'title': title, 'message': message, 'severity': severity,
        'icon': icon, 'url': url,
    })
    return nids
