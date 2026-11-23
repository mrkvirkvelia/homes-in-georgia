"""Копии объекта на myhome (David 11-22, Stanislav: «по адресу, метражу»): the parser keeps only owners' fresh ads, so
agents' copies of an exclusive (the owner's photos re-posted 30 times) never reached «Похожие». For one object a
narrow myhome search is made — its district, the rooms, the area ±12 %, agents included — then every rental on its
street with the same rooms and area; the ads found are kept as listings with status «copy» (never shown to clients,
not marked gone by the parser's sync) with their photos' dHash, so «Похожие» scores them like any other ad
(shared photos, the house, floor, area). Run for exclusives when they are taken / published, and by the card's button."""
import json
import logging
import re
import time

from sqlalchemy.orm import Session

from app import districts
from app.models import Listing, Property
from app.services.common import now
from app.services.dedup import _same_street, street_house, street_words

log = logging.getLogger(__name__)
SEARCH = "https://www.myhome.ge/en/real-estate/?deal_types=2&real_estate_types=1&cities=1&currency_id=2&{}"
PAGES = 5           # myhome renders at most 5 pages (120 ads) of one search
AREA_TOL = 0.12
PHOTOS = 6          # photos per ad to hash: enough to catch the copied ones, few downloads
STATUS = "copy"


def _page(query: str) -> list[dict] | None:
    from curl_cffi import requests
    html = requests.get(SEARCH.format(query), impersonate="chrome", timeout=30).text
    m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.S)
    if not m:
        return None
    qs = json.loads(m.group(1))["props"]["pageProps"]["dehydratedState"]["queries"]
    q = next((q for q in qs if q["queryKey"][:2] == ["statements", "list"]), None)
    return q["state"]["data"]["data"]["data"] if q else None


def search(query: str, pause: float = 1.0) -> list[dict]:
    out = []
    for n in range(1, PAGES + 1):
        items = _page(f"{query}&page={n}")
        if not items:
            break
        out += items
        if len(items) < 24:
            break
        time.sleep(pause)
    return out


def _street(addr) -> frozenset:
    """The street words of an address with or without a house number (myhome: «რამიშვილი ნ. ქ. » often has none)."""
    return street_house(addr)[0] or street_words(addr)


def _filters(p: Property) -> str:
    q = []
    rooms = p.rooms or (p.bedrooms + 1 if p.bedrooms is not None else None)  # myhome «2 room» = 1 bedroom + living
    if rooms:
        q.append(f"room_types={min(int(rooms), 6)}")
    if p.area:
        a = float(p.area)
        q.append(f"area_from={int(a * (1 - AREA_TOL))}&area_to={int(a * (1 + AREA_TOL)) + 1}")
    return "&".join(q)


def candidates(p: Property, pause: float = 1.0) -> list[dict]:
    """myhome ads that could be the object: the city narrowed by rooms and area tells myhome's ids of the object's
    district and street; then the district and the street, each with the rooms and area (≤ 120 ads a search)."""
    base = _filters(p)
    tag, street = districts.tag(p.district), _street(p.address)
    found = {i["id"]: i for i in search(base, pause)}

    def ours(i):
        return (tag and districts.tag(i.get("urban_name")) == tag) or \
            (street and _same_street(street, _street(i.get("address"))))
    urbans = {i["urban_id"] for i in found.values() if tag and i.get("urban_id") and districts.tag(i.get("urban_name")) == tag}
    for uid in list(urbans)[:2]:
        found.update({i["id"]: i for i in search(f"urbans={uid}&{base}", pause)})
    streets = {i["street_id"] for i in found.values() if street and i.get("street_id")
               and _same_street(street, _street(i.get("address")))}
    for sid in list(streets)[:3]:  # the object's street, whatever district myhome files it under
        found.update({i["id"]: i for i in search(f"streets={sid}&{base}", pause)})
    def floor_fits(i):  # agents copy the floor with the photos; ±1: «8» / «8-9» / a slip
        return p.floor is None or i.get("floor") is None or abs(int(i["floor"]) - int(p.floor)) <= 1
    return [i for i in found.values() if ours(i) and floor_fits(i)]


def _usd(i: dict) -> int | None:
    pr = (i.get("price") or {}).get("2") or {}
    return int(pr["price_total"]) if pr.get("price_total") else None


def _hashes(urls: list[str]) -> list[int]:
    import httpx

    from app.services.matching import photo_hash
    out = []
    with httpx.Client(timeout=20, follow_redirects=True) as c:
        for u in urls[:PHOTOS]:
            try:
                h = photo_hash(c.get(u).raise_for_status().content)
            except httpx.HTTPError:
                h = None
            out.append((h & ((1 << 64) - 1)) if h is not None else 0)
    return out


