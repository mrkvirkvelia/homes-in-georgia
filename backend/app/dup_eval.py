"""Precision / recall / false pairs of the duplicate score (services/similar.py CONFIG) on labelled pairs (David 11-19 §6).

    python -m app.dup_eval            # the labelled pairs of services/dup_pairs.json (synthetic, the spec's cases)
    python -m app.dup_eval --db       # the operators' «Дубль» / «Не дубль» decisions (similar_decisions), scored as the
                                      # base is now; read only
    python -m app.dup_eval -v         # every pair: its label, score, level, why

«дубль» is judged on precision first (an auto «дубль» must never be another flat); «показан» (≥ maybe) on recall.
"""
import json
import sys
from pathlib import Path

from app.services import similar
from app.services.dedup import street_house

PAIRS = Path(__file__).resolve().parent / "services" / "dup_pairs.json"


def profile(f: dict) -> dict:
    """A similar.py profile from plain fields: address, district, lat / lng, floor, area, bedrooms, price_usd, phones,
    name, author, cads, type, metro, text, date, urls, flat (else read from the address)."""
    addr = f.get("address")
    return {
        "key": f.get("key", "x"), "kind": f.get("kind", "ad"), "urls": set(f.get("urls") or []),
        "phones": list(f.get("phones") or []), "names": similar._name_tokens(f.get("name")),
        "author": tuple(f["author"]) if f.get("author") else None, "cads": {similar._digits(c) for c in f.get("cads") or []},
        "hashes": [], "house": street_house(addr), "street": similar._bare_street(addr), "at": (f.get("lat"), f.get("lng")),
        "district": f.get("district"), "floor": f.get("floor"), "area": f.get("area"), "bedrooms": f.get("bedrooms"),
        "price_usd": f.get("price_usd"), "flat": f.get("flat") or similar._flat(addr), "handles": similar._handles(f.get("text")),
        "words": similar._words(f.get("text")), "type": f.get("type"), "metro": f.get("metro"),
        "date": similar._date(f.get("date")), "multi": set(f.get("multi") or []),
    }


def labelled() -> list[dict]:
    """[{id, label same|different, note, a, b, shared, photo}]: b inherits a's fields unless it says "fresh": true."""
    out = []
    for p in json.loads(PAIRS.read_text())["pairs"]:
        a = p["a"]
        b = p.get("b", {}) if p.get("fresh") else {**a, **p.get("b", {})}
        out.append({**p, "a": a, "b": {k: v for k, v in b.items() if v is not None}})
    return out


def run(rows: list[tuple[str, str, dict | None]], verbose: bool = False, out=print) -> dict:
    """rows: (id, label, score() result or None). -> the counts and the rates; prints a table."""
    n = {"same": 0, "different": 0}
    tp_same = fp_same = shown_same = fp_shown = 0
    for rid, label, r in rows:
        n[label] += 1
        level = r["level"] if r else None
        if level == "same":
            tp_same += label == "same"
            fp_same += label == "different"
        if level:
            shown_same += label == "same"
            fp_shown += label == "different"
        if verbose or (label == "different" and level == "same"):
            out(f"{rid:<28} {label:<9} {(r or {}).get('pct', '—')!s:>4}% {level or '-':<5} {(r or {}).get('why', 'нет данных')}")
    m = {"pairs": n["same"] + n["different"], "dup_pairs": n["same"], "other_pairs": n["different"],
         "auto_same": tp_same + fp_same, "auto_precision": round(tp_same / (tp_same + fp_same), 3) if tp_same + fp_same else None,
         "auto_recall": round(tp_same / n["same"], 3) if n["same"] else None, "auto_false": fp_same,
         "shown_recall": round(shown_same / n["same"], 3) if n["same"] else None, "shown_false": fp_shown,
         "shown_precision": round(shown_same / (shown_same + fp_shown), 3) if shown_same + fp_shown else None}
    out(f"thresholds: дубль ≥ {similar.CONFIG['same']}, вероятный ≥ {similar.CONFIG['maybe']}; weights {similar.CONFIG['weights']}")
    out(f"pairs {m['pairs']} (дубли {m['dup_pairs']}, разные {m['other_pairs']})")
    out(f"«дубль»: precision {m['auto_precision']}, recall {m['auto_recall']}, false {m['auto_false']}")
    out(f"показан (≥ вероятный): precision {m['shown_precision']}, recall {m['shown_recall']}, false {m['shown_false']}")
    return m


def synthetic(verbose: bool = False, out=print) -> dict:
    rows = []
    for p in labelled():
        r = similar.score(profile(p["a"]), profile(p["b"]), p.get("shared", 0), p.get("photo", 0.0))
        rows.append((p["id"], p["label"], r))
    return run(rows, verbose, out)


def from_db(db, verbose: bool = False, out=print) -> dict:
    from sqlalchemy import select
    from app.models import SimilarDecision
    rows = []
    for d in db.scalars(select(SimilarDecision).where(SimilarDecision.verdict.in_(("same", "different")))):
        rows.append((f"{d.a}~{d.b}", d.verdict, similar.score_pair(db, d.a, d.b)))
    return run(rows, verbose, out)


if __name__ == "__main__":
    v = "-v" in sys.argv
    if "--db" in sys.argv:
        from app.db import SessionLocal
        with SessionLocal() as db:
            from_db(db, v)
    else:
        synthetic(v)
