"""E2E check (slow, ~2–4 min): the CRM ↔ Telegram channel on test data, end to end over HTTP as the frontend does it.

A fresh database (dropped and migrated), the API (uvicorn in a thread, real HTTP on localhost), the worker's jobs
(worker.tick() after each step), and a FAKE Telegram Bot API (bot/test/e2e/fake_tg.py + what is live in each chat now)
— nothing reaches the real Telegram, myhome / ss.ge / korter or any other host (outbound HTTP goes to a dead proxy).

  E2E_DATABASE_URL=postgresql+psycopg://t:t@localhost:55432/homes_e2e_channel_test \\
      .venv/bin/python backend/scripts/e2e_channel.py [--keep]   # --keep: leave the stack up at the end (Ctrl-C)

Prints «step → expected → got → ok/BUG» per check and exits 1 on any BUG.
"""
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
DB_URL = os.environ.get("E2E_DATABASE_URL", "postgresql+psycopg://t:t@localhost:55432/homes_e2e_channel_test")
if "test" not in DB_URL.rsplit("/", 1)[-1] or not any(h in DB_URL for h in ("@localhost:", "@127.0.0.1:")):
    sys.exit("E2E_DATABASE_URL must be a local database whose name contains 'test' (it is dropped)")


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


TG_PORT, API_PORT = free_port(), free_port()
TMP = Path(tempfile.mkdtemp(prefix="e2e_channel_"))
BOT_ID = 7000000001
CH = {"rent": "@e2e_rent", "sale": "@e2e_sale", "commercial": "@e2e_commercial", "originals": "@e2e_originals"}
os.environ.update({
    "DATABASE_URL": DB_URL, "TEST_DATABASE_URL": "", "SECRET_KEY": "e2e-secret-key-that-is-long-enough-for-hs256-ok",
    "APP_ENV": "dev", "BOT_TOKEN": f"{BOT_ID}:test", "BOT_USERNAME": "homes_e2e_bot", "TG_API_BASE": f"http://127.0.0.1:{TG_PORT}",
    "PUBLISH_CHAT_ID": CH["rent"], "AGENCY_CHANNEL": CH["rent"][1:], "RICH_POSTS": os.environ.get("RICH_POSTS", "1"),
    "MEDIA_STORAGE": "local", "MEDIA_DIR": str(TMP / "media"), "ADMIN_BOOTSTRAP_LOGIN": "", "SUPERADMIN_TG_IDS": "",
    "OPERATORS_CHAT_ID": "", "WORK_GROUP_CHAT_ID": "", "USERBOT_URL": "", "READER_URL": "", "OPENAI_API_KEY": "", "APIFY_TOKEN": "",
    "GOOGLE_SA_JSON": "", "PHOTO_VECTORS": "0", "PUBLIC_URL": "https://crm.e2e.test", "CHROME_BIN": os.environ.get("CHROME_BIN", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"), "SITE_URL": "https://site.e2e.test",
    # every outbound request dies at a dead proxy; only the fake Telegram and the API on localhost answer
    "HTTP_PROXY": "http://127.0.0.1:9", "HTTPS_PROXY": "http://127.0.0.1:9", "ALL_PROXY": "http://127.0.0.1:9",
    "NO_PROXY": "127.0.0.1,localhost", "no_proxy": "127.0.0.1,localhost",
})
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(REPO / "bot" / "test" / "e2e"))

import fake_tg  # noqa: E402
import httpx  # noqa: E402

SENDS = ("sendMessage", "sendPhoto", "sendVideo", "sendDocument", "sendMediaGroup", "sendRichMessage", "sendLocation")


class FakeTG(fake_tg.FakeTelegram):
    """fake_tg + what is in each chat now (live: chat -> {message_id: seq of the call that sent it}), refused chats
    (the bot is not an admin there: every call fails), channel admin rights for the bot, deleteMessage(s)."""

    def __init__(self, files_dir):
        super().__init__(files_dir)
        self.live, self.refuse = {}, set()

    def cid(self, raw):
        raw = str(raw)
        if raw.startswith("@"):
            return self.usernames.setdefault(raw[1:], -1009000 - len(self.usernames))
        return int(raw)

    def api(self, method, p, files):
        if "chat_id" in p:
            p["chat_id"] = str(self.cid(p["chat_id"]))
            chat = int(p["chat_id"])
            if chat in self.refuse:
                self.record(method + ":refused", dict(p), {})
                raise PermissionError("Forbidden: bot is not a member of the channel chat")
        if method == "getChatMember":
            return {"status": "administrator", "can_post_messages": True, "can_delete_messages": True, "user": fake_tg.BOT_USER}
        if method == "getChat":
            return {"id": int(p["chat_id"]), "type": "private" if int(p["chat_id"]) > 0 else "channel"}
        if method in ("deleteMessage", "deleteMessages"):
            ids = p.get("message_ids") or [p.get("message_id")]
            ids = json.loads(ids) if isinstance(ids, str) else ids
            self.record(method, dict(p), {}, message_ids=[int(i) for i in ids])
            with self.lock:
                for i in ids:
                    self.live.get(int(p["chat_id"]), {}).pop(int(i), None)
            return True
        if method.startswith("edit") and p.get("message_id") and int(p["message_id"]) not in self.live.get(int(p["chat_id"]), {}):
            raise LookupError("Bad Request: message to edit not found")
        return super().api(method, p, files)

    def record(self, method, p, files, **extra):
        super().record(method, p, files, **extra)
        if method in SENDS and "chat_id" in p:
            with self.lock:
                e = self.log[-1]
                for mid in extra.get("message_ids") or [extra.get("message_id")]:
                    self.live.setdefault(int(p["chat_id"]), {})[mid] = e["seq"]

    # ---- the tester's view
    def chat_of(self, name):
        return self.cid(name)

    def posts(self, name):
        """The posts in a chat now: one per send call with a live message (an album = one post), oldest first."""
        chat = self.chat_of(name)
        with self.lock:
            seqs = sorted(set(self.live.get(chat, {}).values()))
            return [next(x for x in self.log if x["seq"] == s) for s in seqs]

    def delete_by_hand(self, name, mid):
        """An operator deletes a post in the channel app (the Bot API sends the bot nothing about it)."""
        with self.lock:  # the whole album, as «Delete» on a post in the app does
            live = self.live.get(self.chat_of(name), {})
            seq = live.get(int(mid))
            for m in [m for m, s in live.items() if s == seq]:
                live.pop(m)

    def dms(self, tg_id, since=0):
        return [x for x in self.calls(chat=int(tg_id), since=since) if x["method"] in SENDS]


