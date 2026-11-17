"""Sync Bot API client (httpx). BOT_TOKEN and TG_API_BASE come from the environment at call time (tests point
TG_API_BASE at a fake Bot API); the same bot for clients and staff. Never raises: returns the Bot API `result`, or
None on any failure (logged). Exception: inside delivery() (the worker around a job) a failed send is recorded, and a
transient one (network, 5xx, still 429) raises DeliveryError so the job is retried with backoff."""
import contextlib
import contextvars
import html as _html
import json
import logging
import os
import re
import threading
import time

import httpx

log = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)  # its INFO line is the request URL with /bot<TOKEN>/


def conf(key, default=""):
    """Config value: the process environment wins, then app.config.settings (repo .env)."""
    v = os.environ.get(key)
    if v is None:
        try:
            from app.config import settings
            v = getattr(settings, key, None)
        except Exception:
            v = None
    return default if v in (None, "") else str(v)
JSON_PARAMS = {"reply_markup", "media", "entities", "caption_entities", "link_preview_options", "allowed_updates"}
_http = None


def _client():
    global _http
    if _http is None:
        _http = httpx.Client(timeout=httpx.Timeout(30, connect=10))
    return _http


def base():
    token = conf("BOT_TOKEN").strip()
    api = conf("TG_API_BASE", "https://api.telegram.org").rstrip("/")
    return token and f"{api}/bot{token}"


# Telegram allows a bot ~30 messages/s overall: every call of this process waits its turn (pushes to clients, digests)
MIN_GAP = 0.04  # ponytail: one global pace per process (~25/s); per-chat (1/s) and per-group (20/min) pacing if bursts grow
_pace_lock, _last_call = threading.Lock(), [0.0]


def _pace():
    with _pace_lock:
        wait = _last_call[0] + MIN_GAP - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _last_call[0] = time.monotonic()


class DeliveryError(Exception):
    """A message did not go out inside delivery(); raised only for transient failures (the job is worth retrying)."""
    def __init__(self, method, chat_id, reason, permanent=False):
        super().__init__(f"telegram {method} to {chat_id}: {reason}")
        self.method, self.chat_id, self.reason, self.permanent = method, chat_id, reason, permanent


class Delivery:
    """What one worker job sent: `sent` {key: result} (kept in the job's payload when it is retried, so the retry
    replays those results instead of sending the same message twice) and `failed` [DeliveryError]."""
    def __init__(self, replay=None):
        self.replay, self.sent, self.failed, self._n = dict(replay or {}), {}, [], {}

    def key(self, method, params):
        """The n-th message of this method to this chat (and topic) in the job: the same on every attempt."""
        k = f"{method}:{params.get('chat_id')}:{params.get('message_thread_id') or ''}"
        self._n[k] = self._n.get(k, 0) + 1
        return f"{k}:{self._n[k]}"


_delivery = contextvars.ContextVar("tg_delivery", default=None)


@contextlib.contextmanager
def delivery(replay=None):
    """The worker around a job handler: failed sends are counted (API requests and the bot keep «None on failure»)."""
    d = Delivery(replay)
    tok = _delivery.set(d)
    try:
        yield d
    finally:
        _delivery.reset(tok)


def _delivers(method):
    """Methods that put a message in front of someone; edits/deletes keep returning None (callers handle that)."""
    return (method.startswith("send") and method != "sendChatAction") or method in ("copyMessage", "forwardMessage")


def _failed(method, params, reason, permanent):
    d = _delivery.get()
    if d is None or not _delivers(method):
        return None
    err = DeliveryError(method, params.get("chat_id"), reason, permanent)
    d.failed.append(err)
    if not permanent:
        raise err
    return None


def call(method, files=None, **params):
    """POST <api>/bot<token>/<method>, paced (MIN_GAP); a 429 «Too Many Requests» waits retry_after and tries once more.
    params: None values dropped, dict/list ones JSON-encoded (form fields, which the Bot API accepts for every method);
    files: {field: path or (name, bytes)} -> multipart."""
    d = _delivery.get()
    key = d.key(method, params) if d is not None and _delivers(method) else None
    if key and key in d.replay:  # went out on an earlier attempt of this job
        d.sent[key] = d.replay[key]
        return d.replay[key]
    for attempt in (0, 1):
        res = _call(method, files, **params)
        if not (isinstance(res, tuple) and res[0] == 429):
            if key and res is not None:
                d.sent[key] = res
            return res
        if attempt == 0:
            time.sleep(min(res[1], 30))
    log.warning("telegram %s: still rate limited", method)
    return _failed(method, params, "still rate limited (429)", False)


