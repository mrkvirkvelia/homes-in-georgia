"""What a long request is doing right now (the publish: «Готовим видео 1 из 2…»), for the UI to poll (Stanislav 11-16).
ponytail: a dict in this process — the API is one uvicorn process; a second worker process would need a DB row."""
import time

_now: dict[str, dict] = {}


def step(key, code, **kw):
    if key:
        _now[key] = {"step": code, **kw, "at": time.time()}


def get(key) -> dict:
    return _now.get(key) or {}


def done(key):
    _now.pop(key, None)