def text_of(x):
    t = x.get("text") or x.get("caption") or ""
    if x.get("media"):
        t = t or " | ".join(m.get("caption") or "" for m in x["media"])
    if x.get("rich_message"):
        t = t or x["rich_message"].get("html", "")
    return t


def buttons_of(x):
    if x.get("rich_message"):
        import re
        return re.findall(r"<tg-button[^>]*>([^<]*)</tg-button>", x["rich_message"].get("html", ""))
    return [b["text"] for row in fake_tg.FakeTelegram.markup(x) for b in row]


# ------------------------------------------------------------------------------------------------ report

ROWS = []


def check(step, expected, got, ok):
    ROWS.append((step, expected, str(got), bool(ok)))
    print(f"{'ok ' if ok else 'BUG'} | {step} | {expected} | {got}", flush=True)
    return ok


def eq(step, expected, got):
    return check(step, repr(expected), repr(got), expected == got)


# ------------------------------------------------------------------------------------------------ the stack

def fresh_db():
    import psycopg
    base, name = DB_URL.rsplit("/", 1)
    admin = base.replace("postgresql+psycopg://", "postgresql://") + "/postgres"
    with psycopg.connect(admin, autocommit=True) as c:
        c.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        c.execute(f'CREATE DATABASE "{name}"')
    r = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND, capture_output=True, text=True)
    if r.returncode:
        sys.exit("alembic failed:\n" + r.stderr[-3000:])


def no_network_stubs():
    """Search on the sites (myhome / ss.ge / korter) and the userbot are faked; the rest is blocked by the proxy."""
    from app.services import myhome_copies, users
    myhome_copies._page = lambda query: None
    myhome_copies.ss_search = lambda queries, pages=3: []
    myhome_copies.kr_search = lambda slug, query, pause=0.5: []
    users.tg_birth_date = lambda tg_id: None


def start_api():
    import uvicorn
    from app.main import app
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=API_PORT, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(100):
        if server.started:
            return server
        time.sleep(0.1)
    sys.exit("uvicorn did not start")


def work(rounds=3):
    """The worker: every due job, a few passes (a job may schedule another)."""
    from app import worker
    out = {}
    for _ in range(rounds):
        st = worker.tick(limit=200)
        for k, v in st.items():
            out[k] = out.get(k, 0) + v
        if not st:
            break
    return out


class Api:
    def __init__(self, token=None):
        self.c = httpx.Client(base_url=f"http://127.0.0.1:{API_PORT}/api", timeout=120,
                              headers={"Authorization": f"Bearer {token}"} if token else {})

    def _do(self, method, path, ok=True, **kw):
        r = self.c.request(method, path, **kw)
        if ok and r.status_code >= 400:
            raise AssertionError(f"{method} {path} -> {r.status_code} {r.text[:600]}")
        try:
            return r.json() if r.content else None
        except ValueError:
            return r.content

    def get(self, path, **kw):
        return self._do("GET", path, **kw)

    def post(self, path, **kw):
        return self._do("POST", path, **kw)

    def put(self, path, **kw):
        return self._do("PUT", path, **kw)

    def patch(self, path, **kw):
        return self._do("PATCH", path, **kw)

    def raw(self, method, path, **kw):
        return self.c.request(method, path, **kw)


def make_users():
    from app.db import SessionLocal
    from app.models import User
    from app.services import users as U
    people = {"admin": ("superadmin", 9100001, "Стас"), "op": ("operator", 9100002, "Зураб"), "agent": ("agent", 9100003, "Нино"),
              "agent2": ("agent", 9100005, "Гио"), "recruit": ("recruit", 9100004, "Леван")}
    out = {}
    with SessionLocal() as db:
        for key, (role, tg_id, name) in people.items():
            u = User(name=name, role=role, tg_id=tg_id, username=f"e2e_{key}", login=f"e2e_{key}", phone="+995 599 111 222",
                     password_hash=U.hash_password("pw"), birth_date=datetime(1990, 5, 4).date(), email=f"{key}@e2e.test")
            if role == "recruit":
                u.mentor_id = None
            db.add(u)
            db.flush()
            out[key] = (u.id, tg_id)
        db.commit()
    apis = {}
    for key in out:
        tok = Api().post("/auth/login", json={"login": f"e2e_{key}", "password": "pw"})
        apis[key] = Api(tok.get("token") or tok.get("access_token"))
    return out, apis


def photos_for(seed, n=10):
    """n JPEGs of their own for each object (shared photos would make every object a «Дубль в канале» of the others)."""
    import random
    from PIL import Image, ImageDraw
    rnd = random.Random(seed)
    d = TMP / "src" / str(seed)
    d.mkdir(parents=True, exist_ok=True)
    out = []
    for n_ in range(n):
        im = Image.new("RGB", (1280, 960), tuple(rnd.randrange(256) for _ in range(3)))
        dr = ImageDraw.Draw(im)
        for _ in range(25):
            x, y = rnd.randrange(1200), rnd.randrange(900)
            dr.rectangle((x, y, x + rnd.randrange(40, 400), y + rnd.randrange(40, 300)), fill=tuple(rnd.randrange(256) for _ in range(3)))
        p = d / f"p{n_}.jpg"
        im.save(p, "JPEG", quality=85)
        out.append(p)
    return out


def media_files():
    """The first object's photos and a 3 s mp4 (ffmpeg)."""
    video = TMP / "src" / "v.mp4"
    photos = photos_for(0)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=640x360:rate=25", "-t", "3", "-pix_fmt", "yuv420p",
                    str(video)], check=True)
    return photos, video