def _call(method, files=None, **params):
    url = base()
    if not url:
        log.warning("telegram %s skipped: BOT_TOKEN is not set", method)
        return None
    data = {k: json.dumps(v, ensure_ascii=False) if k in JSON_PARAMS or isinstance(v, (dict, list)) else
            ("true" if v is True else "false" if v is False else str(v)) for k, v in params.items() if v is not None}
    opened = []
    try:
        up = None
        if files:
            up = {}
            for k, f in files.items():
                if isinstance(f, (str, os.PathLike)):
                    fh = open(f, "rb")
                    opened.append(fh)
                    up[k] = (os.path.basename(str(f)), fh)
                else:
                    up[k] = f
        _pace()
        r = _client().post(f"{url}/{method}", data=data, files=up)
    except httpx.TransportError as e:  # network, timeout: worth a retry
        log.warning("telegram %s error: %r", method, e)
        return _failed(method, params, repr(e), False)
    except Exception as e:  # missing file, bad params: never propagate into business logic
        log.warning("telegram %s error: %r", method, e)
        return _failed(method, params, repr(e), True)
    finally:
        for fh in opened:
            fh.close()
    status = getattr(r, "status_code", 200)
    try:
        body = r.json()
        if not isinstance(body, dict):
            raise ValueError(type(body).__name__)
    except Exception as e:  # a proxy's HTML error page
        log.warning("telegram %s: HTTP %s, bad JSON: %r", method, status, e)
        return _failed(method, params, f"HTTP {status}", not (status >= 500 or status == 429))
    if body.get("error_code") == 429:
        return 429, int((body.get("parameters") or {}).get("retry_after") or 1)
    if not body.get("ok"):
        log.warning("telegram %s failed: %s", method, body.get("description"))
        code = int(body.get("error_code") or status or 0)
        # 400 chat not found / 403 blocked by the user: the same again would fail the same way; 5xx: Telegram's side
        return _failed(method, params, f"{code} {body.get('description') or ''}".strip(), code < 500)
    return body.get("result")


_TOKEN = re.compile(r"<[^>]*>|&(?:#\d+|#x[0-9a-fA-F]+|[a-zA-Z]+);|[\s\S]", re.S)


def clip(text, limit, html=True):
    """Fit a message into Telegram's limit (counted on the visible text). Plain text is cut; HTML is cut between
    tags/entities (never inside one) and the tags left open are closed, so the markup stays valid."""
    text = text or ""
    if not html:
        return text if len(text) <= limit else text[:limit - 1] + "…"
    toks = _TOKEN.findall(text)
    visible = sum(1 for t in toks if not t.startswith("<"))
    if visible <= limit:
        return text
    out, n, open_ = [], 0, []
    for t in toks:
        if t.startswith("<"):
            name = re.match(r"</?\s*([a-zA-Z0-9-]+)", t)
            if name and not t.endswith("/>"):
                if t.startswith("</"):
                    if name[1].lower() in open_:
                        del open_[len(open_) - 1 - open_[::-1].index(name[1].lower())]
                else:
                    open_.append(name[1].lower())
            out.append(t)
            continue
        if n >= limit - 1:
            break
        out.append(t)
        n += 1
    while out and out[-1].startswith("<") and not out[-1].startswith("</"):  # don't leave an empty opened tag at the end
        name = re.match(r"<\s*([a-zA-Z0-9-]+)", out.pop())
        if name and name[1].lower() in open_:
            del open_[len(open_) - 1 - open_[::-1].index(name[1].lower())]
    return "".join(out) + "…" + "".join(f"</{t}>" for t in reversed(open_))


def plain_to_html(text, limit):
    """Plain text -> escaped HTML that fits `limit` (cut before escaping, so no entity is ever split)."""
    return _html.escape(clip(text, limit, html=False))


def kb(rows):
    """[[button, ...], ...] -> inline_keyboard markup; falsy buttons and empty rows dropped."""
    rows = [[b for b in row if b] for row in rows or []]
    return {"inline_keyboard": [r for r in rows if r]}


def cb(text, data):
    return {"text": text, "callback_data": data}


def url_btn(text, url):
    return url and {"text": text, "url": url}


def app_btn(text, url, private=True):
    """Mini App button: web_app in private chats (https only), plain url button in groups."""
    if not url:
        return None
    if private and url.startswith("https://"):
        return {"text": text, "web_app": {"url": url}}
    return {"text": text, "url": url}


def send(chat_id, text, keyboard=None, html=True, thread_id=None, **kw):
    return call("sendMessage", chat_id=chat_id, text=clip(text, 4096, html), parse_mode="HTML" if html else None,
                reply_markup=keyboard, message_thread_id=thread_id, link_preview_options={"is_disabled": True}, **kw)


def send_photo(chat_id, photo, caption, keyboard=None, html=True, thread_id=None):
    """photo: local path (uploaded), file_id or URL."""
    p = dict(chat_id=chat_id, caption=clip(caption, 1024, html), parse_mode="HTML" if html else None, reply_markup=keyboard,
             message_thread_id=thread_id)
    if isinstance(photo, str) and os.path.exists(photo):
        return call("sendPhoto", files={"photo": photo}, **p)
    return call("sendPhoto", photo=photo, **p)


def edit(chat_id, message_id, text, keyboard=None, html=True):
    return call("editMessageText", chat_id=chat_id, message_id=message_id, text=clip(text, 4096, html),
                parse_mode="HTML" if html else None, reply_markup=keyboard, link_preview_options={"is_disabled": True})


def edit_caption(chat_id, message_id, caption, keyboard=None):
    return call("editMessageCaption", chat_id=chat_id, message_id=message_id, caption=clip(caption, 1024), parse_mode="HTML",
                reply_markup=keyboard)


def edit_markup(chat_id, message_id, keyboard):
    return call("editMessageReplyMarkup", chat_id=chat_id, message_id=message_id, reply_markup=keyboard or {"inline_keyboard": []})
