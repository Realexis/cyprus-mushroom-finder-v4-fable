"""Unit tests for the v0.3 species engine (spec section 5): bucket, degree-days,
state machine, multiplied score. The profile here is a TEST profile, not a real species."""
import copy

import numpy as np
import pytest

from shroomy import config
from shroomy.engine import bucket as B
from shroomy.engine import cycle as C
from shroomy.engine.profile import ProfileError, check, engine_params, load
from shroomy.engine.runner import general_map, prepare_water, run_species
from shroomy.engine.score import combine, habitat_fit, season_prior, soil_fit, temperature_fit
from shroomy.engine.soiltemp import degree_days, soil_temp_proxy

E = config.load("engine")
S = config.load("soil")
BC = E["bucket"]

TEST_PROFILE = {
    "code": "tst", "group": "pine_partner", "tier": "key", "rare": False, "confidence": "low",
    "english_name": "test species", "latin_name": "Testus testus",
    "local_name": {"name": "-", "confirmed": False},
    "host_trees": {"calabrian_pine": 1.0, "black_pine": 0.8, "kermes_oak": 0.4},
    "altitude_range": [0, 1950], "trigger_mm": 20,
    "wait_degree_days": {"total": 60, "base_c": 5},
    "soil_temp_window": {"min": 4, "best": [10, 16], "max": 24},
    "extra_cues": {}, "window_length_days": 10, "recovery_days": 20,
    "season_prior": {"oct": 1.0, "nov": 1.0},
    "soil_pref": {"ph": "unknown", "texture": "unknown", "weight": 0.9},
    "lookalikes": ["a", "b"], "sources": ["test"],
}
P = engine_params(TEST_PROFILE, E)


# ------------------------------------------------------------------ bucket
def test_ra_matches_fao56_example():
    # FAO-56 example 8: 20 S, 3 September -> Ra = 32.2 MJ m-2 day-1
    assert B.extraterrestrial_radiation(-20, 246) == pytest.approx(32.2, abs=0.2)


def test_hargreaves():
    ra = B.extraterrestrial_radiation(35, 300)
    assert B.hargreaves_et0(15, 10, 20, ra) > 0
    assert B.hargreaves_et0(15, 15, 15, ra) == 0                 # no daily range -> no ET
    assert B.hargreaves_et0(25, 15, 35, ra) > B.hargreaves_et0(10, 5, 15, ra)


def _bucket(rain, et0=2.0, cap=30.0, shade=0.5, drain=2, days=None):
    days = days or len(rain)
    r = np.array(rain, float)[None, :]
    e = np.full((1, days), et0)
    return B.run_bucket(r, e, np.array([cap]), B.slope_factor(np.array([shade]), BC),
                        B.drain_rate(np.array([drain]), BC), BC)[0]


def test_bucket_fills_and_caps():
    f = _bucket([0, 40, 100, 0])
    assert f[0] < f[1] <= 1.0
    assert f[2] == pytest.approx(1.0, abs=0.1)                    # never above the capacity
    assert f.max() <= 1.0


def test_bucket_drains_without_rain():
    f = _bucket([50] + [0] * 20)
    assert np.all(np.diff(f) <= 1e-9)
    assert f[-1] < 0.5 * f[0]


def test_drizzle_is_caught_by_canopy():
    f = _bucket([BC["interception_mm"] * 0.9] * 5, et0=0.0)
    assert np.allclose(f, BC["start_fill"], atol=1e-6)


def test_sunny_slope_dries_faster_than_shade():
    rain = [50] + [0] * 10
    assert _bucket(rain, shade=0.0)[-1] < _bucket(rain, shade=1.0)[-1]


def test_fast_drainage_dries_faster():
    rain = [50] + [0] * 5
    assert _bucket(rain, drain=1)[-1] < _bucket(rain, drain=3)[-1]


def test_capacity_blends_by_certainty():
    med = 27.0
    sure = B.blended_capacity(40, 39, 41, med, 1.0, BC)           # narrow band -> close to 40
    unsure = B.blended_capacity(40, 10, 90, med, 1.0, BC)         # band 2x the value -> median
    nodata = B.blended_capacity(np.nan, np.nan, np.nan, med, 1.0, BC)
    assert sure == pytest.approx(40 - 13 * 0.05, abs=0.01)
    assert unsure == pytest.approx(med)
    assert nodata == pytest.approx(med)