def _mh_row(i: dict) -> dict:
    return {"id": f"mh{i['id']}", "source": "myhome.ge",
            "url": f"https://www.myhome.ge/pr/{i['id']}/{i.get('dynamic_slug') or ''}",
            "photos": [x.get("large") for x in i.get("images") or [] if x.get("large")],
            "address": i.get("address"), "area": i.get("area"), "floor": i.get("floor"),
            "bedrooms": int(i["bedroom"]) if str(i.get("bedroom") or "").isdigit() else None,
            "district": districts.label(i.get("urban_name")) or i.get("urban_name"), "price_usd": _usd(i),
            "text": re.sub(r"<br\s*/?>", "\n", i.get("comment") or i.get("dynamic_title") or "")}


def save(db: Session, items: list[dict]) -> int:
    """Upsert the ads (myhome statements, or rows already shaped like _mh_row) as listings (an ad the parser already
    has keeps its status, a gone one becomes a «copy»)."""
    n, t = 0, now().isoformat(timespec="seconds")
    for i in items:
        r = i if "source" in i else _mh_row(i)
        l = db.get(Listing, r["id"])
        if l is None:
            l = Listing(id=r["id"], source=r["source"], status=STATUS, first_seen=t)
            db.add(l)
        elif l.status not in ("gone", STATUS):
            continue  # a live ad of the parser: «Похожие» sees it already
        l.status, l.urls = STATUS, json.dumps([r["url"]])
        l.address, l.area, l.floor, l.bedrooms = r["address"], r["area"], r["floor"], r["bedrooms"]
        l.district, l.price_usd, l.text = r["district"], r["price_usd"], r["text"]
        if l.photos != json.dumps(r["photos"]):
            l.photos, l.photo_hashes = json.dumps(r["photos"]), json.dumps(_hashes(r["photos"]))
        l.last_seen = l.updated_at = t
        n += 1
    db.commit()
    return n


# ------------------------------------------------------------------ ss.ge (David 11-22: «и SS тоже»)
# Cloudflare blocks the server: the search runs inside Apify (cheerio-scraper, a Georgian residential IP), as the
# parser's bot/fetch_ss.py. The gateway's own filters: areaFrom/areaTo, subdistrictIds, streetIds (agents included).
SS_PF = r"""async function pageFunction({ response, body, sendRequest, customData }) {
  let tok = (body.toString().match(/"credentialsToken":"([^"]+)"/) || [])[1];
  const c = [].concat(response.headers['set-cookie'] || []).find(x => x.startsWith('ss-session-token='));
  if (!tok && c) tok = decodeURIComponent(c.split(';')[0].split('=').slice(1).join('='));
  if (!tok) throw new Error('ss.ge: no token');
  const items = [];
  for (const q of customData.queries) {
    for (let page = 1; page <= customData.pages; page++) {
      const r = await sendRequest({ url: 'https://api-gateway.ss.ge/v1/RealEstate/LegendSearch', method: 'POST', responseType: 'text',
        headers: { Authorization: 'Bearer ' + tok, 'Content-Type': 'application/json', Origin: 'https://home.ss.ge', Referer: 'https://home.ss.ge/' },
        body: JSON.stringify(Object.assign({ realEstateType: 5, realEstateDealType: 1, cityIdList: [95], currencyId: 1, pageSize: 30, order: 1, page }, q)) });
      const got = JSON.parse(r.body).realStateItemModel || [];
      items.push(...got);
      if (got.length < 30) break;
    }
  }
  return { items };
}"""
SS_PROXY = {"useApifyProxy": True, "apifyProxyGroups": ["RESIDENTIAL"], "apifyProxyCountry": "GE"}


def _apify_tokens() -> list[str]:
    import os
    out = [t.strip() for t in os.environ.get("APIFY_TOKENS", "").replace(";", ",").split(",")] + [os.environ.get("APIFY_TOKEN", "").strip()]
    return list(dict.fromkeys(t for t in out if t))


