"""NDA for new agents, signed electronically (docs/NDA.md; the HiG Sign idea, PlatformDGE/hig-sign, moved into the CRM).

Staff: «Новое NDA» — the agent's full name, personal ID / passport, phone, Telegram, role and the language (KA, KA-RU,
KA-EN). The text is rendered and frozen (doc_sha256); the company's signature (David draws it once: company_signature)
goes in at once. The CRM gives a personal link /nda/<token> to send the agent.

The agent: opens the link (no CRM login), reads the agreement, confirms himself with Telegram (Login Widget — Telegram
asks him to confirm in the app; the server checks the answer's HMAC with the bot token; if the NDA names a @username
only that account passes), draws the signature, ticks the consent, signs. The server prints the signed PDF (both
signatures in the «Signatures» table + a last page with the signing record: Telegram id / @username, the confirmation's
signed hash = the «confirmation code» of clause 5, time in Tbilisi, IP, device, SHA-256 of the text) and sends it to the
staff member who made the NDA and to the agent (Telegram), and to Google Drive when configured."""
import base64
import hashlib
import hmac
import html as H
import json
import logging
import re
import secrets
import struct
import threading
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app import storage
from app.config import settings as env
from app.models import ADMINS, FIELD_SQL, STAFF, SUPER, AgentNda, User
from app.services import contracts as C, jobs
from app.services.common import TZ, log_event, now
from app.services.errors import DomainError, forbidden
from app.services.nda_text import (APPENDIX, BLOCKS, COMPANY, EDITION, LEVELS, REQUISITES, ROLES, SHORT, SIGNATURES,
                                   SUBTITLE, TITLE)

log = logging.getLogger(__name__)
LANGS = ("KA", "KA-RU", "KA-EN")
SECOND = {"KA": None, "KA-RU": "ru", "KA-EN": "en"}
COMPANY_SIG_KEY = "private/nda/company-signature.json"
CONFIRM_TTL = timedelta(hours=1)  # the Telegram confirmation is good for this long before signing
PNG_PREFIX = "data:image/png;base64,"
MAX_SIGNATURE = 400_000
STATUS_LABEL = {"sent": "Отправлено", "signed": "Подписано", "cancelled": "Отменено"}


# ---------------------------------------------------------------- the text

def _md(s: str) -> str:
    """Escaped text with «**bold**»."""
    return "".join(f"<b>{p}</b>" if i % 2 else p for i, p in enumerate(H.escape(s).split("**")))


def _fill(s: str, f: dict) -> str:
    """{field} → «**value**»; an unknown {…} (typed in an edited clause) stays as typed."""
    v = lambda k: f"**{f[k]}**" if f[k] and f[k] != "—" else "—"  # noqa: E731
    return re.sub(r"\{(\w+)\}", lambda m: v(m.group(1)) if m.group(1) in f else m.group(0), s)


CSS = """@page{size:A4;margin:16mm 15mm 18mm;@bottom-center{content:"Homes in Georgia · № {num} · {lang} · {edition} · " counter(page);
font:7.5pt 'Noto Sans Georgian','DejaVu Sans',Arial,sans-serif;color:#888}}
body{margin:0;font-family:'Noto Sans Georgian','DejaVu Sans',Arial,sans-serif;font-size:9.3pt;line-height:1.35;color:#111}
h1{font-size:13pt;text-align:center;color:#1D3560;margin:0 0 2px}h1+h1{margin-top:0}.sub{text-align:center;color:#666;margin:2px 0 12px}
h2{font-size:12pt;color:#1D3560;margin:0 0 6px}h3{font-size:10.5pt;color:#2F5394;margin:9px 0 3px}p{margin:0 0 5px;text-align:justify}
.cols{width:100%;border-collapse:collapse;table-layout:fixed}.cols>tbody>tr>td{vertical-align:top;padding:0 7px;width:50%}
.cols>tbody>tr>td:first-child{padding-left:0}.cols>tbody>tr>td:last-child{padding-right:0}.cols>tbody>tr>td[colspan]{padding:0}
.li{display:flex;gap:6px;margin:0 0 3px 8px}.li span:first-child{min-width:14px}
.cl{display:flex;gap:6px;margin:0 0 5px}.cl>span:first-child{min-width:26px;color:#2F5394;font-weight:700}
.cl>span:last-child{flex:1}.page{break-before:page}
.grid{width:100%;border-collapse:collapse;margin:4px 0 8px;font-size:8pt;line-height:1.25}
.grid th{background:#1D3560;color:#fff;padding:4px 5px;font-weight:700;text-align:left;vertical-align:top}
.grid td{border:1px solid #c8cfdb;padding:4px 5px;vertical-align:top;height:12px;overflow-wrap:break-word}.grid i{display:block;font-style:normal;opacity:.75;font-size:7.3pt}
.grid th i{font-weight:400}.wrap{overflow-x:auto}
.sig{width:100%;border-collapse:collapse;margin-top:6px;font-size:9pt;table-layout:fixed}.sig th{background:#1D3560;color:#fff;padding:5px;font-weight:700}
.sig td{border:1px solid #c8cfdb;padding:5px;vertical-align:middle;height:16px;overflow-wrap:anywhere}.sig td:first-child{color:#444;width:28%}
.sig img{height:13mm;max-width:100%}.slot{color:#777}
.rec{break-before:page;font-size:9pt}.rec h2{font-size:12pt;text-align:center;color:#1D3560;margin:0 0 10px}
.rec table{width:100%;border-collapse:collapse;margin:6px 0 12px}.rec td{border:1px solid #888;padding:4px 6px;vertical-align:top}
.rec td:first-child{width:36%;color:#333}.rec .mono{font-family:monospace;font-size:8pt;word-break:break-all}.rec img{height:18mm}
@media screen and (max-width:700px){.cols>tbody>tr>td{display:block;width:auto;padding:0 0 8px}}"""


