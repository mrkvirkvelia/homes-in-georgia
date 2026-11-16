import json
import logging
import time
import uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager

import jwt

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.api import api_router
from app import logs
from app.config import REPO_ROOT, settings
from app.db import SessionLocal
from app.models import User
from app.services import users
from app.services.errors import DomainError

logs.setup("api")
log = logging.getLogger("app")
req_log = logging.getLogger("app.request")
DIST = REPO_ROOT / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        with SessionLocal() as db:
            for u in users.ensure_bootstrap(db):
                log.warning("bootstrap superadmin ensured: id=%s login=%s tg_id=%s", u.id, u.login, u.tg_id)
    except Exception:  # noqa: BLE001  (DB not migrated yet: the API still starts, /health shows it)
        log.exception("bootstrap failed")
    yield


if settings.APP_ENV != "dev" and (len(settings.SECRET_KEY) < 32 or "change-me" in settings.SECRET_KEY):
    raise RuntimeError("SECRET_KEY is missing or weak: set a random string of 32+ chars in .env")

app = FastAPI(title="Homes in Georgia API", version="1.0", lifespan=lifespan)
# nothing in front compresses: JSON lists and the JS bundle shrink ~5x, which matters on slow mobile links
app.add_middleware(GZipMiddleware, minimum_size=1000)
if settings.DEV_CORS:
    app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                       allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


def _client_ip(request: Request) -> str:
    h = request.headers
    return (h.get("cf-connecting-ip") or (h.get("x-forwarded-for") or "").split(",")[0].strip()
            or (request.client.host if request.client else ""))


def _token_payload(request: Request) -> dict:
    """The token's claims for the log line only (not trusted: an expired token still tells whose session it was)."""
    auth = request.headers.get("authorization") or ""
    raw = auth[7:].strip() if auth.lower().startswith("bearer ") else request.query_params.get("token")
    if not raw:
        return {}
    try:
        return jwt.decode(raw, options={"verify_signature": False})
    except jwt.PyJWTError:
        return {"bad_token": True}


def _who(request: Request) -> dict:
    u = getattr(request.state, "user", None)
    if u is not None:
        return {"user_id": u.id, "user": u.name, "role": u.role}
    p = _token_payload(request)
    sub = str(p.get("sub") or "")
    return {"user_id": int(sub) if sub.isdigit() else sub, "role": p.get("role")} if sub else ({"bad_token": True} if p else {})


SKIP_LOG = ("/health", "/api/health", "/api/client-log")


# One JSON line per API request (docs/DEPLOY.md «Логи»): who, what, status, ms; errors with code / masked body /
# traceback. X-Request-Id goes back to the browser, which shows it in error toasts, so a screenshot finds the line.
@app.middleware("http")
async def request_log(request: Request, call_next):
    rid = uuid.uuid4().hex[:10]
    request.state.rid = rid
    t0 = time.perf_counter()
    path = request.url.path
    body = None
    ctype = request.headers.get("content-type", "")
    if (request.method in ("POST", "PUT", "PATCH") and "json" in ctype
            and int(request.headers.get("content-length") or 0) <= 64_000):
        body = await request.body()  # starlette caches it: the endpoint still reads it
    exc = None
    try:
        response = await call_next(request)
    except Exception as e:  # noqa: BLE001 — logged with its traceback, the user gets a 500 with the id
        exc = e
        response = JSONResponse({"detail": "Внутренняя ошибка сервера", "code": "internal", "request_id": rid},
                                status_code=500)
    response.headers["X-Request-Id"] = rid
    status = response.status_code
    if path in SKIP_LOG or (not path.startswith("/api/") and status < 500):
        return response
    f = {"rid": rid, **_who(request), "method": request.method, "path": path, "status": status,
         "ms": round((time.perf_counter() - t0) * 1000), "ip": _client_ip(request),
         "ua": (request.headers.get("user-agent") or "")[:120]}
    q = {k: v for k, v in request.query_params.items() if not logs.SECRET_KEYS.search(k)}
    if q:
        f["query"] = logs.mask(q)
    err = getattr(request.state, "err", None)
    if err:
        f["error"] = err
    if status >= 400 and body:
        try:
            f["body"] = json.dumps(logs.mask(json.loads(body)), ensure_ascii=False)[:2000]
        except ValueError:
            f["body"] = f"<{len(body)} bytes, not JSON>"
    level = logging.ERROR if status >= 500 else logging.WARNING if status >= 400 else logging.INFO
    req_log.log(level, "%s %s %s", request.method, path, status, extra={"fields": f},
                exc_info=(type(exc), exc, exc.__traceback__) if exc else None)
    return response


