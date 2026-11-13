"""Rolling weather history, so each daily run only fetches a few days.

history.npz holds one column per date for every weather point. Each fetch is
merged in (newer runs overwrite older values for the same date). A date counts
as "observed" once a run delivered it as a PAST day (not only as a forecast).
"""
from datetime import date, timedelta

import numpy as np

from .. import config

STORE = config.PROCESSED / "weather" / "history.npz"
VARS = ["precip", "tmean", "tmin", "tmax", "rh", "soil", "tsoil_om"]   # tsoil_om: audit step 7
POINT_KEYS = ["lon", "lat", "x", "y", "elev_om"]
KEEP_DAYS = 240          # audit step 4: the engine runs from 1 September (season memory)


def _load(path):
    with np.load(path, allow_pickle=False) as z:
        return {k: z[k] for k in z.files}


def merge(run_path, store=STORE) -> dict:
    """Merge one fetch into the history store and save it."""
    run = _load(run_path)
    today = str(run["today"])
    run_dates = [str(d) for d in run["dates"]]
    if store.exists():
        h = _load(store)
        if not np.allclose(h["lon"], run["lon"]) or not np.allclose(h["lat"], run["lat"]):
            h = None                                          # point set changed: start again
    else:
        h = None
    old_dates = [] if h is None else [str(d) for d in h["dates"]]
    dates = sorted(set(old_dates) | set(run_dates))
    cutoff = (date.fromisoformat(today) - timedelta(days=KEEP_DAYS)).isoformat()
    dates = [d for d in dates if d >= cutoff]
    idx = {d: i for i, d in enumerate(dates)}
    n = len(run["lon"])
    out = {k: run[k] for k in POINT_KEYS}
    out["model"] = run["model"]
    for v in VARS:
        a = np.full((n, len(dates)), np.nan, "float32")
        if h is not None and v in h:                          # older stores have no soil temperature
            for j, d in enumerate(old_dates):
                if d in idx:
                    a[:, idx[d]] = h[v][:, j]
        if v in run:
            for j, d in enumerate(run_dates):
                a[:, idx[d]] = run[v][:, j]
        out[v] = a
    observed = np.zeros(len(dates), bool)
    if h is not None:
        for j, d in enumerate(old_dates):
            if d in idx:
                observed[idx[d]] = h["observed"][j]
    for d in run_dates:
        if d < today:
            observed[idx[d]] = True
    out["dates"] = np.array(dates)
    out["observed"] = observed
    out["last_run"] = today
    store.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(store, **out)
    return out


def complete_for(today: date, past_days: int, store=STORE, skip_recent: int = 0) -> bool:
    """True if every past day the score needs is in the store as an observed day.

    skip_recent: the newest N past days are about to be fetched anyway, so do not require them.
    """
    if not store.exists():
        return False
    h = _load(store)
    obs = {str(d): bool(o) for d, o in zip(h["dates"], h["observed"])}
    need = [(today - timedelta(days=k)).isoformat() for k in range(skip_recent + 1, past_days + 1)]
    return all(obs.get(d, False) for d in need)


def assemble(today: date, past_days: int, forecast_days: int, out_path, store=STORE):
    """Write a run file (same format as a full fetch) for today from the store."""
    h = _load(store)
    dates = [str(d) for d in h["dates"]]
    want = [(today + timedelta(days=k)).isoformat() for k in range(-past_days, forecast_days)]
    missing = [d for d in want if d not in dates]
    if missing:
        raise RuntimeError(f"history is missing {len(missing)} days, e.g. {missing[:3]}")
    cols = [dates.index(d) for d in want]
    out = {k: h[k] for k in POINT_KEYS}
    for v in VARS:
        out[v] = h[v][:, cols]
    np.savez_compressed(out_path, dates=np.array(want), today=today.isoformat(),
                        model=h["model"], **out)
    return out_path


def season_start(today: date) -> date:
    """1 September of the mushroom season that `today` belongs to (Sep-Aug)."""
    return date(today.year if today.month >= 9 else today.year - 1, 9, 1)


def season_past_days(today: date, past_days: int, store=STORE) -> int:
    """How many past days the engine can use: back to 1 September, as far as the store has
    unbroken observed days. Never fewer than `past_days` (the normal run)."""
    if not store.exists():
        return past_days
    h = _load(store)
    obs = {str(d): bool(o) for d, o in zip(h["dates"], h["observed"])}
    want = (today - season_start(today)).days
    k = past_days
    while k < want and obs.get((today - timedelta(days=k + 1)).isoformat(), False):
        k += 1
    return k


def assemble_season(today: date, past_days: int, forecast_days: int, out_path, store=STORE):
    """The engine's run file: from 1 September (or as far back as the store goes) to today + forecast.
    Returns (path, number of past days)."""
    k = season_past_days(today, past_days, store)
    return assemble(today, k, forecast_days, out_path, store), k