def ss_search(queries: list[dict], pages: int = 3) -> list[dict]:
    """ss.ge LegendSearch for each query (extra filters), up to `pages` × 30 ads each, run in Apify -> the ads."""
    import httpx
    inp = {"startUrls": [{"url": "https://home.ss.ge/en"}], "pageFunction": SS_PF, "proxyConfiguration": SS_PROXY,
           "maxRequestRetries": 2, "customData": {"queries": queries, "pages": pages}}
    for tok in _apify_tokens():
        with httpx.Client(headers={"Authorization": f"Bearer {tok}"}, timeout=60) as c:
            r = c.post("https://api.apify.com/v2/acts/apify~cheerio-scraper/runs",
                       params={"memory": 1024, "forcePermissionLevel": "LIMITED_PERMISSIONS"}, json=inp)
            if r.status_code in (402, 403):
                continue  # out of usage / not allowed on this key: the next one
            run = r.raise_for_status().json()["data"]
            while run["status"] in ("READY", "RUNNING"):
                time.sleep(5)
                run = c.get(f"https://api.apify.com/v2/actor-runs/{run['id']}").raise_for_status().json()["data"]
            out = c.get(f"https://api.apify.com/v2/datasets/{run['defaultDatasetId']}/items", params={"clean": "true"}).json()
            return [i for x in out for i in x.get("items") or []]
    raise RuntimeError("no Apify key could run the ss.ge search")


def _ss_row(i: dict) -> dict:
    a = i.get("address") or {}
    return {"id": f"ss{i['applicationId']}", "source": "ss.ge", "url": f"https://home.ss.ge/ka/udzravi-qoneba/{i['detailUrl']}",
            "photos": [x["fileName"].replace("_Thumb", "") for x in i.get("appImages") or [] if x.get("fileName")],
            "address": " ".join(str(x) for x in (a.get("streetTitle"), a.get("streetNumber")) if x) or None,
            "area": i.get("totalArea"), "floor": int(i["floorNumber"]) if str(i.get("floorNumber") or "").isdigit() else None,
            "bedrooms": i.get("numberOfBedrooms"), "district": districts.label(a.get("subdistrictTitle")) or a.get("subdistrictTitle"),
            "price_usd": (i.get("price") or {}).get("priceUsd"), "text": f"{i.get('title') or ''}\n{i.get('description') or ''}".strip()}


def ss_candidates(p: Property) -> list[dict]:
    """ss.ge ads that could be the object: the city by the area finds ss.ge's ids of its district and street, then the
    district and the street with the area; kept: in the district or on the street, floor ±1, the same bedrooms."""
    if not p.area:
        return []
    a = float(p.area)
    area = {"areaFrom": int(a * (1 - AREA_TOL)), "areaTo": int(a * (1 + AREA_TOL)) + 1}
    tag, street = districts.tag(p.district), _street(p.address)

    def addr(i):
        return i.get("address") or {}

    def on_street(i):
        return bool(street) and _same_street(street, _street(addr(i).get("streetTitle")))

    def in_district(i):
        return bool(tag) and districts.tag(addr(i).get("subdistrictTitle")) == tag
    first = ss_search([area])
    subs = list({addr(i)["subdistrictId"] for i in first if in_district(i) and addr(i).get("subdistrictId")})[:2]
    streets = list({addr(i)["streetId"] for i in first if on_street(i) and addr(i).get("streetId")})[:3]
    more = ss_search([{**area, "subdistrictIds": subs}] * bool(subs) + [{**area, "streetIds": streets}] * bool(streets)) \
        if subs or streets else []
    found = {i["applicationId"]: i for i in first + more}

    def fits(i):
        fl = i.get("floorNumber")
        floor_ok = p.floor is None or not str(fl or "").isdigit() or abs(int(fl) - int(p.floor)) <= 1
        bed_ok = p.bedrooms is None or i.get("numberOfBedrooms") is None or int(i["numberOfBedrooms"]) == int(p.bedrooms)
        return floor_ok and bed_ok
    return [_ss_row(i) for i in found.values() if (in_district(i) or on_street(i)) and fits(i)]


SS_DETAIL_PF = r"""async function pageFunction({ $ }) {
  const d = JSON.parse($('#__NEXT_DATA__').text()).props.pageProps.applicationData;
  return { d };
}"""