# ------------------------------------------------------------------------------------------------ the walk

FAKE: FakeTG = None
U, A = {}, {}


def channel_state(step, name, n, *, pid=None):
    """n posts in the chat now; with pid: each is this object's (its CRM link / p<id> start)."""
    posts = FAKE.posts(name)
    ok = len(posts) == n
    check(step, f"{name}: {n} пост(ов)", f"{len(posts)}: {[ (x['method'], text_of(x)[:50]) for x in posts]}", ok)
    return posts


def prop(pid, who="op"):
    return A[who].get(f"/properties/{pid}")


POST_FIELDS = {"deal": "Rent", "prop_type": "Apartment", "building": "NewBuilding", "design": "New", "heating": "CentralHeating",
               "pets": "ByAgreement", "periods": ["12Month"]}


def new_object(agent="agent", address="ул. Палиашвили 12", price=900, phone="+995 555 10 20 30", n_photos=9, video=True,
               rooms=None, **kw):
    """The agent's «Объект вручную» with the owner on the spot, the card filled, photos (+ video) uploaded -> its card."""
    a = A[agent]
    body = {"address": address, "district": "Ваке", "lat": 41.7101, "lng": 44.7612, "price": price, "currency": "USD",
            "bedrooms": 2, "rooms": 3, "area": 70, "floor": 4, "total_floors": 9, "owner_name": "Нана Беридзе",
            "owner_phone": phone, "post_fields": POST_FIELDS, "description": "Светлая квартира с ремонтом"}
    body.update(kw)
    p = a.post("/properties", json=body)
    photos = PHOTOS if p["id"] == 1 else photos_for(p["id"])
    for n, f in enumerate(photos[:n_photos]):
        room = (rooms or [])[n] if rooms and n < len(rooms) else None
        a.post(f"/properties/{p['id']}/media", files={"files": (f.name, f.read_bytes(), "image/jpeg")}, data={"room": room} if room else {})
    if video:
        a.post(f"/properties/{p['id']}/media", files={"files": ("tour.mp4", VIDEO.read_bytes(), "video/mp4")})
    return a.get(f"/properties/{p['id']}")


def posts_of(name, pid):
    """The live posts in a chat that are this object's (its «Contact» / CRM link carries p<id>)."""
    return [x for x in FAKE.posts(name) if f"start=p{pid}" in json.dumps(x, ensure_ascii=False)
            or f"q=o{pid}" in json.dumps(x, ensure_ascii=False)]


def one_post(step, pid, name=None):
    """Exactly one post of the object, in `name` (default the rent channel), none anywhere else."""
    name = name or CH["rent"]
    here = posts_of(name, pid)
    elsewhere = {c: len(posts_of(c, pid)) for c in (CH["rent"], CH["sale"], CH["commercial"]) if c != name and posts_of(c, pid)}
    check(step, f"1 пост объекта в {name}, в других каналах 0", f"{len(here)} в {name}; другие: {elsewhere or 0}",
          len(here) == 1 and not elsewhere)
    return here[0] if here else None


def no_post(step, pid):
    left = {c: len(posts_of(c, pid)) for c in (CH["rent"], CH["sale"], CH["commercial"]) if posts_of(c, pid)}
    check(step, "постов объекта в каналах нет", left or 0, not left)


def dms_to(key, since):
    return [text_of(x) for x in FAKE.dms(U[key][1], since)]


def audience(step, since, needle, want, deny=()):
    """Who got a DM containing needle since the mark: everyone in want, nobody in deny."""
    got = {k for k in U if any(needle in t for t in dms_to(k, since))}
    check(step, f"«{needle}» → {sorted(want)}, не {sorted(deny)}", sorted(got), set(want) <= got and not (got & set(deny)))
    return got


def safe_step(fn):
    def run():
        print(f"\n=== {fn.__doc__.strip().splitlines()[0]}", flush=True)
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            check(fn.__name__, "шаг проходит без ошибок", f"{type(e).__name__}: {str(e)[:400]}", False)
            traceback.print_exc()
    return run


STATE = {}


