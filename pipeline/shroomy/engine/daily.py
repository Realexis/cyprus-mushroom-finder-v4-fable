"""Run every species profile for the map: today + 7 days, on the given squares (v0.3 spec 3.1).

Returns plain arrays for the export (export/web.py). Scores are 0-100 (engine score x 100).
The general map = the best score among the profiled species (spec 3.2 step 6).
"""
import numpy as np

from .. import config
from . import inputs as I
from . import profile as P
from .cycle import OPEN, TRIGGERED
from .runner import prepare_water, rolling_sum, run_species

N_DAYS = 8
# The parts of the score shown in "Why this score" (x100) and the plain numbers behind them (x10).
PARTS = ["habitat", "water", "temperature", "cycle", "prior"]
INPUTS = ["fill_pct", "soil_temp_c", "rain_3d_mm", "state", "left_days"]


def season_text(prior: dict) -> str:
    """Months with full season prior, e.g. 'Oct-Jan' (in calendar order, wrapping the new year)."""
    full = [P.MONTHS.index(m) + 1 for m, v in prior.items() if v >= 1]
    if not full:
        return "all year"
    full.sort()
    gaps = [i for i in range(1, len(full)) if full[i] - full[i - 1] > 1]
    if gaps:                                   # wraps the new year, e.g. Oct-Jan
        full = full[gaps[0]:] + full[:gaps[0]]
    names = [m.capitalize() for m in P.MONTHS]
    return names[full[0] - 1] if len(full) == 1 else f"{names[full[0] - 1]}-{names[full[-1] - 1]}"


def _left_days(state, t0, window_days, days):
    """Days to the next change, per day k = 0..7, read from the run itself:
    Open -> days until the window closes; Triggered -> days until it opens. -1 = unknown / none."""
    n, nd = state.shape
    out = np.full((n, N_DAYS), -1, "int16")
    for k in range(N_DAYS):
        t = t0 + k
        s = state[:, t]
        for want, until in ((OPEN, lambda x: x != OPEN), (TRIGGERED, lambda x: x == OPEN)):
            m = s == want
            found = np.zeros(n, bool)
            for t2 in range(t + 1, nd):
                hit = m & ~found & until(state[:, t2])
                out[hit, k] = t2 - t
                found |= hit
            if want == OPEN:                       # still open at the end of the run: estimate
                rest = m & ~found
                out[rest, k] = np.maximum(window_days - days[rest, t], 1)
    return out


def _pack_parts(x):
    """0..1 floats -> uint8 0..100."""
    return np.clip(np.round(np.nan_to_num(x) * 100), 0, 100).astype("uint8")


def _pack_inputs(x):
    """Plain numbers -> int16 x10."""
    return np.clip(np.round(np.nan_to_num(x, nan=-0.1) * 10), -32000, 32000).astype("int16")


def habitat_all(inp, profiles, E, S):
    """Habitat fit (0..1) per species per square: (species, squares)."""
    from .score import habitat_fit
    return np.stack([habitat_fit(inp["squares"], p, E["habitat"], S["habitat_v03"]["tree_cover_min_pct"],
                                 S["soil_effect"]["neutral_at_rel_band"]) for p in profiles])


def run(run_file, mask, profiles=None, keep=None):
    """Score every profile for today + 7 days.

    mask: boolean (rows, cols) of candidate squares (e.g. all land).
    keep: optional function (habitat (species, n), squares dict) -> boolean (n,) of squares to run;
          default = squares with habitat for at least one species.
    Returns a dict of compact arrays, or None without profiles:
      score[code]  uint8 (n, 8), 0-100; parts[code] uint8 (n, 8, 5) x100; inputs[code] int16 (n, 8, 5) x10
      habitat (species, n) float32; general["key" | "all"] = best of those species, same layout
      + "best" (n, 8) index into general[...]["codes"].
    """
    profiles = profiles if profiles is not None else P.load_all()
    if not profiles:
        return None
    E, S = config.load("engine"), config.load("soil")
    inp = I.build(run_file, mask)
    hab = habitat_all(inp, profiles, E, S)
    sel = keep(hab, inp["squares"]) if keep else (hab > 0).any(axis=0)
    inp = I.subset(inp, sel)
    hab = hab[:, sel]
    t0 = inp["today_index"]
    days = slice(t0, t0 + N_DAYS)
    water = prepare_water(inp, E, S)
    rain3 = rolling_sum(inp["precip"], E["cycle"]["trigger_days"])
    common = [water["fill"][:, days] * 100, water["tsoil"][:, days], rain3[:, days]]

    codes = [p["code"] for p in profiles]
    out = {"codes": codes, "habitat": hab.astype("float32"), "score": {}, "parts": {}, "inputs": {},
           "profiles": {}, "rows": inp["rows"], "cols": inp["cols"], "dates": inp["dates"][days]}
    raw = []
    for prof in profiles:
        r = run_species(prof, inp, water, E, S)
        c = prof["code"]
        pp = P.engine_params(prof, E)
        sc = r["score"][:, days]
        raw.append(sc)
        out["score"][c] = _pack_parts(sc)
        out["parts"][c] = _pack_parts(np.stack([np.broadcast_to(r["habitat"][:, None], sc.shape), r["water"][:, days],
                                                r["temperature"][:, days], r["cycle"][:, days], r["prior"][:, days]],
                                               axis=2))
        left = _left_days(r["state"], t0, pp["window_days"], r["days"])
        out["inputs"][c] = _pack_inputs(np.stack(common + [r["state"][:, days].astype("float32"), left], axis=2))
        out["profiles"][c] = {"english_name": prof["english_name"], "latin_name": prof["latin_name"],
                              "tier": prof["tier"], "rare": bool(prof["rare"]), "group": prof["group"],
                              "confidence": prof["confidence"], "window_days": pp["window_days"],
                              "trigger_mm": pp["trigger_mm"], "unused_cues": pp["unused_cues"],
                              "season_text": season_text(prof["season_prior"])}
        del r
    raw = np.stack(raw)                                                   # (species, n, 8)
    n = raw.shape[1]
    ar, dd = np.arange(n)[:, None], np.arange(N_DAYS)[None, :]
    out["general"] = {}
    for name, members in (("key", [i for i, p in enumerate(profiles) if p["tier"] == "key"]),
                          ("all", list(range(len(profiles))))):
        sub = raw[members]
        has = hab[members][:, :, None] > 0                                # only species with habitat here
        best = np.where(has, sub, -1.0).argmax(axis=0)                    # (n, 8) index into members
        src = np.array(members)[best]                                     # index into codes
        out["general"][name] = {
            "codes": [codes[i] for i in members],
            "habitat": hab[members].max(axis=0),
            "score": _pack_parts(sub.max(axis=0)),
            "best": best.astype("uint8"),
            "parts": np.stack([out["parts"][c] for c in codes])[src, ar, dd],
            "inputs": np.stack([out["inputs"][c] for c in codes])[src, ar, dd],
        }
    return out
