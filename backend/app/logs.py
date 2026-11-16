"""Logs of every process (api, worker, bot, userbot, refresh): stdout (docker logs) + JSON lines in
LOG_DIR/<service>.log, rotated at midnight, 30 days kept (docs/DEPLOY.md «Логи»). Masking helpers for request bodies.
`python -m app.logs <service>`: tee stdin (a shell process' output) into the same file, one JSON line per line."""
import json
import logging
import logging.handlers
import os
import re
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Tbilisi")
VERSION = os.environ.get("APP_VERSION", "")
SECRET_KEYS = re.compile(r"pass|token|secret|key|signature|sign_data|authorization|cookie|init_?data|code|otp|hash", re.I)
PHONE = re.compile(r"\+?\d[\d\s()-]{7,}\d")


def mask_phone(s: str) -> str:
    """+995 555 12 34 56 -> +995***56: enough to tell two numbers apart, not to call."""
    return PHONE.sub(lambda m: m.group()[:4] + "***" + m.group()[-2:], s)


def mask(v, key: str = ""):
    """A JSON value with secrets dropped and phones masked (logged bodies of failed requests)."""
    if key and SECRET_KEYS.search(key):
        return "***"
    if isinstance(v, dict):
        return {k: mask(x, str(k)) for k, x in v.items()}
    if isinstance(v, list):
        return [mask(x) for x in v[:50]]
    if isinstance(v, str):
        return mask_phone(v[:500])
    return v


class JsonFormatter(logging.Formatter):
    def __init__(self, service: str):
        super().__init__()
        self.service = service

    def format(self, r: logging.LogRecord) -> str:
        d = {"ts": datetime.fromtimestamp(r.created, TZ).isoformat(timespec="milliseconds"), "service": self.service,
             "level": r.levelname, "logger": r.name, "msg": r.getMessage()}
        d.update(getattr(r, "fields", None) or {})
        if r.exc_info:
            d["traceback"] = self.formatException(r.exc_info)
        return json.dumps(d, ensure_ascii=False, default=str)


def setup(service: str, level=logging.INFO) -> None:
    """Root logger -> stdout (JSON too: one line per event, greppable in `docker logs`) + the daily file."""
    root = logging.getLogger()
    if any(getattr(h, "_hig", False) for h in root.handlers):
        return
    for h in root.handlers[:]:
        root.removeHandler(h)
    fmt = JsonFormatter(service)
    handlers = [logging.StreamHandler(sys.stdout)]
    log_dir = os.environ.get("LOG_DIR", "/app/data/logs" if os.path.isdir("/app/data") else "")
    if log_dir:
        try:
            os.makedirs(log_dir, exist_ok=True)
            # ponytail: daily rotation, no size cap per day; ~1 line per API request is tens of MB/day at most
            handlers.append(logging.handlers.TimedRotatingFileHandler(
                os.path.join(log_dir, f"{service}.log"), when="midnight", backupCount=30, encoding="utf-8"))
        except OSError as e:
            print(f"log file disabled: {e!r}", file=sys.stderr)
    for h in handlers:
        h.setFormatter(fmt)
        h._hig = True
        root.addHandler(h)
    root.setLevel(level)
    for noisy in ("httpx", "httpcore", "uvicorn.access", "telethon.network"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    # uvicorn installs its own handlers: route them through ours (no duplicate plain-text lines)
    for name in ("uvicorn", "uvicorn.error"):
        logging.getLogger(name).handlers = []
        logging.getLogger(name).propagate = True
    sys.excepthook = lambda *exc: logging.getLogger(service).critical("uncaught exception", exc_info=exc)
    logging.getLogger(service).info("%s started, version %s", service, VERSION or "?")


def tee(service: str) -> None:
    setup(service)
    log = logging.getLogger(service)
    for line in sys.stdin:
        line = line.rstrip("\n")
        if line:
            low = line.lower()
            bad = "traceback" in low or "error" in low or "failed" in low or "exception" in low
            log.log(logging.WARNING if bad else logging.INFO, "%s", line)


if __name__ == "__main__":
    tee(sys.argv[1] if len(sys.argv) > 1 else "refresh")
