"""Species cards data: config/species.yaml + config/lookalikes.yaml + iNaturalist photos.

Photos: only CC0, CC BY, CC BY-SA and CC BY-NC [BRIEF]. Every photo keeps its
attribution line and a link to its iNaturalist page. Photos are shown from
iNaturalist's open-data bucket (not copied into this repo).

Output: web/src/generated/species.json (committed: public facts + photo credits).
API answers are cached in data/raw/inat/, so this runs offline after the first time.

Run:  uv run python -m shroomy.export.species [--refresh]
"""
import json
import sys
import time

import requests

from .. import config
from ..score import species as SP

API = "https://api.inaturalist.org/v1"
GBIF = "https://api.gbif.org/v1"
INAT_CYPRUS = "10289,96773"                       # iNaturalist places: Cyprus + Northern Cyprus
CACHE = config.RAW / "inat"
OUT = config.ROOT / "web" / "src" / "generated" / "species.json"
ALLOWED = {"cc0": "CC0", "cc-by": "CC BY", "cc-by-sa": "CC BY-SA", "cc-by-nc": "CC BY-NC"}   # [BRIEF]
HEADERS = {"User-Agent": "cyprus-mushroom-finder/0.1 (non-commercial, static site)"}


def _get(path, params, cache_name, refresh):
    f = CACHE / f"{cache_name}.json"
    if f.exists() and not refresh:
        return json.loads(f.read_text())
    time.sleep(1.1)                                   # stay well under iNaturalist's ~60/min
    r = requests.get(f"{API}/{path}", params=params, headers=HEADERS, timeout=30)
    r.raise_for_status()
    CACHE.mkdir(parents=True, exist_ok=True)
    f.write_text(r.text)
    return r.json()


def _gbif(path, params, cache_name, refresh):
    f = config.RAW / "gbif" / f"{cache_name}.json"
    if f.exists() and not refresh:
        return json.loads(f.read_text())
    time.sleep(0.3)
    r = requests.get(f"{GBIF}/{path}", params=params, headers=HEADERS, timeout=30)
    r.raise_for_status()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(r.text)
    return r.json()


def cyprus_records(names, refresh=False):
    """Public records in Cyprus: GBIF occurrences (with months) + iNaturalist research-grade.

    Facts only (counts and months of real records). Few records = Cyprus fungi are
    under-recorded; we never turn this into a season or a place.
    """
    out = {"gbif_total": 0, "inat_research": 0, "months": {}, "links": []}
    for nm in names:
        slug = nm.lower().replace(" ", "_")
        m = _gbif("species/match", {"name": nm, "kingdom": "Fungi"}, f"match_{slug}", refresh)
        key = m.get("usageKey") if m.get("matchType") == "EXACT" else None
        if key:
            o = _gbif("occurrence/search", {"country": "CY", "taxonKey": key, "limit": 0, "facet": "month",
                                            "facetLimit": 12}, f"cy_{key}", refresh)
            out["gbif_total"] += o["count"]
            for c in (o.get("facets") or [{}])[0].get("counts", []):
                out["months"][int(c["name"])] = out["months"].get(int(c["name"]), 0) + c["count"]
            out["links"] += [
                {"label": f"GBIF: {nm}", "url": f"https://www.gbif.org/species/{key}"},
                {"label": f"GBIF records in Cyprus: {nm}",
                 "url": f"https://www.gbif.org/occurrence/search?country=CY&taxon_key={key}"}]
        t = taxon(nm, refresh)
        if t:
            o = _get("observations", {"place_id": INAT_CYPRUS, "taxon_id": t["id"], "quality_grade": "research",
                                      "per_page": 0}, f"cy_obs_{t['id']}", refresh)
            out["inat_research"] += o["total_results"]
            out["links"] += [
                {"label": f"iNaturalist: {nm}", "url": f"https://www.inaturalist.org/taxa/{t['id']}"},
                {"label": f"iNaturalist sightings in Cyprus: {nm}",
                 "url": f"https://www.inaturalist.org/observations?place_id={INAT_CYPRUS}&taxon_id={t['id']}"}]
    out["months"] = dict(sorted(out["months"].items()))
    return out


def allowed_photos(taxon: dict, n: int) -> list:
    """Up to n photos with an allowed licence, each with its attribution."""
    out = []
    for tp in taxon.get("taxon_photos", []):
        ph = tp["photo"]
        lic = (ph.get("license_code") or "").lower()
        if lic not in ALLOWED or not ph.get("medium_url"):
            continue
        out.append({"url": ph["medium_url"], "licence": ALLOWED[lic],
                    "attribution": ph["attribution"],
                    "page": f"https://www.inaturalist.org/photos/{ph['id']}"})
        if len(out) == n:
            break
    return out


def taxon(name: str, refresh=False):
    slug = name.lower().replace(" ", "_")
    found = _get("taxa", {"q": name, "per_page": 10}, f"search_{slug}", refresh)
    match = [t for t in found["results"] if t["name"] == name]
    if not match:
        print(f" ! no exact iNaturalist taxon for {name}")
        return None
    tid = match[0]["id"]
    return _get(f"taxa/{tid}", {}, f"taxon_{tid}", refresh)["results"][0]


def photos_for(names, n, refresh):
    out, pages = [], []
    per = -(-n // len(names))                         # share the photos between the names
    for nm in names:
        t = taxon(nm, refresh)
        if t:
            pages.append({"name": nm, "url": f"https://www.inaturalist.org/taxa/{t['id']}"})
            out += [p | {"taxon": nm} for p in allowed_photos(t, per)]
    return out[:n], pages


def build(refresh=False):
    specs = config.load("species")["species"]
    looks = config.load("lookalikes")["lookalikes"]
    out_s = []
    for s in specs:
        ph, pages = photos_for(s["inat"], 3, refresh)
        out_s.append({k: s[k] for k in ("code", "latin", "common", "local", "local_confirmed", "trees",
                                         "trees_text", "bands", "altitude_text", "months", "notes")}
                     | {"tier": s.get("tier", "key"), "rare": bool(s.get("rare", False)), "warn": s.get("warn", ""),
                        "season_text": SP.months_text(s["months"]), "photos": ph, "inat_pages": pages,
                        "records": cyprus_records(s["inat"], refresh)})
        print(f" - {s['latin']}: {len(ph)} photos")
    out_l = []
    for lk in looks:
        ph, pages = photos_for([lk["inat"]], 2, refresh)
        out_l.append({k: lk[k] for k in ("latin", "common", "severity", "note")} | {"photos": ph, "inat_pages": pages})
        print(f" - lookalike {lk['latin']}: {len(ph)} photos")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "_about": "Built by pipeline/shroomy/export/species.py from config/species.yaml + config/lookalikes.yaml. "
                  "Photos: iNaturalist, licence and attribution per photo.",
        "species": out_s, "lookalikes": out_l}, indent=1, ensure_ascii=False))
    print(f"-> {OUT}")


if __name__ == "__main__":
    build(refresh="--refresh" in sys.argv)