@safe_step
def step1():
    """1) агент создаёт эксклюзив без е-подписи → собственник подписывает по ссылке → фото/видео/категории → проверка → публикация"""
    settings = A["admin"].get("/settings")
    rooms = [x for x in (settings.get("photo_rooms") or "").split("\n") if x]
    check("1 категории фото", "есть Прихожая/Фасад/Гардероб/Терраса/Кабинет/Санузел, нет «Ванная»", rooms,
          {"Прихожая", "Фасад", "Гардероб", "Терраса", "Кабинет", "Санузел"} <= set(rooms) and "Ванная" not in rooms)
    p = new_object(rooms=["Прихожая", "Фасад", "Гардероб", "Терраса", "Кабинет", "Санузел", "Гостиная", "Кухня", "Спальня 1"],
                   is_exclusive=True)
    pid = STATE["pid"] = p["id"]
    eq("1 объект создан агентом", "media_uploaded", p["status"])
    photo = next(m for m in p["media"] if m["kind"] == "photo")
    r = A["agent"].patch(f"/properties/{pid}/media/{photo['id']}", json={"room": "Вид на Мтацминду"})
    eq("1 «Свой вариант» категории фото", "Вид на Мтацминду", r["room"])
    p = prop(pid)
    eq("1 категории на фото", ["Вид на Мтацминду", "Фасад", "Гардероб", "Терраса", "Кабинет", "Санузел", "Гостиная", "Кухня", "Спальня 1"],
       [m["room"] for m in p["media"] if m["kind"] == "photo"])
    check("1 видео загружено", "1 video", [m["kind"] for m in p["media"]].count("video"), [m["kind"] for m in p["media"]].count("video") == 1)
    r = A["agent"].raw("POST", f"/properties/{pid}/submit")
    eq("1 эксклюзив без договора не уходит на проверку", "no_exclusive_contract", r.json().get("code"))
    mark = FAKE.mark()
    A["agent"].post(f"/properties/{pid}/exclusive-no-esign", data={"reason": "собственник за границей, подпишет позже"})
    work()
    p = prop(pid)
    check("1 без е-подписи: запрос решён системой (дублей нет)", "no_esign approved", (p.get("no_esign") or {}).get("status"),
          (p.get("no_esign") or {}).get("status") == "approved")
    token = p.get("exclusive_sign_token")
    check("1 ссылка на подпись есть", "token", bool(token), bool(token))
    PDF = b"%PDF-1.4 e2e signed contract"
    r = Api().raw("POST", f"/public/exclusive/{token}", data={"full_name": "Нана Беридзе", "personal_id": "01001012345",
                                                             "phone": "+995 555 10 20 30", "consent": "true"},
                  files={"file": ("c.pdf", PDF, "application/pdf"), "id_doc": ("id.jpg", PHOTOS[0].read_bytes(), "image/jpeg"),
                         "extract": ("ex.pdf", PDF, "application/pdf")})
    check("1 собственник подписал по ссылке позже", "200 signed_at", f"{r.status_code} {r.json().get('signed_at') or r.text[:200]}",
          r.status_code == 200 and r.json().get("signed_at"))
    p = prop(pid)
    check("1 договор в карточке", "exclusive_contract", bool(p.get("exclusive_contract")), bool(p.get("exclusive_contract")))
    audience("1 уведомление «подписал эксклюзив»", mark, "подписал эксклюзивный договор", {"agent", "op"}, {"agent2", "recruit"})
    eq("1 карточка ничего не просит", [], p.get("missing"))
    mark = FAKE.mark()
    p = A["agent"].post(f"/properties/{pid}/submit")
    eq("1 на проверку", "review", p["status"])
    audience("1 оператору «на проверку»", mark, f"#{pid}", {"op"})
    A["admin"].put("/settings", json={"originals_chat_id": CH["originals"], "publish_chat_sale": CH["sale"],
                                      "publish_chat_commercial": CH["commercial"]})
    mark = FAKE.mark()
    p = A["op"].post(f"/properties/{pid}/review", json={"approve": True, "comment": "ок"})
    eq("1 опубликован", "published", p["status"])
    check("1 ссылка на пост в канале аренды", f"t.me/{CH['rent'][1:]}/…", p.get("post_url"), f"t.me/{CH['rent'][1:]}/" in (p.get("post_url") or ""))
    post = one_post("1 пост в канале аренды", pid)
    if post and post["method"] == "sendRichMessage":
        eq("1 кнопки под постом", ["📍 On the map", "💬 Contact"], buttons_of(post))
    elif post:  # RICH_POSTS=0: an album can't carry buttons; the caption links to the map instead
        check("1 альбом (RICH_POSTS=0): кнопок нет, ссылка на карту в подписи", "APARTMENTS ON MAP", post["method"],
              "APARTMENTS ON MAP" in text_of(post))
    if post:
        STATE["post_mid"] = post["message_id"]
    work()
    oc = [x for x in FAKE.calls(chat=FAKE.chat_of(CH["originals"]), since=mark)]
    seq = [x["method"] + (":" + ",".join(m["type"] for m in x["media"]) if x.get("media") else "") for x in oc]
    check("1 оригиналы: документы → текст → видео", "sendMediaGroup:document×9, sendMessage, sendDocument", seq,
          len(oc) == 3 and oc[0]["method"] == "sendMediaGroup" and all(m["type"] == "document" for m in oc[0]["media"])
          and len(oc[0]["media"]) == 9 and oc[1]["method"] == "sendMessage" and oc[2]["method"] == "sendDocument"
          and (oc[2].get("file") or "").endswith(".mp4"))
    audience("1 агенту «опубликован», оператору (нажал сам) — нет", mark, f"#{pid}", {"agent"}, {"op"})
    work()
    one_post("1 после воркера дублей нет", pid)


def publish_new(agent="agent", **kw):
    """An object made by the agent, sent for review and published by the operator -> its card."""
    p = new_object(agent, **kw)
    A[agent].post(f"/properties/{p['id']}/submit")
    return A["op"].post(f"/properties/{p['id']}/review", json={"approve": True})


def site(pid):
    r = Api().raw("GET", f"/public/site/listings/o{pid}")
    return r.json() if r.status_code == 200 else None