def _sig_table(lang: str, f: dict) -> str:
    """The parties' details and signatures (one table per language column): the Operator | the Participant."""
    t = lambda k: H.escape((REQUISITES.get(k) or SIGNATURES[k])[lang])  # noqa: E731
    e = lambda v: H.escape(v) if v else "—"  # noqa: E731
    slot = lambda name, text: f'<span class="slot" data-slot="{name}">{H.escape(text)}</span>'  # noqa: E731
    contacts = " · ".join(v for v in (f["phone"], f["email"], f["telegram"]) if v and v != "—") or "—"
    name = f["name_ka"] if lang == "ka" else f["name2"]
    rows = [("name", COMPANY["name"][lang], name), ("ie", COMPANY["ie"], f["ie"]), ("pid", COMPANY["pid"], f["pid"]),
            ("address", COMPANY["address"][lang], f["address"]), ("iban_gel", COMPANY["iban_gel"], f["iban_gel"]),
            ("iban_usd", COMPANY["iban_usd"], f["iban_usd"]), ("contacts", COMPANY["contacts"], contacts)]
    return (f'<h3>{t("title")}</h3><table class="sig"><tr><th></th><th>{t("company")}</th><th>{t("recipient")}</th></tr>'
            + "".join(f'<tr><td>{t(k)}</td><td>{e(a)}</td><td>{e(b)}</td></tr>' for k, a, b in rows)
            + f'<tr><td>{t("signature")}</td><td>{slot("company-sig", SIGNATURES["pending"][lang])}</td>'
            f'<td>{slot("recipient-sig", SIGNATURES["pending"][lang])}</td></tr>'
            f'<tr><td>{t("time")}</td><td>{slot("company-time", SIGNATURES["auto"][lang])}</td>'
            f'<td>{slot("recipient-time", SIGNATURES["auto"][lang])}</td></tr></table>')


def render(lang: str, f: dict, blocks: list | None = None) -> str:
    """The agreement's HTML (A4 print CSS) for the participant's fields f (nda_text: {num} {date} {name_ka} {name2} …;
    role_ka / role2 come from f["role"], a ROLES key)."""
    second = SECOND[lang]
    langs = ["ka"] + ([second] if second else [])
    f = {k: (str(v).strip() if v else "—") for k, v in f.items()}
    role = ROLES.get(f.pop("role", ""), None)
    per = {ln: {**f, "role_ka": role["ka"] if role else "—", "role2": role[ln if ln != "ka" else "ru"] if role else "—"}
           for ln in ("ka", "ru", "en")}
    fill = lambda texts, ln: _md(_fill(texts[ln], per[ln]))  # noqa: E731

    def cell(b: dict, ln: str) -> str:
        k = b["k"]
        if k == "h":
            return f'<h3>{H.escape(b["n"])}. {fill(b, ln)}</h3>'
        if k == "sub":
            return f"<h3>{fill(b, ln)}</h3>"
        if k == "app":
            return f'<h2>{H.escape(APPENDIX[ln])} {H.escape(b["n"])}. {fill(b, ln)}</h2>'
        if k in ("n", "li"):
            return f'<div class="cl"><span>{H.escape(b["n"])}</span><span>{fill(b, ln)}</span></div>' if b[ln] else \
                f'<div class="cl"><span>{H.escape(b["n"])}</span><span></span></div>'
        return f"<p>{fill(b, ln)}</p>"

    def grid(b: dict) -> str:
        two = lambda c, tag: (f"{fill(c, 'ka')}" + (f"<i>{fill(c, second)}</i>" if second and c[second] != c["ka"] and c[second] else ""))  # noqa: E731
        rows = b["rows"] or [[{"ka": "", "ru": "", "en": ""} for _ in b["head"]] for _ in range(2)]
        return ('<div class="wrap"><table class="grid"><tr>' + "".join(f"<th>{two(c, 'th')}</th>" for c in b["head"]) + "</tr>"
                + "".join("<tr>" + "".join(f"<td>{two(c, 'td')}</td>" for c in row) + "</tr>" for row in rows)
                + "</table></div>")

    # sections: the agreement, the parties' details + signatures, each appendix on a new page
    sections: list[list[str]] = [[]]
    sig_done = False
    for b in blocks or BLOCKS:
        if b.get("only") and lang not in b["only"].split():
            continue
        if b["k"] == "app":
            if not sig_done:
                sections.append([("sig", None)])
                sig_done = True
            sections.append([])
        sections[-1].append(("t", grid(b)) if b["k"] == "t" else ("row", [cell(b, ln) for ln in langs]))
    if not sig_done:
        sections.append([("sig", None)])

    def section(items, i) -> str:
        cls = ' class="page"' if i and not any(kind == "sig" for kind, _ in items) else ""
        if any(kind == "sig" for kind, _ in items):
            cells = [_sig_table(ln, per[ln]) for ln in langs]
            items = [("row", cells)]
        if second:
            trs = "".join(f'<tr><td colspan="2">{x}</td></tr>' if kind == "t" else f"<tr><td>{x[0]}</td><td>{x[1]}</td></tr>"
                          for kind, x in items)
            return f'<div{cls}><table class="cols"><tbody>{trs}</tbody></table></div>'
        return f"<div{cls}>" + "".join(x if kind == "t" else x[0] for kind, x in items) + "</div>"

    head = f'<h1>{H.escape(TITLE["ka"])}</h1>' + (f'<h1>{H.escape(TITLE[second])}</h1>' if second else "") + \
        f'<div class="sub">{H.escape(SUBTITLE)} · № {H.escape(f["num"])} · {H.escape(f["date"])}</div>'
    body = "".join(section(items, i) for i, items in enumerate(sections) if items)
    css = CSS.replace("{lang}", lang).replace("{num}", f["num"].replace('"', "")).replace("{edition}", EDITION)
    return (f'<!doctype html><html lang="ka"><head><meta charset="utf-8"><title>{H.escape(SHORT["ka"])} · '
            f'{H.escape(f["name2"])}</title><style>{css}</style></head><body>{head}{body}</body></html>')