# ------------------------------------------------------------------ soil temperature
def test_soil_temp_lags_air():
    air = np.array([[10] * 3 + [20] * 10], float)
    ts = soil_temp_proxy(air, 4)[0]
    assert ts[2] == pytest.approx(10)
    assert 10 < ts[3] < 20 and ts[-1] > ts[4]
    assert ts[-1] == pytest.approx(20, abs=1.0)


def test_degree_days():
    assert degree_days(12, 5) == 7
    assert degree_days(3, 5) == 0
    assert np.sum(degree_days(np.array([4, 6, 8, 10]), 5)) == 1 + 3 + 5


# ------------------------------------------------------------------ cycle
def _run(rain, fill, tsoil, frost=None, prof=P, new_season=None):
    n = len(rain)
    rw = np.array(rain, float)[None, :]
    f = np.array(fill, float)[None, :]
    ts = np.array(tsoil, float)[None, :]
    fr = np.zeros((1, n), bool) if frost is None else np.array(frost, bool)[None, :]
    tok = temperature_fit(ts, prof["temp"]) > 0
    return C.run_cycle(rw, f, ts, tok, fr, prof, E["cycle"], new_season)


P0 = engine_params({**TEST_PROFILE, "recovery_days": 0}, E)     # forest species after audit step 3
REWET = E["cycle"]["rewet_wait_days"]


def test_full_cycle():
    n = 60
    rain = [0, 0, 30] + [0] * (n - 3)                    # one soaking rain on day 2
    out = _run(rain, [0.9] * n, [11] * n)                # 6 degree-days a day, 60 needed
    s = out["state"][0]
    assert s[0] == C.PRIMED and s[2] == C.TRIGGERED
    first_open = int(np.argmax(s == C.OPEN))
    assert first_open == 2 + 10                          # 10 days x 6 dd = 60
    assert np.sum(s == C.OPEN) == P["window_days"]
    after = first_open + P["window_days"]
    assert s[after] == C.SPENT
    assert s[after + E["cycle"]["spent_days"]] == C.RECOVERING
    assert s[after + P["recovery_days"]] == C.PRIMED
    assert out["trigger_t"][0, first_open] == 2


def test_warm_opens_sooner_than_cool():
    n = 40
    rain = [30] + [0] * (n - 1)
    warm = _run(rain, [0.9] * n, [14] * n)["state"][0]
    cool = _run(rain, [0.9] * n, [7] * n)["state"][0]
    assert np.argmax(warm == C.OPEN) < np.argmax(cool == C.OPEN)


def test_dry_soil_cancels_the_wait():
    n = 30
    fill = [0.9] * 3 + [0.05] * (n - 3)
    s = _run([30] + [0] * (n - 1), fill, [11] * n)["state"][0]
    assert s[0] == C.TRIGGERED and s[3] == C.PRIMED
    assert not np.any(s == C.OPEN)


def test_frost_closes_an_open_window():
    n = 30
    frost = [False] * 15 + [True] + [False] * (n - 16)
    s = _run([30] + [0] * (n - 1), [0.9] * n, [11] * n, frost)["state"][0]
    assert s[14] == C.OPEN and s[15] == C.PRIMED


def test_rain_while_spent_is_ignored():
    n = 50
    rain = [30] + [0] * 20 + [30] * 3 + [0] * (n - 24)   # window: days 10-19; more rain on 21-23
    s = _run(rain, [0.9] * n, [11] * n)["state"][0]
    assert s[20] == C.SPENT
    assert np.all(s[21:24] != C.TRIGGERED)


def test_hot_soil_is_dormant():
    s = _run([30] * 5, [0.9] * 5, [30] * 5)["state"][0]
    assert np.all(s == C.DORMANT)


def test_cycle_factor_rises_while_triggered():
    out = _run([30] + [0] * 11, [0.9] * 12, [11] * 12)
    f = out["factor"][0]
    assert f[0] < f[5] < f[9] < f[10] == E["cycle"]["factor"]["open"]


def test_new_rain_reopens_after_two_days_once_the_season_started():
    """LOI19: after the first flush, surveys go out 1-2 days after each new rain. No 21-day rest."""
    n = 60
    rain = [30] + [0] * 29 + [30] + [0] * (n - 31)
    fill = [0.9] * 14 + [0.05] * 6 + [0.9] * (n - 20)   # window opens day 10, dry soil closes it day 14
    s = _run(rain, fill, [11] * n, prof=P0)["state"][0]
    assert s[10] == C.OPEN and s[14] == C.PRIMED
    assert s[30] == C.TRIGGERED
    assert s[30 + REWET] == C.OPEN                      # 2 days, not another 10-day degree-day wait