@safe_step
def step2():
    """2) «Обновить пост», «% Скидка», «Править» поля, «Редактировать пост» → перевыкладка без дублей"""
    pid = STATE["pid"]
    old = STATE["post_mid"]
    mark = FAKE.mark()
    p = A["op"].post(f"/properties/{pid}/publish", json={"channel": "tg", "tg": True, "site": True})
    post = one_post("2 «Обновить пост»: один пост", pid)
    check("2 «Обновить пост»: старый удалён, новый вышел", f"старый #{old} удалён, новый ≠ {old}",
          post and post["message_id"], post and post["message_id"] != old and old not in FAKE.live.get(FAKE.chat_of(CH["rent"]), {}))
    eq("2 ссылка в CRM на новый пост", f"https://t.me/{CH['rent'][1:]}/{post['message_id'] if post else '?'}", p["post_url"])
    work()
    oc = FAKE.calls(chat=FAKE.chat_of(CH["originals"]), since=mark)
    eq("2 оригиналы при перевыкладке с теми же фото не шлются", 0, len(oc))
    one_post("2 после воркера дублей нет", pid)

    # % Скидка (the operator: an unlocked edit), as DiscountModal sends it
    mark = FAKE.mark()
    p = prop(pid)
    r = A["op"].patch(f"/properties/{pid}", json={"price": 800, "post_fields": {**p["post_fields"], "discount": True}})
    eq("2 «% Скидка»: цена в CRM", 800, float(r["price"]))
    check("2 «% Скидка»: перевыкладка в очереди", "без второй кнопки", "worker", True)
    work()
    post = one_post("2 «% Скидка»: один пост после перевыкладки", pid)
    t = text_of(post or {})
    import re
    check("2 «% Скидка»: в посте новая цена и #Discount", "$800 и #Discount, без 900", re.findall(r"[^<>]{0,25}(?:800|900|Discount)[^<>]{0,15}", t),
          ("$800" in t or "800$" in t) and "#Discount" in t and "$900" not in t and "900$" not in t)
    s_ = site(pid)
    check("2 «% Скидка»: цена на сайте", "800", s_ and s_.get("price"), s_ is not None and "800" in json.dumps(s_))
    audience("2 скидка: агенту уведомление? (нет требования)", mark, "Скидка", set(), {"op"})

    # «Править» a post field by the operator → repost; a field not in the post → no repost
    old = post and post["message_id"]
    A["op"].patch(f"/properties/{pid}", json={"area": 75})
    work()
    post = one_post("2 «Править» площадь: один пост", pid)
    t = text_of(post or {})
    check("2 «Править» площадь: пост перевыложен с 75", "новый пост, 75 м²", (post and post["message_id"], "75" in t),
          post and post["message_id"] != old and "75" in t)
    mark = FAKE.mark()  # two quick edits before the worker comes: one repost
    A["op"].patch(f"/properties/{pid}", json={"floor": 5})
    A["op"].patch(f"/properties/{pid}", json={"floor": 6})
    work()
    sent = [x for x in FAKE.calls(chat=FAKE.chat_of(CH["rent"]), since=mark) if x["method"] in SENDS]
    eq("2 две правки подряд → одна перевыкладка", 1, len(sent))
    post = one_post("2 две правки подряд: один пост", pid)
    old = post and post["message_id"]
    A["op"].patch(f"/properties/{pid}", json={"cadastral_code": "01.10.11.011.011"})
    work()
    post = one_post("2 правка поля не из поста", pid)
    eq("2 правка поля не из поста: пост не трогается", old, post and post["message_id"])

    # «Редактировать пост» = the «Править» form by the agent: a verified object → locked fields go to the operator
    mark = FAKE.mark()
    r = A["agent"].patch(f"/properties/{pid}", json={"price": 750, "post_fields": {**prop(pid)["post_fields"], "discount": True},
                                                   "reason": "собственник снизил"})
    cr = r.get("change_request")
    check("2 скидка агентом на проверенном объекте → запрос оператору", "change_request pending", cr and cr.get("status"),
          cr and cr.get("status") == "pending")
    audience("2 запрос оператору пришёл оператору", mark, "", {"op"}, {"agent"})
    work()
    eq("2 до решения оператора пост не меняется", old, (posts_of(CH["rent"], pid) or [{}])[0].get("message_id"))
    A["op"].post(f"/change-requests/{cr['id']}/decide", json={"approve": True})
    work()
    post = one_post("2 запрос одобрен → перевыкладка", pid)
    t = text_of(post or {})
    check("2 запрос одобрен: пост с ценой 750", "750", t[:120], "750" in t)
    eq("2 цена в CRM после одобрения", 750, float(prop(pid)["price"]))
    STATE["post_mid"] = post and post["message_id"]


@safe_step
def step3():
    """3) «Снять только из канала/с сайта» и обратно; «Снять с публикации» / «Опубликовать снова»; «Приостановить» / «Снять с паузы»"""
    pid = STATE["pid"]
    p = A["op"].post(f"/properties/{pid}/unpost")
    no_post("3 «Снять только из канала»: поста нет", pid)
    check("3 «Снять только из канала»: статус и сайт остались", "published, на сайте", (p["status"], p["site_hidden"], p.get("post_url")),
          p["status"] == "published" and not p["site_hidden"] and site(pid) is not None and not p.get("post_url"))
    work()
    no_post("3 после воркера пост не вернулся", pid)
    p = A["op"].post(f"/properties/{pid}/publish", json={"channel": "tg", "tg": True, "site": True})
    one_post("3 «Выложить в канал» обратно", pid)
    p = A["op"].post(f"/properties/{pid}/site", json={"on": False})
    check("3 «Снять только с сайта»: сайт 404, пост остался", "site None, 1 пост", (site(pid) is None, p["status"]),
          site(pid) is None and p["status"] == "published")
    one_post("3 «Снять только с сайта»: пост на месте", pid)
    p = A["op"].post(f"/properties/{pid}/site", json={"on": True})
    check("3 «Вернуть на сайт»", "на сайте", site(pid) is not None, site(pid) is not None)
    work()
    one_post("3 сайт туда-обратно: пост один", pid)

    mark = FAKE.mark()
    p = A["agent"].post(f"/properties/{pid}/unpublish")
    eq("3 «Снять с публикации» агентом: архив/unpublished", ("archived", "unpublished"), (p["status"], p["archive_reason"]))
    check("3 «Снять с публикации»: сайт", "404", site(pid), site(pid) is None)
    work()
    no_post("3 «Снять с публикации»: поста нет", pid)
    audience("3 «Снять с публикации» агентом → оператору", mark, f"#{pid}", {"op"}, {"agent"})
    mark = FAKE.mark()
    p = A["op"].post(f"/properties/{pid}/resume", json={"republish": False})
    eq("3 «Опубликовать снова»", "published", p["status"])
    work()
    one_post("3 «Опубликовать снова»: один пост", pid)
    check("3 «Опубликовать снова»: сайт", "на сайте", site(pid) is not None, site(pid) is not None)
    audience("3 «Опубликовать снова» оператором → агенту", mark, f"#{pid}", {"agent"}, {"op"})

    mark = FAKE.mark()
    p = A["agent"].post(f"/properties/{pid}/archive", json={"reason": "paused", "comment": "собственник уехал на неделю"})
    cr = p.get("change_request")
    check("3 «Приостановить» агентом (объект проверен) → запрос оператору", "change_request pending", (p["status"], cr and cr["status"]),
          p["status"] == "published" and cr and cr["status"] == "pending")
    audience("3 запрос на паузу → оператору", mark, "", {"op"}, {"agent"})
    one_post("3 до решения пост на месте", pid)
    mark = FAKE.mark()
    A["op"].post(f"/change-requests/{cr['id']}/decide", json={"approve": True})
    p = prop(pid)
    eq("3 «Приостановить» (одобрено)", ("archived", "paused"), (p["status"], p["archive_reason"]))
    work()
    no_post("3 «Приостановить»: пост удалён", pid)
    check("3 «Приостановить»: сайт", "404", site(pid), site(pid) is None)
    audience("3 запрос одобрен → агенту", mark, "", {"agent"}, {"op"})
    p = A["agent"].post(f"/properties/{pid}/resume", json={})
    eq("3 «Снять с паузы»", "published", p["status"])
    work()
    post = one_post("3 «Снять с паузы»: пост снова", pid)
    STATE["post_mid"] = post and post["message_id"]


