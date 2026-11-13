"""summary.json — a small, plain file Claude (or anyone) can read to plan a trip.

Ask Claude: "Here is summary.json — where should we go on Saturday?"
Public level only: ~2 km hexagons, named by the nearest village. No exact spots.
"""
import json
import math
from datetime import date

import numpy as np

from .. import config
from ..score import clock
from ..score import species as SP

TREE_NAMES = ["Calabrian pine (likely)", "Troodos black pine (likely)", "Golden oak (likely)",
              "Other broadleaf", "Tripylos cedar zone (closed)"]
TOP_N = 5
MIN_GAP_KM = 8          # spread the top zones out over the island


def _km(lat1, lon1, lat2, lon2):
    p = math.pi / 180
    a = (math.sin((lat2 - lat1) * p / 2) ** 2
         + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lon2 - lon1) * p / 2) ** 2)
    return 12742 * math.asin(math.sqrt(a))


def _compass(lat1, lon1, lat2, lon2):
    """Direction FROM the village TO the zone."""
    b = math.degrees(math.atan2((lon2 - lon1) * math.cos(math.radians(lat1)), lat2 - lat1)) % 360
    return ["N", "NE", "E", "SE", "S", "SW", "W", "NW"][int((b + 22.5) // 45) % 8]


def near(lat, lon, places):
    best = min(places, key=lambda p: _km(lat, lon, p[1], p[0]))
    d = _km(lat, lon, best[1], best[0])
    if d < 1:
        return best[2]
    return f"{d:.0f} km {_compass(best[1], best[0], lat, lon)} of {best[2]}"


def load_places():
    return json.loads((config.DATA / "static" / "places.json").read_text())["places"]


def pick(zones, key, n=TOP_N):
    """Best zones by `key`, spread at least MIN_GAP_KM apart."""
    picked = []
    for z in sorted(zones, key=lambda z: -key(z)):
        if all(_km(z["lat"], z["lon"], p["lat"], p["lon"]) >= MIN_GAP_KM for p in picked):
            picked.append(z)
        if len(picked) == n:
            break
    return picked


def reasons(inp: dict, fac: dict) -> str:
    """Plain-language 'why', strongest factors first."""
    parts = [
        (fac["rain_total"], f"{inp['rain_30d_mm']:.0f} mm rain in 30 days"),
        (fac["rain_pulse"], f"{inp['pulse_mm']:.0f} mm soaking rain 7-20 days ago"),
        (fac["temperature"], f"{inp['t7_mean_c']:.0f} °C average this week"),
        (fac["soil_moisture"], f"soil wetter than {inp['soil_percentile']:.0f}% of last season"),
        (fac["shade"], "shady slopes and valleys"),
    ]
    good = [t for v, t in sorted(parts, key=lambda x: -x[0]) if v >= 0.6]
    weak = [t for v, t in sorted(parts, key=lambda x: x[0]) if v < 0.4]
    s = ("Good: " + "; ".join(good) + ".") if good else ""
    if weak:
        s += (" " if s else "") + "Weak: " + "; ".join(weak[:2]) + "."
    if inp["frost_days"] >= 1:
        s += f" Frost on {inp['frost_days']:.0f} day(s)."
    return s


CONF = ["high", "medium", "low"]                  # v0.3: from rain dependence (engine/daily.py)

STATE_TEXT = {
    0: "Soil too warm or too cold: the mushroom clock is paused.",
    1: "Waiting for a soaking rain to start the mushroom clock.",
    2: "Soaking rain fell. The mushroom clock is running.",
    3: "Window open.",
    4: "A window just ended. It needs rest and a new soaking rain.",
    5: "Resting after a window. It needs a new soaking rain later.",
}


def engine_clock(inp: dict) -> str:
    """Plain words for the v0.3 cycle state (inputs: state, left_days)."""
    st, left = int(round(inp["state"])), int(round(inp["left_days"]))
    if st == 3 and left > 0:
        return f"Window open, about {left} more day{'s' if left != 1 else ''}."
    if st == 2 and left > 0:
        return f"Soaking rain fell. Window opens in about {left} day{'s' if left != 1 else ''}."
    return STATE_TEXT.get(st, "")


def engine_reasons(inp: dict, fac: dict) -> str:
    """v0.3 'why': the parts that multiply into the score, strongest first."""
    parts = [
        (fac["habitat"], "partner trees and tree cover"),
        (fac["water"], f"ground {inp['fill_pct']:.0f}% wet"),
        (fac["temperature"], f"soil about {inp['soil_temp_c']:.0f} °C"),
        (fac["cycle"], "mushroom clock"),
        (fac["prior"], "season"),
    ]
    good = [t for v, t in sorted(parts, key=lambda x: -x[0]) if v >= 0.6]
    weak = [t for v, t in sorted(parts, key=lambda x: x[0]) if v < 0.4]
    s = ("Good: " + "; ".join(good) + ".") if good else ""
    if weak:
        s += (" " if s else "") + "Holding it back: " + "; ".join(weak[:2]) + "."
    return s


def build(zones: list, days: list, meta: dict, specs: list, engine: bool = False) -> dict:
    c = meta["clock"]
    general = [z for z in zones if z["score"] is not None]
    out_days = []
    for d in days:
        k = d["offset"]
        month = date.fromisoformat(d["date"]).month
        gen_k = [z for z in general if np.isfinite(z["score"][k])]      # zones with a species in season that day
        picked = pick(gen_k, lambda z: z["score"][k])
        scores = np.array([z["score"][k] for z in gen_k])
        top = []
        for rank, z in enumerate(picked, 1):
            inp = {n: float(v[k]) for n, v in z["inputs"].items()}
            fac = {n: float(v[k]) for n, v in z["factors"].items()}
            trees = {TREE_NAMES[i]: round(float(f), 2) for i, f in enumerate(z["trees"]) if f >= 0.1}
            top.append({
                "rank": rank,
                "where": z["where"],
                "spot": z.get("spot"),             # index into spots.json (the site opens this zone)
                "lat": round(z["lat"], 4), "lon": round(z["lon"], 4),
                "score": int(round(z["score"][k])),
                **({"confidence": CONF[int(z["conf"][k])]} if z.get("conf") is not None else {}),
                "why": engine_reasons(inp, fac) if engine else reasons(inp, fac),
                "mushroom_clock": engine_clock(inp) if engine else clock.sentence(int(z["clock"][k]), c["opens"], c["closes"]),
                "trees": trees,
                "altitude_m": [int(z["alt"][0]), int(z["alt"][1])],
                "inputs": {n: round(v, 1) for n, v in inp.items()},
                "factors_0_to_1": {n: round(v, 2) for n, v in fac.items()},
            })
        sp_out = {}
        for s in specs:
            label = f"good conditions for {s['latin']} ({s['common']}) habitat"
            if not SP.in_season(month, s):
                sp_out[s["code"]] = {"label": label, "in_season": False,
                                     "season": SP.months_text(s["months"]), "top_zones": []}
                continue
            have = [z for z in zones if s["code"] in z["species"]]
            sp_out[s["code"]] = {"label": label, "in_season": True, "season": s.get("season_text") or SP.months_text(s["months"]),
                                 "top_zones": [{"where": z["where"], "spot": z.get("spot"), "lat": round(z["lat"], 4),
                                                "lon": round(z["lon"], 4),
                                                "score": int(round(z["species"][s["code"]][k])),
                                                **({"confidence": CONF[int(z["species_conf"][s["code"]][k])]}
                                                   if z.get("species_conf") else {})}
                                               for z in pick(have, lambda z: z["species"][s["code"]][k], 3)]}
        out_days.append({
            "date": d["date"], "weekday": date.fromisoformat(d["date"]).strftime("%A"),
            "confidence": d["confidence"],
            "island": {"median_score": int(np.median(scores)) if len(scores) else 0,
                       "zones_70_plus": int((scores >= 70).sum()), "zones_total": len(general)},
            "top_zones": top,
            "species": sp_out,
        })
    how = (
        "Scores 0-100 = how good GROWING CONDITIONS are in ~2 km forest zones. v0.3: for each species, "
        "habitat x water x temperature x mushroom clock x a season factor, multiplied, so one poor "
        "part makes the score poor. The general score is the best species here that is in season that day. "
        if engine else
        "Scores 0-100 = how good GROWING CONDITIONS are (rain, temperature, soil moisture, "
        "season for the altitude, shade) in ~2 km forest zones. ")
    sp_note = ("Species scores say 'good conditions for [species] habitat', never that the species is there. "
               "In the edge months of its season a species scores lower; further out it scores zero."
               if engine else
               "Species scores change only the habitat filter (trees, altitude) and the season "
               "window. They say 'good conditions for [species] habitat', never that the "
               "species is there. Out of season = no score.")
    return {
        "title": "Cyprus Mushroom Finder — growing conditions summary",
        "safety": meta["safety"],
        "how_to_read": (
            how + "It never says a mushroom is "
            "there, and never says anything about eating one. Nature reserves are closed and "
            "never listed. "
            + ("Each zone's confidence says how much its score needs rain that has not fallen yet: "
               "high = it holds on rain that already fell, medium = partly forecast rain, low = mostly forecast rain. "
               if engine else "Confidence: high = days 0-2, medium = 3-4, low = 5+ (forecast). ")
            + "Picking rules: no rakes or tools; pick by hand or knife; put the leaf litter back."),
        "emergency": "Poisoning: call 112. Cyprus Poison Centre: 1401. Do not wait for symptoms.",
        "weather_run": meta["weather_run"], "generated_utc": meta["generated_utc"],
        "site": "https://realexis.github.io/cyprus-mushroom-finder/",
        "days": out_days,
        "species_note": sp_note,
    }