def test_first_flush_still_needs_the_full_wait():
    n = 30
    s = _run([30] + [0] * (n - 1), [0.9] * n, [11] * n, prof=P0)["state"][0]
    assert int(np.argmax(s == C.OPEN)) == 10             # 60 dd at 6 a day


def test_wet_window_goes_on_as_late_window():
    n = 40
    fill = [0.9] * 30 + [0.05] * (n - 30)
    out = _run([30] + [0] * (n - 1), fill, [11] * n, prof=P0)
    s, f = out["state"][0], out["factor"][0]
    assert np.all(s[10:30] == C.OPEN)                    # past its 10 days while the soil stays wet
    assert f[15] == E["cycle"]["factor"]["open"]
    assert f[25] == E["cycle"]["factor"]["late_open"]
    assert s[30] == C.PRIMED                             # dry soil closes it
    assert not np.any(s == C.SPENT)


def test_species_with_recovery_still_rest():
    n = 50
    s = _run([30] + [0] * (n - 1), [0.9] * n, [11] * n)["state"][0]   # recovery_days 20
    assert s[20] == C.SPENT


def test_1_september_resets_the_season():
    n = 40
    rain = [30] + [0] * 24 + [30] + [0] * (n - 26)
    fill = [0.9] * 14 + [0.05] * 6 + [0.9] * (n - 20)
    ns = [False] * 20 + [True] + [False] * (n - 21)     # new season starts on day 20
    s = _run(rain, fill, [11] * n, prof=P0, new_season=ns)["state"][0]
    assert s[25] == C.TRIGGERED and s[25 + REWET] != C.OPEN   # full degree-day wait again
    assert s[35] == C.OPEN


# ------------------------------------------------------------------ score
def test_zero_water_gives_near_zero_score():
    # perfect habitat, temperature, cycle and season - but a dry bucket
    s = combine(1.0, 0.0, 1.0, 1.0, 1.0)
    assert s == 0
    fill = np.array([0.1])
    from shroomy.engine.score import water_fit
    assert combine(1.0, water_fit(fill, *P["water"]), 1.0, 1.0, 1.0)[0] < 0.02


def test_multiply_not_sum():
    assert combine(0.1, 1.0, 1.0, 1.0, 1.0) == pytest.approx(0.1)
    assert combine(0.5, 0.5, 0.5, 1.0, 1.0) == pytest.approx(0.125)


def test_season_prior_is_soft():
    sp = season_prior(np.arange(1, 13), P["season"], E["season_prior"]["floor"])
    assert sp.min() == 0.5 and sp.max() == 1.0
    assert sp[9] == 1.0 and sp[6] == 0.5                # oct in, jul out


def test_temperature_fit_shape():
    t = temperature_fit(np.array([0, 4, 7, 12, 20, 24, 30]), P["temp"])
    assert t[0] == 0 and t[1] == 0 and 0 < t[2] < 1 and t[3] == 1
    assert 0 < t[4] < 1 and t[5] == 0 and t[6] == 0


def _squares(n=6):
    return {"likely_tree": np.array([1, 2, 3, 4, 1, 1], float)[:n],
            "tree_cover_pct": np.array([60, 60, 60, 60, 5, 60], float)[:n],
            "elevation_m": np.array([500, 1500, 800, 800, 500, 500], float)[:n],
            "reserve_id": np.array([0, 0, 0, 0, 0, 3], float)[:n],
            "ph": np.full(n, 7.0), "ph_q05": np.full(n, 5.0), "ph_q95": np.full(n, 8.5),
            "drainage": np.full(n, 2.0), "awc_certainty": np.zeros(n),
            "igneous_fraction": np.ones(n), "calcareous_frac": np.zeros(n),
            "clc_burnt": np.zeros(n), "grass_frac": np.zeros(n)}


def test_habitat_fit():
    h = habitat_fit(_squares(), TEST_PROFILE, E["habitat"], 30, 1.0)
    assert h[0] == pytest.approx(1.0)                    # calabrian pine 1.0
    assert h[1] == pytest.approx(0.8)                    # black pine 0.8
    assert h[2] == 0 and h[3] == 0                       # golden oak / broadleaf not hosts here
    assert h[4] == 0                                     # too little tree cover
    assert h[5] == 0                                     # nature reserve: closed