@safe_step
def step4():
    """4) пост удалили в канале руками → сверка post_sync → объект снят везде"""
    from app.db import SessionLocal
    from app.services import post_sync
    pid = STATE["pid"]
    post = posts_of(CH["rent"], pid)[0]
    FAKE.delete_by_hand(CH["rent"], post["message_id"])
    post_sync.alive = lambda channel, msgs: {m for m in msgs if m in FAKE.live.get(FAKE.chat_of("@" + channel), {})}
    mark = FAKE.mark()
    with SessionLocal() as db:
        n = post_sync.run(db, pause=0)
    eq("4 сверка нашла удалённый пост", 1, n)
    p = prop(pid)
    eq("4 объект снят: архив, «Сдал сам»", ("archived", "rented_by_owner"), (p["status"], p["archive_reason"]))
    check("4 снят с сайта", "404", site(pid), site(pid) is None)
    work()
    no_post("4 в канале ничего не появилось", pid)
    rented = [x for x in FAKE.calls(chat=FAKE.chat_of(CH["rent"]), since=mark) if x["method"].startswith("send")]
    eq("4 без #FlatRented (удалили руками)", 0, len(rented))
    audience("4 «Пост удалён в канале» → агенту и оператору", mark, "Пост удалён в канале", {"agent", "op"})
    with SessionLocal() as db:
        eq("4 повторная сверка ничего не трогает", 0, post_sync.run(db, pause=0))


@safe_step
def step5():
    """5) продажа и коммерция — в свои каналы; бот не админ → основной канал"""
    sale = publish_new("agent2", address="пр. Чавчавадзе 30", price=150000, phone="+995 555 30 30 30",
                       post_fields={**POST_FIELDS, "deal": "Sale", "sale_price": 150000})
    one_post("5 продажа → канал продажи", sale["id"], CH["sale"])
    comm = publish_new("agent2", address="ул. Абашидзе 5", price=2500, phone="+995 555 50 50 50",
                       post_fields={**POST_FIELDS, "prop_type": "Commercial"})
    one_post("5 коммерция → канал коммерции", comm["id"], CH["commercial"])
    p = A["op"].post(f"/properties/{sale['id']}/publish", json={"channel": "tg", "tg": True, "site": True})
    one_post("5 «Обновить пост» продажи: в том же канале, один", sale["id"], CH["sale"])
    FAKE.refuse.add(FAKE.chat_of(CH["sale"]))
    sale2 = publish_new("agent2", address="ул. Барнова 7", price=99000, phone="+995 555 70 70 70",
                        post_fields={**POST_FIELDS, "deal": "Sale", "sale_price": 99000})
    one_post("5 канал продажи отказал → основной канал", sale2["id"], CH["rent"])
    warn = json.dumps(sale2, ensure_ascii=False)
    check("5 карточка предупреждает, что ушло в основной", "«Бот не админ в …»", "Бот не админ" in warn, "Бот не админ" in warn)
    p = A["op"].post(f"/properties/{sale['id']}/publish", json={"channel": "tg", "tg": True, "site": True})
    eq("5 перевыкладка продажи при отказе канала → основной канал", 1, len(posts_of(CH["rent"], sale["id"])))
    pubs = [x for x in p.get("publications") or [] if x.get("delete_error")]
    check("5 старый пост в отказавшем канале не удалить — карточка показывает ошибку", "delete_error в publications",
          [(x.get("url"), x.get("delete_error")) for x in pubs], len(posts_of(CH["sale"], sale["id"])) == 1 and pubs)
    FAKE.refuse.discard(FAKE.chat_of(CH["sale"]))
    STATE["sale"] = sale["id"]


def png_signature():
    import base64
    import io
    from PIL import Image, ImageDraw
    im = Image.new("RGBA", (300, 100), (255, 255, 255, 0))
    ImageDraw.Draw(im).line((10, 80, 100, 20, 200, 70, 290, 30), fill=(0, 0, 0, 255), width=4)
    b = io.BytesIO()
    im.save(b, "PNG")
    return "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()