# ponytail: in-memory per-IP limit, one api process; a shared store if the api ever runs several workers
_client_hits: dict[str, deque] = defaultdict(deque)


@app.post("/api/client-log", include_in_schema=False)
async def client_log(request: Request):
    """Frontend errors (window.onerror, unhandled rejections, the React error boundary, failed API calls): one log line.
    Auth optional, 30/min per IP, 16 KB."""
    ip = _client_ip(request)
    hits, now = _client_hits[ip], time.time()
    while hits and hits[0] < now - 60:
        hits.popleft()
    if len(hits) >= 30:
        return JSONResponse({"ok": False, "code": "rate_limited"}, status_code=429)
    hits.append(now)
    raw = await request.body()
    if len(raw) > 16_000:
        return JSONResponse({"ok": False, "code": "too_large"}, status_code=413)
    try:
        d = json.loads(raw)
        assert isinstance(d, dict)
    except (ValueError, AssertionError):
        return JSONResponse({"ok": False, "code": "bad_json"}, status_code=400)
    who = _who(request)
    if who.get("user_id"):
        try:
            with SessionLocal() as db:
                u = db.get(User, int(who["user_id"]))
                if u:
                    who["user"] = u.name
        except Exception:  # noqa: BLE001 — the log line matters more than the name
            pass
    f = {"rid": request.state.rid, **who, "ip": ip, "ua": (request.headers.get("user-agent") or "")[:200]}
    for k in ("kind", "message", "url", "version", "stack", "component", "api_path", "api_status", "api_rid"):
        if d.get(k) is not None:
            f[k] = logs.mask_phone(str(d[k])[:4000 if k == "stack" else 500])
    logging.getLogger("app.client").error("client %s: %s", f.get("kind", "error"), f.get("message", "")[:200],
                                          extra={"fields": f})
    return {"ok": True}


@app.exception_handler(DomainError)
async def domain_error(request: Request, e: DomainError):
    request.state.err = {"code": e.code, "message": str(e.message)[:300]}
    return JSONResponse({"detail": e.message, "code": e.code}, status_code=e.status)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, e: RequestValidationError):
    request.state.err = {"code": "validation", "message": "; ".join(
        f"{'.'.join(map(str, x.get('loc', ())))}: {x.get('msg')}" for x in e.errors())[:500]}
    return JSONResponse({"detail": "validation error", "code": "validation", "errors": e.errors()}, status_code=422)


app.include_router(api_router, prefix="/api")


@app.get("/health")
@app.get("/api/health")
def health():
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        return {"ok": True, "db": True}
    except Exception:  # noqa: BLE001
        return JSONResponse({"ok": False, "db": False}, status_code=503)


@app.get("/map", include_in_schema=False)
def client_map():  # the bot's Mini App map (public, no data)
    return FileResponse(REPO_ROOT / "bot" / "webapp" / "index.html", media_type="text/html")


@app.get("/journey", include_in_schema=False)
def journey():
    return FileResponse(REPO_ROOT / "bot" / "docs" / "user-journey" / "index.html", media_type="text/html")


if (DIST / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")


@app.get("/{path:path}", include_in_schema=False)
def spa(path: str):
    if path == "api" or path.startswith("api/"):
        return JSONResponse({"detail": "not found", "code": "not_found"}, status_code=404)
    if DIST.is_dir():
        f = (DIST / path).resolve()
        if path and f.is_file() and f.is_relative_to(DIST.resolve()):
            return FileResponse(f)
        index = DIST / "index.html"
        if index.is_file():
            # revalidated on every load: after a deploy the browser picks the new hashed bundle, not a cached old app
            return FileResponse(index, media_type="text/html", headers={"Cache-Control": "no-cache"})
    return JSONResponse({"detail": "frontend is not built (frontend/dist)", "code": "not_found"}, status_code=404)