def test_uncertain_soil_is_neutral():
    sq = _squares()
    pref = {"ph": "acid", "weight": 0.8}
    wide = soil_fit({**sq, "ph": np.full(6, 8.0)}, pref, E["habitat"], 1.0)
    sure = soil_fit({**sq, "ph": np.full(6, 8.0), "ph_q05": np.full(6, 7.9), "ph_q95": np.full(6, 8.1)},
                    pref, E["habitat"], 1.0)
    assert np.all(sure < 0.81) and np.all(sure >= 0.8)   # sure + wrong pH -> down to the weight
    assert np.all(wide > sure)                           # unsure -> pulled towards 1.0


def test_needs_burn():
    p = copy.deepcopy(TEST_PROFILE)
    p["extra_cues"] = {"needs_burn": True}
    sq = _squares()
    assert habitat_fit(sq, p, E["habitat"], 30, 1.0)[0] == 0
    sq["clc_burnt"] = np.ones(6)
    assert habitat_fit(sq, p, E["habitat"], 30, 1.0)[0] == pytest.approx(1.0)


# ------------------------------------------------------------------ profiles
def test_profile_check():
    check(TEST_PROFILE)
    bad = {k: v for k, v in TEST_PROFILE.items() if k != "trigger_mm"}
    with pytest.raises(ProfileError, match="trigger_mm"):
        check(bad)
    with pytest.raises(ProfileError, match="weight"):
        check({**TEST_PROFILE, "soil_pref": {"ph": "acid", "weight": 0.5}})


def test_template_profile_is_valid():
    load(config.ROOT / "species" / "_template.yaml")


# ------------------------------------------------------------------ runner end to end
def test_runner_end_to_end():
    n, d = 6, 40
    precip = np.zeros((n, d))
    precip[:3, 5] = 40                                   # rain on squares 0-2 only
    inp = {"lat": np.full(n, 34.9), "doy": 280 + np.arange(d), "month": np.full(d, 10),
           "precip": precip, "tmean": np.full((n, d), 13.0), "tmin": np.full((n, d), 8.0),
           "tmax": np.full((n, d), 18.0), "tsoil": None, "island_awc_median": 27.0,
           "squares": {**_squares(n), "awc_mm": np.full(n, 27.0), "awc_q05_mm": np.full(n, 10.0),
                       "awc_q95_mm": np.full(n, 60.0), "shade_score": np.full(n, 0.5)}}
    water = prepare_water(inp, E, S)
    r = run_species(TEST_PROFILE, inp, water, E, S)
    assert r["score"].shape == (n, d)
    assert r["score"][0].max() > 0.5                     # wet pine square opens a window
    assert r["score"][4:].max() == 0                     # no habitat -> 0
    assert r["score"][0].max() > 5 * r["score"][3].max() + 1e-9
    best, idx = general_map([r, r])
    assert np.array_equal(best, r["score"]) and idx.max() == 0


# ------------------------------------------------------------------ step 5: profiles + map run
def test_real_profiles_load():
    from shroomy.engine.profile import load_all
    codes = {p["code"] for p in load_all()}
    assert {"lde", "lsa"} <= codes


def test_season_text():
    from shroomy.engine.daily import season_text
    assert season_text({"sep": 0.3, "oct": 1, "nov": 1, "dec": 1, "jan": 1}) == "Oct-Jan"
    assert season_text({"sep": 1, "oct": 1, "nov": 0.3}) == "Sep-Oct"
    assert season_text({}) == "all year"


def test_left_days_reads_the_run():
    from shroomy.engine.daily import _left_days
    # square 0: triggered on days 0-2, open 3-5, then spent; square 1: open from day 0 to the end
    state = np.array([[C.TRIGGERED] * 3 + [C.OPEN] * 3 + [C.SPENT] * 4,
                      [C.OPEN] * 10], "int8")
    days = np.array([[0] * 3 + [0, 1, 2] + [0] * 4, list(range(10))], "int16")
    left = _left_days(state, 0, 10, days)
    assert left[0, 0] == 3 and left[0, 3] == 3 and left[0, 5] == 1   # opens in 3; open 3 / 1 more days
    assert left[0, 6] == -1                                           # spent: nothing to count
    assert left[1, 7] == 3                                            # open to the end: 10 - 7 days


def test_summary_clock_words():
    from shroomy.export.summary import engine_clock
    assert engine_clock({"state": 3, "left_days": 4}) == "Window open, about 4 more days."
    assert "opens in about 1 day." in engine_clock({"state": 2, "left_days": 1})
    assert "soaking rain" in engine_clock({"state": 1, "left_days": -1})