@safe_step
def step6():
    """6) договор аренды → подписи обеих сторон → блок через 24 ч → сделка → подтверждение → «Сдан» + #FlatRented → «Вернуть в работу»"""
    from app.db import SessionLocal
    from sqlalchemy import text as sql
    pid = publish_new("agent", address="ул. Иракли Абашидзе 40", price=1200, phone="+995 555 60 60 60")["id"]
    STATE["pid6"] = pid
    one_post("6 объект в канале", pid)
    a = A["agent"]
    pre = a.get(f"/properties/{pid}/contract")
    c = a.post("/contracts", json={"kind": "rent", "lang": "RU", "property_id": pid, "address": pre.get("address") or "ул. Иракли Абашидзе 40",
                                   "client_name": "Джон Смит", "owner_name": "Нана Беридзе",
                                   "html": "<h1>Договор аренды</h1><p>Квартира, 1200 $ в месяц.</p>"})
    eq("6 договор создан", "draft", c["status"])
    c = a.post(f"/contracts/{c['id']}/esign")
    sig = png_signature()
    mark = FAKE.mark()
    for s in c["esign"]["signers"]:
        tok = s["path"].rsplit("/", 1)[-1]
        r = Api().raw("POST", f"/public/esign/{tok}", json={"full_name": "Нана Беридзе" if s["role"] == "owner" else "John Smith",
                                                            "personal_id": "01001012345", "phone": "+995 555 60 60 60",
                                                            "consent": True, "signature": sig, "doc_sha256": c["esign"]["doc_sha256"]})
        check(f"6 подпись: {s['role']}", "200", f"{r.status_code} {r.text[:150] if r.status_code != 200 else ''}", r.status_code == 200)
        if s["role"] == "owner":
            audience("6 подпись одной стороны → агенту и оператору", mark, "подписал(а) электронно", {"agent", "op"})
            mark = FAKE.mark()
    c = a.get(f"/contracts/{c['id']}")
    eq("6 договор подписан обеими", "signed", c["status"])
    audience("6 подпись обеих сторон → агенту и оператору", mark, "подписан электронно обеими", {"agent", "op"})
    me = a.get("/auth/me")
    eq("6 сразу после подписи блокировки нет", None, me.get("deal_overdue"))
    with SessionLocal() as db:  # the 24 h are over
        db.execute(sql("UPDATE contracts SET deal_due_at = now() - interval '1 minute' WHERE id = :i"), {"i": c["id"]})
        db.execute(sql("UPDATE jobs SET due_at = now() - interval '1 minute' WHERE kind = 'deal_due' AND ref = :r"), {"r": str(c["id"])})
        db.commit()
    mark = FAKE.mark()
    work()
    audience("6 через 24 ч: «Оформите сделку» агенту и оператору", mark, "Оформите сделку", {"agent", "op"}, {"agent2", "recruit"})
    me = a.get("/auth/me")
    check("6 агент заблокирован", "deal_overdue", me.get("deal_overdue"), bool(me.get("deal_overdue")))
    r = a.raw("PATCH", f"/properties/{pid}", json={"description": "x"})
    eq("6 блок: правка объекта закрыта (423)", 423, r.status_code)
    r = A["agent2"].raw("PATCH", f"/properties/{STATE.get('sale', pid)}", json={"description": "другой агент"})
    check("6 другого агента блок не касается", "не 423", r.status_code, r.status_code != 423)
    mark = FAKE.mark()
    d = a.post("/deals", json={"property_id": pid, "deal_type": "rent", "price": 1200, "commission_total": 600,
                               "client_name": "John Smith", "client_phone": "+995 555 99 99 99", "client_src": "Агент",
                               "rent_from": "2026-12-01", "rent_to": "2027-11-30"})
    eq("6 сделка оформлена агентом", "pending", d["status"])
    me = a.get("/auth/me")
    eq("6 блокировка снята после сделки", None, me.get("deal_overdue"))
    audience("6 «Новая сделка на подтверждение» → оператору, не агенту", mark, "Новая сделка", {"op"}, {"agent"})
    mark = FAKE.mark()
    d = A["op"].post(f"/deals/{d['id']}/confirm")
    eq("6 оператор подтвердил", "confirmed", d["status"])
    p = prop(pid)
    eq("6 объект «Сдан»", "rented", p["status"])
    check("6 сайт снят", "404", site(pid), site(pid) is None)
    work()
    no_post("6 пост объекта удалён", pid)
    fr = [x for x in FAKE.posts(CH["rent"]) if "#FlatRented" in text_of(x) and x["seq"] > mark]
    check("6 #FlatRented: один пост, одно фото", "1 sendPhoto", [(x["method"], text_of(x)[:60]) for x in fr],
          len(fr) == 1 and fr[0]["method"] == "sendPhoto")
    check("6 #FlatRented с хэштегом района", "#Vake", text_of(fr[0]) if fr else "", fr and "#Vake" in text_of(fr[0]))
    audience("6 «Сделка подтверждена» → агенту", mark, "Сделка подтверждена", {"agent"}, {"op"})
    work()
    fr = [x for x in FAKE.posts(CH["rent"]) if "#FlatRented" in text_of(x) and x["seq"] > mark]
    eq("6 повторный проход воркера: #FlatRented не дублируется", 1, len(fr))
    eq("6 договор → «сделка»", "deal", a.get(f"/contracts/{c['id']}")["status"])
    p = a.post(f"/properties/{pid}/resume")  # the deal card's «Вернуть объект в работу»
    eq("6 «Вернуть в работу» из сделки: «Взят» у агента", ("taken", U["agent"][0]), (p["status"], p.get("agent", {}).get("id") if isinstance(p.get("agent"), dict) else p.get("agent_id")))
    work()
    no_post("6 после «Вернуть в работу» в канале объекта нет", pid)
    eq("6 #FlatRented остаётся в канале", 1, len([x for x in FAKE.posts(CH["rent"]) if "#FlatRented" in text_of(x) and x["seq"] > mark]))


@safe_step
def step7():
    """7) рекрут оформляет сделку; уведомления нужным людям, нажавшему — нет"""
    pid = publish_new("recruit", address="ул. Мосашвили 3", price=700, phone="+995 555 77 77 71")["id"]
    one_post("7 объект рекрута в канале", pid)
    mark = FAKE.mark()
    r = A["recruit"].raw("POST", "/deals", json={"property_id": pid, "deal_type": "rent", "price": 700, "commission_total": 350,
                                                 "client_name": "Ana", "client_phone": "+995 555 88 88 88", "client_src": "Рекрут",
                                                 "rent_from": "2026-12-05", "rent_to": "2027-12-04"})
    check("7 рекрут оформляет сделку", "200 pending", f"{r.status_code} {r.text[:300] if r.status_code != 200 else r.json()['status']}",
          r.status_code == 200 and r.json()["status"] == "pending")
    if r.status_code != 200:
        return
    d = r.json()
    audience("7 сделка рекрута → оператору, не рекруту", mark, "Новая сделка", {"op"}, {"recruit"})
    mark = FAKE.mark()
    A["op"].post(f"/deals/{d['id']}/confirm")
    work()
    got = audience("7 подтверждение → рекруту (и агенту объекта?), не оператору", mark, "Сделка подтверждена", {"recruit"}, {"op"})
    no_post("7 пост объекта рекрута удалён", pid)
    p = A["op"].post(f"/properties/{pid}/resume", json={"republish": True})  # staff «Опубликовать снова» on a rented one
    eq("7 «Опубликовать снова» сданного (оператор)", "published", p["status"])
    work()
    one_post("7 сданный опубликован снова: один пост", pid)
    check("7 сайт снова", "на сайте", site(pid) is not None, site(pid) is not None)


