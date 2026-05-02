# Websocket icin basit pub/sub.
# app.py disindaki modullerin (live, schedule, sim) socketio'ya
# dogrudan referans gerektirmeden olay yayinlamasi icin.
import threading

_socketio = None
_lock = threading.Lock()


def init(socketio):
    """SocketIO örneğini kaydet — sadece bir kez çağrılmalı."""
    global _socketio
    with _lock:
        _socketio = socketio


def emit(event, data=None):
    """Tüm bağlı istemcilere bir olay yayınla. Bağlantı yoksa sessizce geçer."""
    if _socketio is None:
        return
    try:
        _socketio.emit(event, data if data is not None else {})
    except Exception as e:
        print(f'[realtime] emit hatasi ({event}):', e)


def emit_to(room, event, data=None):
    """Belirli bir odaya (kullanıcıya) yayınla — bildirim sistemi için."""
    if _socketio is None:
        return
    try:
        _socketio.emit(event, data if data is not None else {}, to=room)
    except Exception as e:
        print(f'[realtime] emit_to hatasi ({room}/{event}):', e)


def is_active():
    return _socketio is not None