def _ss_detail(url: str) -> dict:
    """One ss.ge ad page (Apify, as ss_search) -> a row like _ss_row."""
    import httpx
    inp = {"startUrls": [{"url": url}], "pageFunction": SS_DETAIL_PF, "proxyConfiguration": SS_PROXY, "maxRequestRetries": 2}
    for tok in _apify_tokens():
        with httpx.Client(headers={"Authorization": f"Bearer {tok}"}, timeout=90) as c:
            r = c.post("https://api.apify.com/v2/acts/apify~cheerio-scraper/run-sync-get-dataset-items",
                       params={"memory": 1024, "forcePermissionLevel": "LIMITED_PERMISSIONS", "timeout": 80}, json=inp)
            if r.status_code in (402, 403):
                continue
            d = r.raise_for_status().json()[0]["d"]
            desc = d.get("description")
            desc = " ".join(v for v in desc.values() if v) if isinstance(desc, dict) else desc
            return _ss_row({"applicationId": d["applicationId"], "detailUrl": url.rsplit("/", 1)[-1], "address": d.get("address"),
                            "totalArea": d.get("totalArea"), "floorNumber": str(d.get("floor") or ""), "numberOfBedrooms": d.get("bedrooms"),
                            "price": d.get("price"), "appImages": d.get("appImages"), "title": d.get("title"), "description": desc})
    raise RuntimeError("no Apify key could open the ss.ge ad")


def _mh_detail(mid: str) -> dict:
    from curl_cffi import requests
    html = requests.get(f"https://www.myhome.ge/en/pr/{mid}/", impersonate="chrome", timeout=30).text
    m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.S)
    qs = json.loads(m.group(1))["props"]["pageProps"]["dehydratedState"]["queries"] if m else []
    st = next((q["state"]["data"]["data"]["statement"] for q in qs if q["queryKey"][1:2] == ["details"]), None)
    if not st:
        raise ValueError("myhome: the ad page has no data (removed?)")
    return _mh_row(st)


# /ka/pr/26740808/… and the new slug form /ka/udzravi-qoneba/qiravdeba-…-vakeshi-26740808/ (David 11-23)
MH_LINK = re.compile(r"myhome\.ge/(?:[a-z]{2}/)?(?:pr/(\d+)|[^?#]*?-(\d{6,})/?(?:[?#]|$))")
SS_LINK = re.compile(r"ss\.ge/.*?(\d{6,})(?:[/?#]|$)")


def by_link(url: str) -> dict:
    """A myhome / ss.ge ad link -> its row (_mh_row / _ss_row shape); ValueError for another link."""
    url = url.strip()
    if m := MH_LINK.search(url):
        return _mh_detail(m[1] or m[2])
    if SS_LINK.search(url):
        return _ss_detail(url.split("?")[0])
    raise ValueError("Нужна ссылка на объявление myhome.ge или ss.ge")


def compare_link(db: Session, pid: int, url: str) -> dict:
    """«Сравнить по ссылке» (David 11-22): the ad of a competitor / an owner is saved as a copy and scored against the
    object as «Похожие» does (photos by their files now, by the rooms once the worker has their vectors)."""
    from app.services import similar
    from app.services.common import log_event
    row = by_link(url)
    save(db, [row])
    r = similar.score_pair(db, f"p:{pid}", f"l:{row['id']}") or {}
    log_event(db, "property", pid, "compare_link", None, label="сравнение по ссылке", url=row["url"], listing_id=row["id"],
              pct=r.get("pct"))
    db.commit()
    return {"listing_id": row["id"], "url": row["url"], "address": row["address"], "area": row["area"], "floor": row["floor"],
            "bedrooms": row["bedrooms"], "price_usd": row["price_usd"], "photos": row["photos"][:4],
            **{k: r.get(k) for k in ("pct", "level", "why", "matched", "differs")}}


def recent(db: Session, pid: int, hours: int = 24) -> bool:
    from datetime import timedelta

    from sqlalchemy import select

    from app.models import Event
    return db.scalar(select(Event.id).where(Event.entity == "property", Event.entity_id == str(pid),
                                            Event.action == "myhome_copies", Event.at > now() - timedelta(hours=hours))
                     .limit(1)) is not None


def run(db: Session, pid: int, pause: float = 1.0) -> int:
    """Job myhome_copies: search, save -> how many ads were saved (an event on the object says when)."""
    from app.services.common import log_event
    p = db.get(Property, pid)
    if p is None or not (p.area or p.bedrooms is not None or p.rooms):
        return 0
    items = candidates(p, pause)
    n = save(db, items)
    try:
        ss = ss_candidates(p)
        n_ss = save(db, ss)
    except Exception as e:  # noqa: BLE001 — ss.ge / Apify down: the myhome copies stand
        log.warning("ss.ge copies of #%s failed: %r", pid, e)
        ss, n_ss = [], 0
    log_event(db, "property", pid, "myhome_copies", None, label="поиск копий на myhome и ss.ge", candidates=len(items),
              saved=n, ss_candidates=len(ss), ss_saved=n_ss)
    db.commit()
    log.info("copies of #%s: myhome %s/%s, ss.ge %s/%s", pid, len(items), n, len(ss), n_ss)
    return n + n_ss
