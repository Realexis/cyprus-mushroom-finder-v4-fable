"""Run every species profile for the map: today + 7 days, on the given squares (v0.3 spec 3.1).

Returns plain arrays for the export (export/web.py). Scores are 0-100 (engine score x 100).
The general map = the best score among the profiled species (spec 3.2 step 6).
"""
import numpy as np

from .. import config
from . import inputs as I
from . import profile as P
from .cycle import OPEN, TRIGGERED
from .runner import general_map, prepare_water, rolling_sum, run_species

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


def run(run_file, mask, profiles=None):
    """mask: boolean (rows, cols) of the squares to score. Returns a dict, or None without profiles."""
    profiles = profiles if profiles is not None else P.load_all()
    if not profiles:
        return None
    E, S = config.load("engine"), config.load("soil")
    inp = I.build(run_file, mask)
    t0 = inp["today_index"]
    days = slice(t0, t0 + N_DAYS)
    water = prepare_water(inp, E, S)
    rain3 = rolling_sum(inp["precip"], E["cycle"]["trigger_days"])
    common_inp = [water["fill"][:, days] * 100, water["tsoil"][:, days], rain3[:, days]]

    out = {"codes": [], "habitat": {}, "score": {}, "parts": {}, "inputs": {}, "profiles": {},
           "rows": inp["rows"], "cols": inp["cols"], "dates": inp["dates"][days]}
    results = []
    for prof in profiles:
        r = run_species(prof, inp, water, E, S)
        c = prof["code"]
        pp = P.engine_params(prof, E)
        results.append(r)
        out["codes"].append(c)
        out["habitat"][c] = r["habitat"]
        out["score"][c] = r["score"][:, days] * 100
        out["parts"][c] = np.stack([np.broadcast_to(r["habitat"][:, None], r["score"][:, days].shape),
                                    r["water"][:, days], r["temperature"][:, days],
                                    r["cycle"][:, days], r["prior"][:, days]], axis=2)
        left = _left_days(r["state"], t0, pp["window_days"], r["days"])
        out["inputs"][c] = np.stack(common_inp + [r["state"][:, days].astype("float32"), left], axis=2)
        out["profiles"][c] = {"english_name": prof["english_name"], "latin_name": prof["latin_name"],
                              "tier": prof["tier"], "rare": bool(prof["rare"]), "group": prof["group"],
                              "confidence": prof["confidence"], "window_days": pp["window_days"],
                              "trigger_mm": pp["trigger_mm"], "unused_cues": pp["unused_cues"],
                              "season_text": season_text(prof["season_prior"])}
    best, idx = general_map(results)
    best = best[:, days] * 100
    idx = idx[:, days]
    n = len(best)
    ar = np.arange(n)[:, None]
    stack_p = np.stack([out["parts"][c] for c in out["codes"]])           # (species, n, 8, parts)
    stack_i = np.stack([out["inputs"][c] for c in out["codes"]])
    out["general"] = {"score": best, "best": idx,
                      "habitat": np.max(np.stack([out["habitat"][c] for c in out["codes"]]), axis=0),
                      "parts": stack_p[idx, ar, np.arange(N_DAYS)[None, :]],
                      "inputs": stack_i[idx, ar, np.arange(N_DAYS)[None, :]]}
    return out