def doc_hash(page: str) -> str:
    return hashlib.sha256(page.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- the company's signature (David, once)

def company_signature() -> dict | None:
    raw = storage.read(COMPANY_SIG_KEY)
    try:
        return json.loads(raw) if raw else None
    except ValueError:
        return None


def set_company_signature(signature: str, user: User) -> dict:
    if user.role not in SUPER:
        raise forbidden("only a superadmin sets the company signature")
    _png(signature)
    d = {"signature": signature, "name": COMPANY["name"]["ru"], "by": user.id, "by_name": user.name,
         "at": now().isoformat()}
    storage.put(COMPANY_SIG_KEY, json.dumps(d).encode())
    return d


# ---------------------------------------------------------------- staff: create / list / cancel

def _staff(user: User) -> None:
    if user.role not in STAFF:
        raise forbidden("only staff send NDAs")


def path(token: str) -> str:
    return f"/nda/{token}"


def out(db: Session, n: AgentNda, full: bool = False) -> dict:
    by = db.get(User, n.created_by) if n.created_by else None
    d = {"id": n.id, "status": n.status, "status_label": STATUS_LABEL[n.status], "lang": n.lang, "full_name": n.full_name,
         "personal_id": n.personal_id, "phone": n.phone, "telegram": n.telegram, "role": n.role,
         "path": path(n.token) if n.status == "sent" else None, "created_at": n.created_at.isoformat() if n.created_at else None,
         "created_by": {"id": by.id, "name": by.name} if by else None,
         "signed_at": n.signed_at.isoformat() if n.signed_at else None,
         "tg_username": n.tg_username, "has_pdf": bool(n.pdf_path), "in_drive": bool(n.drive_file_id),
         "number": number(n), "details": n.details or {}, "user_id": n.user_id}
    if full:
        d["html"] = n.html
    return d


def _clean(v, n=200) -> str:
    return re.sub(r"\s+", " ", str(v or "").replace("*", "")).strip()[:n]  # «*» would toggle bold in the text


DETAILS = ("full_name_ka", "ie", "address", "email", "level", "access", "iban_gel", "iban_usd")  # → agent_ndas.details


def _date(v) -> str:
    """«2026-11-14» (a date input) or «14.11.2026» → «14.11.2026»; anything else as typed."""
    v = _clean(v, 20)
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", v)
    return f"{m.group(3)}.{m.group(2)}.{m.group(1)}" if m else v


def number(n: AgentNda) -> str:
    """The agreement's number: «2026-0007» (year made + id)."""
    return f"{(n.created_at or now()).astimezone(TZ):%Y}-{n.id:04d}"


def _page(n: AgentNda, blocks="own") -> str:
    """The NDA's text from its fields and its own edited clauses (details.blocks; or the blocks given, None = the
    standard text) — the date is the day it was made."""
    d = n.details or {}
    day = (n.created_at or now()).astimezone(TZ).strftime("%d.%m.%Y")
    return render(n.lang, {"num": number(n), "date": day, "name_ka": d.get("full_name_ka") or n.full_name,
                           "name2": n.full_name, "ie": d.get("ie"), "pid": n.personal_id, "address": d.get("address"),
                           "phone": n.phone, "email": d.get("email"), "telegram": f"@{n.telegram}" if n.telegram else "",
                           "role": d.get("role", ""), "level": d.get("level"), "access": d.get("access"),
                           "iban_gel": d.get("iban_gel"), "iban_usd": d.get("iban_usd")},
                  d.get("blocks") if blocks == "own" else blocks)


def create(db: Session, body: dict, user: User) -> AgentNda:
    _staff(user)
    lang = body.get("lang") or "KA-RU"
    if lang not in LANGS:
        raise DomainError("bad_input", "Язык: KA, KA-RU или KA-EN")
    member = db.get(User, int(body["user_id"])) if body.get("user_id") else None
    if body.get("user_id") and not member:
        raise DomainError("not_found", "Пользователь не найден")
    f = {k: _clean(body.get(k)) for k in ("full_name", "personal_id", "phone", "telegram")}
    f["telegram"] = f["telegram"].lstrip("@").split("/")[-1] or ""  # «@name» or «t.me/name» → «name»
    if not f["full_name"] or not f["personal_id"]:
        raise DomainError("missing_fields", "Укажите ФИО и личный номер агента")
    role = "agent"  # every agreement is «Агент» (Stanislav 11-16): no role in the form, level 50 / 70 / 90
    d = {k: _clean(body.get(k)) for k in DETAILS}
    if len(f["full_name"].split()) < 2:
        raise DomainError("bad_name", "ФИО агента: имя и фамилия, как в паспорте")
    if d["full_name_ka"] and not re.search(r"[\u10a0-\u10ff]", d["full_name_ka"]):
        raise DomainError("bad_name_ka", "ФИО по-грузински — грузинскими буквами (или оставьте пустым)")
    d["level"] = d["level"] if d["level"] in LEVELS and d["level"] != "25" else "50"
    d["access"] = _date(d["access"]) or now().astimezone(TZ).strftime("%d.%m.%Y")
    d["role"] = role
    if member:  # a team member: one open agreement at a time — «Отправить снова» or «Пересоздать» (replace)
        old = list(db.scalars(select(AgentNda).where(or_(*_conds(member)), AgentNda.status == "sent").with_for_update()))
        if old and not body.get("replace"):
            raise DomainError("nda_exists", "У участника уже есть неподписанное соглашение: отправьте его снова или пересоздайте", 409)
        for o in old:
            o.status, o.cancelled_at = "cancelled", now()
            log_event(db, "nda", o.id, "cancelled", user, label=o.full_name, reason="recreated")
    if not d["ie"] and (u := member or _user_by_username(db, f["telegram"])):
        d["ie"] = u.ie_number or ""  # the profile's ИП number (users.ie_number)
    comp = company_signature()
    if not comp:
        raise DomainError("no_company_signature", "Сначала Давид должен один раз расписаться за компанию (NDA → «Подпись компании»)", 409)
    n = AgentNda(lang=lang, token=secrets.token_urlsafe(24), html="", doc_sha256="", details=d, role=ROLES[role]["ru"],
                 company_signature=comp["signature"], company_signed_at=now(), created_by=user.id,
                 user_id=member.id if member else None,
                 **{k: (v or None) for k, v in f.items()})
    db.add(n)
    db.flush()  # the id → the agreement's number
    page = _page(n)
    n.html, n.doc_sha256 = page, doc_hash(page)
    log_event(db, "nda", n.id, "created", user, label=f["full_name"], lang=lang)
    db.commit()
    return n


def get(db: Session, nid: int, user: User) -> AgentNda:
    _staff(user)
    n = db.get(AgentNda, int(nid))
    if not n:
        raise DomainError("not_found", "NDA не найдено")
    return n


def query(user: User, status: str | None = None):
    _staff(user)
    q = select(AgentNda)
    if status and status != "all":
        q = q.where(AgentNda.status == status)
    return q.order_by(AgentNda.id.desc())


def cancel(db: Session, nid: int, user: User) -> AgentNda:
    n = get(db, nid, user)
    if n.status != "sent":
        raise DomainError("bad_status", f"NDA: {STATUS_LABEL[n.status]}", 409)
    n.status, n.cancelled_at = "cancelled", now()
    log_event(db, "nda", n.id, "cancelled", user)
    db.commit()
    return n


# ---------------------------------------------------------------- staff: this NDA's own text (like a client contract's
# text edited in the wizard's preview): clauses changed / added / removed per agent while it is not signed

KINDS = ("p", "h", "n", "li", "app", "sub", "t")
TEXT_LANGS = ("ka", "ru", "en")
MAX_BLOCKS, MAX_TEXT = 600, 6000


def text(db: Session, nid: int, user: User) -> dict:
    n = get(db, nid, user)
    own = (n.details or {}).get("blocks")
    return {"blocks": own or BLOCKS, "edited": bool(own), "edition": EDITION, "lang": n.lang, "status": n.status}


def _cell(c) -> dict:
    c = c if isinstance(c, dict) else {}
    return {ln: str(c.get(ln) or "")[:MAX_TEXT] for ln in TEXT_LANGS}


def _blocks(raw) -> list[dict]:
    """The edited clause list, checked: known kinds, the three texts as strings (escaped when printed), «todo» = the
    languages not translated yet after an edit in another one (shown to staff, not printed)."""
    if not isinstance(raw, list) or not raw or len(raw) > MAX_BLOCKS:
        raise DomainError("bad_input", "Текст соглашения: пустой или слишком длинный")
    out = []
    for b in raw:
        if not isinstance(b, dict) or b.get("k") not in KINDS:
            raise DomainError("bad_input", "Текст соглашения: неизвестный блок")
        x = {"k": b["k"]}
        if b["k"] == "t":
            x["head"] = [_cell(c) for c in (b.get("head") or [])][:12]
            x["rows"] = [[_cell(c) for c in (r or [])][:12] for r in (b.get("rows") or []) if isinstance(r, list)][:60]
        else:
            x.update(n=str(b.get("n") or "")[:20], **_cell(b))
        if b.get("only") in ("KA", "KA-RU", "KA-EN", "KA-RU KA-EN"):
            x["only"] = b["only"]
        todo = [ln for ln in TEXT_LANGS if ln in (b.get("todo") or [])]
        if todo:
            x["todo"] = todo
        out.append(x)
    return out


def set_text(db: Session, nid: int, body: dict, user: User, save: bool = True) -> dict:
    """blocks → this NDA's text (re-rendered, new doc_sha256: an open signing page gets «текст изменился, обновите»);
    blocks null → back to the standard text. Admins only, never a signed NDA. save=False: the preview's HTML only."""
    if user.role not in ADMINS:
        raise forbidden("only an admin changes an agreement's text")
    n = db.get(AgentNda, int(nid), with_for_update=save) if str(nid).isdigit() else None
    if not n:
        raise DomainError("not_found", "NDA не найдено")
    if n.status != "sent":
        raise DomainError("bad_status", f"NDA: {STATUS_LABEL[n.status]} — текст не меняется", 409)
    blocks = None if body.get("blocks") is None else _blocks(body["blocks"])
    if blocks == BLOCKS:
        blocks = None
    page = _page(n, blocks)
    if not save:
        return {"html": page}
    n.details = {**{k: v for k, v in (n.details or {}).items() if k != "blocks"}, **({"blocks": blocks} if blocks else {})}
    if page != n.html:
        n.html, n.doc_sha256 = page, doc_hash(page)
        log_event(db, "nda", n.id, "text_edited", user, label=n.full_name, edited=bool(blocks),
                  doc_sha256=n.doc_sha256)
    db.commit()
    return out(db, n, full=True)


def pdf_bytes(n: AgentNda, amended: bool = False) -> bytes:
    key = ((n.details or {}).get("ie_amended") or {}).get("pdf") if amended else n.pdf_path
    data = storage.read(key) if key else None
    if not data:
        raise DomainError("not_found", "PDF ещё не готов")
    return data


def filename(n: AgentNda) -> str:
    day = (n.signed_at or n.created_at or now()).astimezone(TZ).date().isoformat()
    return re.sub(r"[\\/:*?\"<>|\s]+", " ", f"NDA {n.full_name} {day}").strip()[:150] + ".pdf"


# ---------------------------------------------------------------- the agent (public, by token)

def _by_token(db: Session, token: str, lock: bool = False) -> AgentNda:
    q = select(AgentNda).where(AgentNda.token == token)
    n = db.scalar(q.with_for_update() if lock else q) if token and len(token) >= 20 else None
    if not n or n.status == "cancelled":
        raise DomainError("not_found", "Ссылка недействительна. Попросите прислать новую")
    return n


def _test_mode() -> bool:
    """A test stand (settings.TEST_MODE, when it has one): Telegram is off there, the page offers a marked stand-in."""
    return bool(getattr(env, "TEST_MODE", False))


def _confirmed(n: AgentNda) -> bool:
    return bool(n.tg_id and n.tg_auth_date and now() - n.tg_auth_date < CONFIRM_TTL)


def view(db: Session, token: str) -> dict:
    n = _by_token(db, token)
    return {"lang": n.lang, "status": n.status, "full_name": n.full_name, "personal_id": n.personal_id, "phone": n.phone,
            "telegram": n.telegram, "role": n.role, "doc_sha256": n.doc_sha256,
            "confirmed": _confirmed(n) or n.status == "signed", "tg_username": n.tg_username, "tg_name": n.tg_name,
            "signed_at": n.signed_at.isoformat() if n.signed_at else None, "has_pdf": bool(n.pdf_path),
            "test_mode": _test_mode(), "html": n.html if n.status == "sent" else None,
            "details": {k: (n.details or {}).get(k) or "" for k in ("iban_gel", "iban_usd", "ie")}}


IBAN_RE = re.compile(r"[A-Z]{2}\d{2}[A-Z0-9]{10,30}")  # GE: GE + 2 digits + 2-letter bank + 16 digits


def set_details(db: Session, token: str, data: dict) -> dict:
    """The agent's own details on the signing page: IBAN GEL / USD (at least one) and the ИП number (optional, he can add
    it in the profile later) → the agreement re-rendered (new hash)."""
    n = _by_token(db, token, lock=True)
    if n.status != "sent":
        raise DomainError("already_signed", "NDA уже подписано", 409)
    new = {k: re.sub(r"[\s-]", "", str(data.get(k) or "")).upper()[:40] for k in ("iban_gel", "iban_usd", "ie")}
    for k in ("iban_gel", "iban_usd"):
        if new[k] and not IBAN_RE.fullmatch(new[k]):
            raise DomainError("bad_iban", "IBAN: GE29TB0000000000000000")
    if not (new["iban_gel"] or new["iban_usd"]):
        raise DomainError("iban_required", "IBAN GEL / USD")
    if new["ie"] and not re.fullmatch(r"\d{9}|\d{11}", new["ie"]):
        raise DomainError("bad_ie", "ი/მ / ИП: 9 / 11")
    d = dict(n.details or {})
    if any(d.get(k, "") != v for k, v in new.items()):
        n.details = {**d, **new}
        page = _page(n)
        n.html, n.doc_sha256 = page, doc_hash(page)
        log_event(db, "nda", n.id, "details", None, label=n.full_name, doc_sha256=n.doc_sha256, **new)
        db.commit()
    return view(db, token)


def confirm_telegram(db: Session, token: str, data: dict) -> dict:
    """The Login Widget's answer → checked with the bot token; only the NDA's @username (when given) passes."""
    n = _by_token(db, token, lock=True)
    if n.status != "sent":
        raise DomainError("bad_status", "NDA уже подписано", 409)
    if _test_mode() and data.get("test") is True:  # the test server has no Telegram: a marked stand-in
        fields = {"id": "0", "username": n.telegram or "test", "first_name": "TEST", "auth_date": str(int(now().timestamp())),
                  "hash": "test-mode-" + secrets.token_hex(8)}
    else:
        from app.api.auth import verify_login_widget
        payload = {k: (str(v) if v is not None else None) for k, v in data.items() if k in
                   ("id", "first_name", "last_name", "username", "photo_url", "auth_date", "hash")}
        fields = verify_login_widget(payload, env.LOGIN_BOT_TOKEN or env.BOT_TOKEN, max_age=int(CONFIRM_TTL.total_seconds()))
        fields["hash"] = payload["hash"]
    got = (fields.get("username") or "").lower()
    if n.telegram and got != n.telegram.lower():
        raise DomainError("wrong_telegram", f"Это NDA для Telegram @{n.telegram}. Войдите в Telegram этим аккаунтом", 403)
    n.tg_id, n.tg_username = str(fields.get("id")), fields.get("username") or None
    n.tg_name = " ".join(x for x in (fields.get("first_name"), fields.get("last_name")) if x) or None
    n.tg_auth_date = datetime.fromtimestamp(int(fields.get("auth_date") or 0), timezone.utc)
    n.tg_hash = fields.get("hash")
    log_event(db, "nda", n.id, "telegram_confirmed", None, label=n.full_name, tg_id=n.tg_id, tg_username=n.tg_username)
    db.commit()
    return view(db, token)


def confirm_by_bot(db: Session, token: str, frm: dict) -> AgentNda:
    """/start nda_<token> in the CRM sign-in bot (the page's «Подтвердить в Telegram-боте»: a plain t.me link, which works
    on phones where the Login Widget's popup doesn't): the private message's sender is the Telegram account; only the
    NDA's @username (when given) passes. The confirmation code: an HMAC (bot token) of the token, the account and time."""
    n = _by_token(db, token, lock=True)
    if n.status != "sent":
        raise DomainError("bad_status", "Соглашение уже подписано", 409)
    got = (frm.get("username") or "").lower()
    if n.telegram and got != n.telegram.lower():
        raise DomainError("wrong_telegram", f"Это соглашение для Telegram @{n.telegram}. Откройте ссылку из этого аккаунта", 403)
    at = now()
    n.tg_id, n.tg_username = str(frm["id"]), frm.get("username") or None
    n.tg_name = " ".join(x for x in (frm.get("first_name"), frm.get("last_name")) if x) or None
    n.tg_auth_date = at
    key = hashlib.sha256((env.LOGIN_BOT_TOKEN or env.BOT_TOKEN or "").encode()).digest()
    n.tg_hash = "bot-" + hmac.new(key, f"{n.token}:{n.tg_id}:{int(at.timestamp())}".encode(), hashlib.sha256).hexdigest()
    log_event(db, "nda", n.id, "telegram_confirmed", None, label=n.full_name, tg_id=n.tg_id, tg_username=n.tg_username, via="bot")
    db.commit()
    return n


def _png(sig) -> bytes:
    if not isinstance(sig, str) or not sig.startswith(PNG_PREFIX) or len(sig) > MAX_SIGNATURE:
        raise DomainError("bad_signature", "Подпись не получена, распишитесь ещё раз")
    try:
        raw = base64.b64decode(sig[len(PNG_PREFIX):], validate=True)
    except ValueError:
        raise DomainError("bad_signature", "Подпись не получена, распишитесь ещё раз")
    if not raw.startswith(b"\x89PNG\r\n\x1a\n") or raw[12:16] != b"IHDR" or min(struct.unpack(">II", raw[16:24])) < 12:
        raise DomainError("bad_signature", "Подпись не получена, распишитесь ещё раз")
    return raw


def sign(db: Session, token: str, data: dict, ip: str | None, user_agent: str | None) -> dict:
    n = _by_token(db, token, lock=True)
    if n.status != "sent":
        raise DomainError("already_signed", "NDA уже подписано", 409)
    if (data.get("doc_sha256") or "") != n.doc_sha256:
        raise DomainError("doc_changed", "Текст изменился: обновите страницу", 409)
    if not _confirmed(n):
        raise DomainError("telegram_required", "Подтвердите себя через Telegram", 403)
    if data.get("consent") is not True:
        raise DomainError("consent_required", "Нужно согласие с условиями")
    if not ((n.details or {}).get("iban_gel") or (n.details or {}).get("iban_usd")):
        raise DomainError("iban_required", "IBAN GEL / USD")
    _png(data.get("signature"))
    n.signature, n.signed_at = data["signature"], now()
    n.ip, n.user_agent = (ip or "")[:100] or None, (user_agent or "")[:300] or None
    n.status = "signed"
    ie, u = (n.details or {}).get("ie"), _user_of(db, n)
    if ie and u and not u.ie_number and re.fullmatch(r"\d{9}|\d{11}", ie):
        u.ie_number = ie  # the agreement's ИП → the profile
        log_event(db, "user", u.id, "updated", None, ie_number=ie, source=f"nda {n.id}")
    for k in ("iban_gel", "iban_usd"):  # the agreement's IBANs → an empty profile
        if u and not getattr(u, k) and (v := (n.details or {}).get(k)) and IBAN_RE.fullmatch(v):
            setattr(u, k, v)
            log_event(db, "user", u.id, "updated", None, **{k: v}, source=f"nda {n.id}")
    if u and not u.personal_id and n.personal_id:
        u.personal_id = n.personal_id  # the agreement's personal number → the profile
        log_event(db, "user", u.id, "updated", None, personal_id=n.personal_id, source=f"nda {n.id}")
    log_event(db, "nda", n.id, "signed", None, label=n.full_name, tg_id=n.tg_id, tg_username=n.tg_username, ip=n.ip,
              user_agent=n.user_agent, doc_sha256=n.doc_sha256)
    db.commit()
    try:
        finalize(db, n.id)
    except Exception:  # noqa: BLE001 — the signature is saved; the worker prints the PDF again
        db.rollback()
        log.exception("nda %s: signed PDF failed, retrying in the worker", n.id)
        jobs.schedule(db, "nda_pdf", n.id, now())
        db.commit()
    return view(db, token)


# ---------------------------------------------------------------- the signed PDF

def _tbilisi(dt) -> str:
    return dt.astimezone(TZ).strftime("%d.%m.%Y %H:%M:%S") + " (Tbilisi)"


def _record(n: AgentNda, by: User | None) -> str:
    second = SECOND[n.lang] or "en"
    L = {"title": ("ელექტრონული ხელმოწერის ოქმი", {"ru": "Протокол электронного подписания", "en": "Electronic signature record"}),
         "doc": ("დოკუმენტი", {"ru": "Документ", "en": "Document"}), "hash": ("ტექსტის SHA-256", {"ru": "SHA-256 текста", "en": "Text SHA-256"}),
         "rec": ("მონაწილე", {"ru": "Участник", "en": "Participant"}), "comp": ("ოპერატორი", {"ru": "Оператор", "en": "Operator"}),
         "name": ("სახელი, გვარი", {"ru": "ФИО", "en": "Full name"}), "pid": ("პირადი ნომერი", {"ru": "Личный номер", "en": "Personal number"}),
         "phone": ("ტელეფონი", {"ru": "Телефон", "en": "Phone"}), "tg": ("Telegram (დადასტურებული)", {"ru": "Telegram (подтверждён)", "en": "Telegram (confirmed)"}),
         "code": ("დადასტურების კოდი", {"ru": "Код подтверждения", "en": "Confirmation code"}),
         "conf": ("დადასტურების დრო", {"ru": "Время подтверждения", "en": "Confirmed at"}),
         "at": ("ხელმოწერის დრო", {"ru": "Время подписи", "en": "Signed at"}), "ip": ("IP მისამართი", {"ru": "IP-адрес", "en": "IP address"}),
         "ua": ("მოწყობილობა", {"ru": "Устройство", "en": "Device"}), "sig": ("ხელმოწერა", {"ru": "Подпись", "en": "Signature"}),
         "sent": ("გაგზავნა", {"ru": "Отправил", "en": "Sent by"})}
    t = lambda k: H.escape(f"{L[k][0]} / {L[k][1][second]}")  # noqa: E731
    e = lambda v: H.escape(str(v)) if v else "—"  # noqa: E731
    row = lambda k, v, cls="": f'<tr><td>{t(k)}</td><td{cls}>{v}</td></tr>'  # noqa: E731
    tg = f'@{e(n.tg_username)} · id {e(n.tg_id)}' + (f' · {e(n.tg_name)}' if n.tg_name else "")
    return (f'<section class="rec"><h2>{t("title")}</h2><table>{row("doc", f"{e(SHORT[second])} № {number(n)} · {e(n.lang)} · {EDITION}")}'
            f'{row("hash", n.doc_sha256, " class=mono")}</table>'
            f'<table><tr><td colspan="2"><b>{t("rec")}</b></td></tr>{row("name", e(n.full_name))}{row("pid", e(n.personal_id))}'
            f'{row("phone", e(n.phone))}{row("tg", tg)}{row("code", e(n.tg_hash), " class=mono")}'
            f'{row("conf", _tbilisi(n.tg_auth_date) if n.tg_auth_date else "—")}{row("at", _tbilisi(n.signed_at))}'
            f'{row("ip", e(n.ip))}{row("ua", e(n.user_agent), " class=mono")}'
            f'{row("sig", f"<img src={chr(34)}{n.signature}{chr(34)} alt={chr(34)}{chr(34)}>")}</table>'
            f'<table><tr><td colspan="2"><b>{t("comp")}</b></td></tr>{row("name", e(COMPANY["name"][second]) + " · IE " + COMPANY["ie"])}'
            f'{row("at", _tbilisi(n.company_signed_at) if n.company_signed_at else "—")}{row("sent", e(by and by.name))}'
            f'{row("sig", f"<img src={chr(34)}{n.company_signature}{chr(34)} alt={chr(34)}{chr(34)}>")}</table></section>')


def signed_html(n: AgentNda, by: User | None = None) -> str:
    """The frozen text with both signatures and times in the «Signatures» tables, plus the signing record page."""
    img = lambda s: f'<img src="{s}" alt="">' if s else "—"  # noqa: E731
    fill = {"company-sig": img(n.company_signature), "recipient-sig": img(n.signature),
            "company-time": _tbilisi(n.company_signed_at) if n.company_signed_at else "—",
            "recipient-time": _tbilisi(n.signed_at) if n.signed_at else "—"}
    page = re.sub(r'<span class="slot" data-slot="([\w-]+)">[^<]*</span>', lambda m: fill.get(m.group(1), m.group(0)), n.html)
    return page.replace("</body>", _record(n, by) + "</body>", 1)


def finalize(db: Session, nid: int) -> str:
    """Signed: print the PDF, keep it, send it (staff + agent), queue Google Drive. Idempotent."""
    n = db.get(AgentNda, nid, with_for_update=True, populate_existing=True)
    if not n or n.status != "signed" or n.pdf_path:
        return "stale"
    by = db.get(User, n.created_by) if n.created_by else None
    pdf = C.render_pdf(signed_html(n, by))
    n.pdf_path = f"private/nda/{n.id}/{secrets.token_hex(8)}.pdf"
    storage.put(n.pdf_path, pdf)
    jobs.schedule(db, "nda_drive", n.id, now())
    log_event(db, "nda", n.id, "pdf", None, pdf_sha256=hashlib.sha256(pdf).hexdigest())
    db.commit()
    # in the background: the agent's page answers as soon as the PDF is kept (two Telegram uploads took seconds)
    _bg(_send, env.BOT_TOKEN, by and by.tg_id, f"✅ NDA подписано: {n.full_name} (@{n.tg_username or '—'})", filename(n), pdf)
    _bg(_send, env.LOGIN_BOT_TOKEN or env.BOT_TOKEN, n.tg_id if n.tg_id and n.tg_id != "0" else None,
          "Homes in Georgia: your signed NDA / ხელმოწერილი NDA", filename(n), pdf)
    return "ok"


def _bg(fn, *args) -> None:
    threading.Thread(target=fn, args=args, daemon=True).start()


def _send(token: str, chat_id, caption: str, name: str, pdf: bytes) -> None:
    """A PDF to a Telegram chat through the given bot; never fails the signing (the agent may not have allowed the
    login bot to write to him)."""
    if not token or not chat_id:
        return
    try:
        base = (env.TG_API_BASE or "https://api.telegram.org").rstrip("/")
        httpx.post(f"{base}/bot{token}/sendDocument", data={"chat_id": str(chat_id), "caption": caption},
                   files={"document": (name, pdf, "application/pdf")}, timeout=30)
    except Exception:  # noqa: BLE001
        log.warning("nda: telegram send to %s failed", chat_id)


def drive_upload(db: Session, nid: int) -> str:
    """Worker: the signed NDA → the contracts Drive folder (same settings as contracts)."""
    n = db.get(AgentNda, nid)
    if not n or n.status != "signed" or not n.pdf_path or n.drive_file_id:
        return "stale"
    sa = C.drive_configured()
    if not sa:
        return "skipped"
    n.drive_file_id = C.drive_put(sa, filename(n), pdf_bytes(n))
    log_event(db, "nda", n.id, "drive_uploaded", None, file_id=n.drive_file_id)
    return "ok"


def signed_pdf(db: Session, token: str) -> tuple[AgentNda, bytes]:
    n = _by_token(db, token)
    if n.status != "signed":
        raise DomainError("not_found", "NDA ещё не подписано")
    return n, pdf_bytes(n)


# ---------------------------------------------------------------- the ИП number added later in the profile (Stanislav 11-16)
# An NDA is the user's when it was confirmed with his Telegram account (tg_id) or names his @username.

def _user_by_username(db: Session, username: str | None) -> User | None:
    if not username:
        return None
    return db.scalar(select(User).where(func.lower(User.username) == username.lower(), User.deleted_at.is_(None))
                     .order_by(User.id).limit(1))


def _user_of(db: Session, n: AgentNda) -> User | None:
    if n.user_id and (u := db.get(User, n.user_id)):
        return u
    u = db.scalar(select(User).where(User.tg_id == int(n.tg_id))) if n.tg_id and n.tg_id.isdigit() and n.tg_id != "0" else None
    return u or _user_by_username(db, n.telegram)


def _addendum(n: AgentNda, ie: str, at) -> str:
    """The page appended to the signed agreement: the participant's ИП number, added from his profile."""
    second = SECOND[n.lang] or "en"
    day = at.astimezone(TZ).strftime("%d.%m.%Y")
    title = {"ka": "დამატება: მონაწილის რეკვიზიტები", "ru": "Дополнение: реквизиты участника", "en": "Addendum: the participant's details"}
    note = {"ka": f"ი/მ ნომერი შეტანილია {day} მონაწილის მიერ პროფილში მითითებული მონაცემების საფუძველზე. ხელმოწერილი ტექსტი არ შეცვლილა.",
            "ru": f"Номер ИП внесён {day} на основании данных участника в профиле. Подписанный текст не изменён.",
            "en": f"The IE number was added on {day} from the participant's details in his profile. The signed text is unchanged."}
    ie_l = {"ka": "ი/მ ნომერი", "ru": "Номер ИП", "en": "IE number"}
    e = H.escape
    return (f'<section class="rec"><h2>{e(title["ka"])} / {e(title[second])}</h2><table>'
            f'<tr><td>{e(SHORT["ka"])} / {e(SHORT[second])}</td><td>№ {number(n)} · {e(n.lang)} · {EDITION}</td></tr>'
            f'<tr><td>{e(ie_l["ka"])} / {e(ie_l[second])}</td><td><b>{e(ie)}</b></td></tr>'
            f'<tr><td>SHA-256</td><td class="mono">{n.doc_sha256}</td></tr></table>'
            f'<p>{e(note["ka"])}</p><p>{e(note[second])}</p></section>')


def apply_ie(db: Session, u: User, actor: User | None) -> None:
    """The user's ИП number set / changed in the profile → his NDAs: an unsigned one is re-rendered with it (new hash: an
    open signing page asks to reload); a signed one that went without it keeps its signed PDF and gets a second,
    amended PDF (the signed one + an «Addendum: the participant's details» page), sent to him like the signed one."""
    ie = u.ie_number
    if not ie:
        return
    for n in list(db.scalars(select(AgentNda).where(or_(*_conds(u)), AgentNda.status.in_(("sent", "signed"))).with_for_update())):
        d = dict(n.details or {})
        if n.status == "sent" and d.get("ie") != ie:
            n.details = {**d, "ie": ie}
            page = _page(n)
            n.html, n.doc_sha256 = page, doc_hash(page)
            log_event(db, "nda", n.id, "ie_added", actor, label=n.full_name, ie=ie, doc_sha256=n.doc_sha256)
        elif n.status == "signed" and n.pdf_path and not d.get("ie") and (d.get("ie_amended") or {}).get("ie") != ie:
            at = now()
            try:
                pdf = C.render_pdf(signed_html(n, db.get(User, n.created_by) if n.created_by else None)
                                   .replace("</body>", _addendum(n, ie, at) + "</body>", 1))
            except Exception:  # noqa: BLE001 — the profile is saved; saving the number again retries
                log.exception("nda %s: amended PDF failed", n.id)
                continue
            key = f"private/nda/{n.id}/{secrets.token_hex(8)}-ie.pdf"
            storage.put(key, pdf)
            n.details = {**d, "ie_amended": {"ie": ie, "at": at.isoformat(), "pdf": key}}
            log_event(db, "nda", n.id, "ie_amended", actor, label=n.full_name, ie=ie,
                      pdf_sha256=hashlib.sha256(pdf).hexdigest())
            db.commit()
            _send(env.LOGIN_BOT_TOKEN or env.BOT_TOKEN, n.tg_id if n.tg_id and n.tg_id != "0" else None,
                  "Homes in Georgia: NDA + IE number / NDA + ი/მ ნომერი", filename(n).replace(".pdf", " IE.pdf"), pdf)
    db.commit()


# ---------------------------------------------------------------- team members without a signed agreement (Stanislav
# 11-16): the list on the NDA page, the form prefilled from the profile, the link sent by the CRM bot

def _conds(u: User) -> list:
    """An NDA is the user's: made for him (user_id), confirmed with his Telegram account or naming his @username."""
    return [AgentNda.user_id == u.id] + ([AgentNda.tg_id == str(u.tg_id)] if u.tg_id else []) + \
        ([func.lower(AgentNda.telegram) == u.username.lower()] if u.username else [])


def _mine(n: AgentNda, u: User) -> bool:
    return n.user_id == u.id or bool(u.tg_id and n.tg_id == str(u.tg_id)) or \
        bool(u.username and n.telegram and n.telegram.lower() == u.username.lower())


def prefill(u: User, last: AgentNda | None = None) -> dict:
    """The NDA form from the profile; what the profile lacks stays empty for staff to fill. The agreement's role is always
    Агент (no role / level in the form, Stanislav 11-16); the level from the profile, else 50."""
    role = "agent"
    level = str(u.level) if str(u.level) in LEVELS and u.level != 25 else "50"
    return {"user_id": u.id, "lang": "KA-RU", "full_name": " ".join(x for x in (u.first_name, u.last_name) if x) or u.name,
            "full_name_ka": "", "personal_id": u.personal_id or "", "ie": u.ie_number or "", "address": "",
            "phone": u.phone or "", "email": u.email or "", "telegram": f"@{u.username}" if u.username else "",
            "role": role, "level": level, "access": now().astimezone(TZ).strftime("%Y-%m-%d"),
            "iban_gel": u.iban_gel or "", "iban_usd": u.iban_usd or "",
            **_from_nda(last)}


def _from_nda(n: AgentNda | None) -> dict:
    """What staff typed into the member's latest agreement (even a cancelled one) — so «Пересоздать» / «Сформировать»
    after a cancel doesn't lose the full name, personal number, address…"""
    if not n:
        return {}
    d = n.details or {}
    got = {"full_name": n.full_name, "personal_id": n.personal_id, "phone": n.phone,
           **{k: d.get(k) for k in ("full_name_ka", "ie", "address", "email", "iban_gel", "iban_usd")}}
    return {k: v for k, v in got.items() if v}


def team(db: Session, user: User) -> dict:
    """Active field users (agents, recruits, staff «+ как агент») without a signed agreement: the open one if sent, what
    the profile lacks (личный номер and the surname are required; ИП, phone, email only shown)."""
    _staff(user)
    users = list(db.scalars(select(User).where(FIELD_SQL, User.is_active.is_(True), User.deleted_at.is_(None)).order_by(User.name)))
    ndas = list(db.scalars(select(AgentNda).order_by(AgentNda.id.desc())))
    rows, signed = [], 0
    for u in users:
        mine = [n for n in ndas if _mine(n, u)]  # ponytail: users × NDAs in Python, fine for a team of dozens
        if any(n.status == "signed" for n in mine):
            signed += 1
            continue
        open_ = next((n for n in mine if n.status == "sent"), None)
        last = mine[0] if mine else None
        need = [k for k, v in (("personal_id", u.personal_id), ("last_name", u.last_name)) if not v]
        extra = [k for k, v in (("ie", u.ie_number), ("phone", u.phone), ("email", u.email)) if not v]
        rows.append({"user_id": u.id, "name": u.name, "role": u.role, "level": u.level, "username": u.username,
                     "can_send": bool(u.tg_id), "missing": need + extra, "ready": not need,
                     "status": "sent" if open_ else "none", "nda": out(db, open_) if open_ else None, "prefill": prefill(u, last)})
    return {"items": rows, "signed": signed, "total": len(users)}


def send_link(db: Session, nid: int, user: User) -> dict:
    """The signing link → the team member's Telegram through the CRM bot; {sent: false} → staff copy the link."""
    from app.telegram import client as tg
    n = get(db, nid, user)
    if n.status != "sent":
        raise DomainError("bad_status", f"NDA: {STATUS_LABEL[n.status]}", 409)
    url = env.PUBLIC_URL.rstrip("/") + path(n.token)
    u = _user_of(db, n)
    ok = False
    if u and u.tg_id:
        text = (f"📝 <b>Homes in Georgia</b>\nპლატფორმასთან მიერთების შეთანხმება — გთხოვთ, გაეცნოთ და მოაწეროთ ხელი.\n"
                f"Соглашение о подключении к платформе — пожалуйста, прочитайте и подпишите.\n{H.escape(n.full_name)}")
        ok = tg.send(u.tg_id, text, {"inline_keyboard": [[{"text": "✍️ ხელმოწერა / Подписать", "url": url}]]}) is not None
    log_event(db, "nda", n.id, "link_sent" if ok else "link_not_sent", user, label=n.full_name, to=u and u.id)
    db.commit()
    return {"sent": ok, "url": url, "path": path(n.token)}


def send_all(db: Session, user: User) -> dict:
    """«Сформировать и отправить всем»: every team member with no agreement yet and the required profile fields."""
    made, sent, manual = 0, 0, []
    for r in team(db, user)["items"]:
        if r["status"] != "none" or not r["ready"]:
            continue
        n = create(db, r["prefill"], user)
        made += 1
        if send_link(db, n.id, user)["sent"]:
            sent += 1
        else:
            manual.append(r["name"])
    return {"made": made, "sent": sent, "not_sent": manual}