@safe_step
def step5b():
    """5b) сделка продажи подтверждена → пост удалён, объявление о продаже (не «found a tenant») в канале продажи"""
    pid = publish_new("agent2", address="ул. Джавахишвили 11", price=120000, phone="+995 555 11 11 19",
                      post_fields={**POST_FIELDS, "deal": "Sale", "sale_price": 120000})["id"]
    one_post("5b продажа в канале продажи", pid, CH["sale"])
    work()
    mark = FAKE.mark()
    d = A["agent2"].post("/deals", json={"property_id": pid, "deal_type": "sale", "price": 120000, "commission_total": 3600,
                                         "client_name": "Buyer", "client_phone": "+995 555 12 12 12", "client_src": "Агент"})
    A["op"].post(f"/deals/{d['id']}/confirm")
    work()
    no_post("5b пост продажи удалён", pid)
    new = [x for x in FAKE.calls(since=mark) if x["method"] in SENDS and int(x.get("chat", 0)) < 0
           and x["chat"] != FAKE.chat_of(CH["originals"])]
    check("5b объявление в канале продажи — о продаже", "#Sold / sold, канал продажи",
          [(x["chat"], text_of(x)[:70]) for x in new],
          bool(new) and all(x["chat"] == FAKE.chat_of(CH["sale"]) and "tenant" not in text_of(x) for x in new))


@safe_step
def step8():
    """8) «Сравнить по ссылке» / «Где ещё выложен» → «Попросить снять» → «Проверено: снято»"""
    from app.services import myhome_copies
    pid = publish_new("agent", address="ул. Чавчавадзе 70", price=1000, phone="+995 555 80 80 80")["id"]
    url = "https://www.myhome.ge/pr/26740808/"
    myhome_copies.by_link = lambda u: {"id": "mh26740808", "source": "myhome", "url": url, "address": "Чавчавадзе 70",
                                       "area": 70, "floor": 4, "bedrooms": 2, "district": "Ваке", "price_usd": 1100,
                                       "text": "Сдаётся квартира в Ваке", "photos": [], "user_type": "agent"}
    r = A["agent"].post(f"/properties/{pid}/compare-link", json={"url": url})
    check("8 «Сравнить по ссылке»: ответ", "linked, pct", (r.get("linked"), r.get("pct"), r.get("level")), r.get("linked") is True)
    work()
    p = A["agent"].get(f"/properties/{pid}")
    ads = p.get("copies") or []
    check("8 «Где ещё выложен» заполнен", "MyHome, привязано", [(a.get("where"), a.get("level"), a.get("who")) for a in ads],
          any(a.get("listing_id") == "mh26740808" for a in ads))
    mark = FAKE.mark()
    p = A["op"].post(f"/properties/{pid}/listings/mh26740808/takedown")
    a = next((x for x in p.get("copies") or [] if x["listing_id"] == "mh26740808"), {})
    check("8 «Попросить снять»: отмечено", "asked", a.get("asked"), bool(a.get("asked")))
    audience("8 «Попросить снять» → задача агенту", mark, "", {"agent"}, {"op"})
    mark = FAKE.mark()
    p = A["op"].post(f"/properties/{pid}/listings/mh26740808/removed")
    left = [x for x in p.get("copies") or [] if x["listing_id"] == "mh26740808"]
    eq("8 «Проверено: снято»: из списка ушло", [], left)
    audience("8 «Проверено: снято» → агенту", mark, f"#{pid}", {"agent"}, {"op"})
    r = A["agent"].raw("POST", f"/properties/{pid}/listings/mh26740808/removed")
    check("8 «Проверено: снято» — только оператор", "403", r.status_code, r.status_code in (401, 403))
    one_post("8 пост объекта не тронут", pid)


def main():
    global FAKE, PHOTOS, VIDEO
    fresh_db()
    FAKE = FakeTG(str(TMP / "tgfiles"))
    FAKE.serve(TG_PORT)
    no_network_stubs()
    start_api()
    import logging
    logging.getLogger("app.request").setLevel(logging.WARNING)
    users, apis = make_users()
    U.update(users)
    A.update(apis)
    PHOTOS, VIDEO = media_files()
    from app.db import SessionLocal
    from app.services import settings as S
    with SessionLocal() as db:  # the connected operator account (prod: Зураб) gets the operators' messages
        S.set(db, "userbot_tg_id", str(U["op"][1]))
    for st in STEPS:
        st()
    bugs = [r for r in ROWS if not r[3]]
    print(f"\n{len(ROWS) - len(bugs)} ok, {len(bugs)} BUG")
    for r in bugs:
        print("BUG |", " | ".join(r[:3]))
    with open(TMP / "dms.txt", "w") as f:  # every message to a person, for reading through
        for k, (_, tg_id) in U.items():
            f.write(f"\n##### {k} ({tg_id})\n")
            for x in FAKE.calls(chat=int(tg_id)):
                f.write(f"#{x['seq']} {x['method']}: {text_of(x)[:300]!r}\n")
    print("dms:", TMP / "dms.txt")
    (TMP / "report.json").write_text(json.dumps(ROWS, ensure_ascii=False, indent=1))
    print("report:", TMP / "report.json")
    if "--keep" in sys.argv:
        print(f"API http://127.0.0.1:{API_PORT}/api, fake Telegram http://127.0.0.1:{TG_PORT}; Ctrl-C to stop")
        threading.Event().wait()
    sys.exit(1 if bugs else 0)


STEPS = [step1, step2, step3, step4, step5, step5b, step6, step7, step8]
PHOTOS, VIDEO = [], None

if __name__ == "__main__":
    main()
