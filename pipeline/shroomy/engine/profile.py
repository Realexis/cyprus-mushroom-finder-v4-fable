"""Species profiles: one YAML file per species in species/ (v0.3 spec 3.1, 3.4).

The format is described in species/README.md. Every profile must have every field of
spec 3.4; this module checks that and turns a profile into the numbers the engine uses.
"""
from pathlib import Path

import yaml

from .. import config

SPECIES_DIR = config.ROOT / "species"
MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]

REQUIRED = ["code", "group", "host_trees", "altitude_range", "trigger_mm", "wait_degree_days",
            "soil_temp_window", "extra_cues", "window_length_days", "recovery_days",
            "season_prior", "tier", "rare", "confidence", "local_name", "english_name",
            "latin_name", "lookalikes", "soil_pref", "sources"]
GROUPS = {"pine_partner", "oak_partner", "litter_recycler", "field_recycler", "fennel_root",
          "burn", "underground"}
# Extra cues the engine knows how to use today. Others are kept but have no effect yet.
KNOWN_CUES = {"needs_burn"}


class ProfileError(ValueError):
    pass


def check(p: dict, name: str = "profile") -> dict:
    """Raise ProfileError if a field is missing or out of range. Returns p."""
    miss = [k for k in REQUIRED if k not in p]
    if miss:
        raise ProfileError(f"{name}: missing {', '.join(miss)}")
    err = []
    if p["group"] not in GROUPS:
        err.append(f"group must be one of {sorted(GROUPS)}")
    if p["tier"] not in ("key", "more"):
        err.append("tier must be key or more")
    if p["confidence"] not in ("low", "medium"):
        err.append("confidence must be low or medium")
    lo, hi = p["altitude_range"]
    if not lo <= hi:
        err.append("altitude_range must be [low, high]")
    w = p["soil_temp_window"]
    best = w["best"] if isinstance(w["best"], list) else [w["best"], w["best"]]
    if not w["min"] <= best[0] <= best[1] <= w["max"]:
        err.append("soil_temp_window must be min <= best <= max")
    if p["wait_degree_days"]["total"] <= 0:
        err.append("wait_degree_days.total must be > 0")
    for m, v in p["season_prior"].items():
        if m not in MONTHS or not 0 <= v <= 1:
            err.append(f"season_prior {m}: month name jan..dec and value 0..1")
    sw = p["soil_pref"].get("weight", 1.0)
    if not 0.8 <= sw <= 1.0:
        err.append("soil_pref.weight must be 0.8..1.0 (spec 3.4)")
    for t, v in p["host_trees"].items():
        if not 0 <= v <= 1:
            err.append(f"host_trees {t}: weight 0..1")
    # Spec 3.4 wants 2-3. Until sourced lookalikes exist (TODO-facts L5) we accept 1-3,
    # and never make one up.
    if not 1 <= len(p["lookalikes"]) <= 3:
        err.append("lookalikes: 1-3 specific to this species (spec 3.4 wants 2-3)")
    if err:
        raise ProfileError(f"{name}: " + "; ".join(err))
    return p


def engine_params(p: dict, ecfg: dict) -> dict:
    """The numbers the cycle and score need, with engine defaults filled in."""
    w = p["soil_temp_window"]
    best = w["best"] if isinstance(w["best"], list) else [w["best"], w["best"]]
    wf = p.get("water_fit", {})
    return {
        "trigger_mm": float(p["trigger_mm"]),
        "trigger_days": int(p.get("trigger_days", ecfg["cycle"]["trigger_days"])),
        "wait_dd": float(p["wait_degree_days"]["total"]),
        "base_c": float(p["wait_degree_days"]["base_c"]),
        "window_days": int(p["window_length_days"]),
        "recovery_days": int(p["recovery_days"]),
        "temp": (float(w["min"]), float(best[0]), float(best[1]), float(w["max"])),
        "water": (float(wf.get("zero_at_fill", ecfg["water_fit"]["zero_at_fill"])),
                  float(wf.get("full_at_fill", ecfg["water_fit"]["full_at_fill"]))),
        "season": [float(p["season_prior"].get(m, 0.0)) for m in MONTHS],
        "unused_cues": sorted(set(p["extra_cues"] or {}) - KNOWN_CUES),
    }


def load(path) -> dict:
    path = Path(path)
    with open(path, encoding="utf-8") as f:
        p = yaml.safe_load(f)
    return check(p, path.name)


def load_all(folder=SPECIES_DIR) -> list[dict]:
    """Every profile in species/ (files starting with _ are templates, skipped)."""
    return [load(f) for f in sorted(Path(folder).glob("*.yaml")) if not f.name.startswith("_")]