def test_scores_file_round_trip(tmp_path):
    from shroomy.export.web_v03 import write_info, write_scores
    idx = np.array([2, 5, 9])
    sc = np.arange(24, dtype="uint8").reshape(3, 8)
    write_scores(tmp_path / "s.bin", idx, sc)
    b = (tmp_path / "s.bin").read_bytes()
    n, days = np.frombuffer(b[:8], "<u4")
    assert (n, days) == (3, 8)
    assert list(np.frombuffer(b[8:20], "<u4")) == [2, 5, 9]
    assert np.array_equal(np.frombuffer(b[20:], "u1").reshape(3, 8), sc)
    parts = np.full((3, 8, 5), 50, "uint8")
    inputs = np.full((3, 8, 6), -7, "int16")
    write_info(tmp_path / "i.bin", parts, inputs)
    b = (tmp_path / "i.bin").read_bytes()
    assert list(np.frombuffer(b[:16], "<u4")) == [3, 8, 5, 6]
    start = 16 + 120 + (120 % 2)
    assert np.all(np.frombuffer(b[start:], "<i2") == -7)


def test_all_profiles_valid_and_tiers():
    from shroomy.engine.profile import load_all
    ps = load_all()
    tiers = {p["code"]: p["tier"] for p in ps}
    assert len(ps) == 14
    assert sum(t == "key" for t in tiers.values()) == 7 and sum(t == "more" for t in tiers.values()) == 7
    assert {p["code"] for p in ps if p["rare"]} == {"cci", "ter"}


def test_land_cover_needs_a_real_share():
    p = copy.deepcopy(TEST_PROFILE)
    p["host_trees"] = {}
    p["land_cover"] = {"grass_frac": 1.0}
    sq = _squares()
    sq["grass_frac"] = np.array([0.05, 0.3, 0.6, 1.0, 0.0, 1.0])
    h = habitat_fit(sq, p, E["habitat"], 30, 1.0)
    assert h[0] == 0 and 0 < h[1] < 1 and h[2] == 1 and h[4] == 0
    assert h[5] == 0                                      # reserve


def test_rain_dependence_and_confidence():
    from shroomy.engine.daily import confidence, rain_dependence
    wet = np.array([0.8, 0.8, 0.8, 0.0])
    dry = np.array([0.8, 0.4, 0.0, 0.0])
    dep = rain_dependence(wet, dry)
    assert np.allclose(dep, [0.0, 0.5, 1.0, 0.0])          # no score -> nothing depends on rain
    c = confidence(dep, E["confidence"])
    assert list(c) == [0, 1, 2, 0]                          # sure, likely, unsure, sure


def test_window_from_past_rain_is_sure_days_ahead():
    """A window opened by rain that already fell stays 'sure' in the forecast days (spec 3.7)."""
    from shroomy.engine.daily import confidence, rain_dependence
    n, d, t0 = 1, 30, 20
    precip = np.zeros((n, d)); precip[0, 5] = 40              # soaking rain long before today
    inp = {"lat": np.full(n, 34.9), "doy": 280 + np.arange(d), "month": np.full(d, 10),
           "precip": precip, "tmean": np.full((n, d), 13.0), "tmin": np.full((n, d), 8.0),
           "tmax": np.full((n, d), 18.0), "tsoil": None, "island_awc_median": 27.0,
           "squares": {**_squares(n), "awc_mm": np.full(n, 27.0), "awc_q05_mm": np.full(n, 10.0),
                       "awc_q95_mm": np.full(n, 60.0), "shade_score": np.full(n, 1.0)}}
    wet = run_species(TEST_PROFILE, inp, prepare_water(inp, E, S), E, S)["score"][:, t0:]
    dry_inp = dict(inp); dry_inp["precip"] = precip.copy(); dry_inp["precip"][:, t0 + 1:] = 0
    dry = run_species(TEST_PROFILE, dry_inp, prepare_water(dry_inp, E, S), E, S)["score"][:, t0:]
    assert np.all(confidence(rain_dependence(wet, dry), E["confidence"]) == 0)


def test_bucket_starts_empty_in_september():
    from shroomy.engine.runner import start_fill
    assert start_fill({"dates": ["2026-09-01", "2026-09-02"]}, BC) == BC["start_fill_september"] == 0.0
    assert start_fill({"dates": ["2026-10-13"]}, BC) == BC["start_fill"]
    assert start_fill({}, BC) == BC["start_fill"]
