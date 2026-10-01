"""Простой ограничитель частоты запросов в памяти процесса (скользящее окно).

Нужен для публичных форм (заявка на бронирование, «забыли пароль»), которые открыты всем:
без него один скрипт мог бы за минуту создать сотни заявок и занять все номера. Счётчики
живут в памяти каждого процесса (при двух воркерах лимит фактически вдвое мягче) — для
защиты от спама этого достаточно; точный лимит по IP дополнительно держит nginx (deploy/nginx.conf).
"""
import threading
import time
from collections import defaultdict, deque

_lock = threading.Lock()
_hits: dict[str, deque] = defaultdict(deque)


def allow(key: str, limit: int, window_seconds: int) -> bool:
    """True, если запрос укладывается в лимит (и он засчитывается); False — лимит исчерпан."""
    if limit <= 0:
        return True
    now = time.monotonic()
    with _lock:
        q = _hits[key]
        while q and now - q[0] > window_seconds:
            q.popleft()
        if len(q) >= limit:
            return False
        q.append(now)
        if len(_hits) > 20000:  # защита от разрастания памяти при переборе ключей
            for k in [k for k, v in _hits.items() if not v or now - v[-1] > window_seconds][:5000]:
                _hits.pop(k, None)
        return True


def reset() -> None:
    with _lock:
        _hits.clear()


def client_ip(request) -> str:
    return request.client.host if request.client else "unknown"
