"""Backtest helpers: which records count for a profile, find events, the fair score."""
import numpy as np

from shroomy.backtest import RECORD_RULES, classify, fair_score, find_events, nearest_open_offset


def rec(taxon, rank="species", ids=(), date="2025-12-27", lat=35.05, lon=32.36, source="iNaturalist"):
    return {"taxon": taxon, "rank": rank, "ancestor_ids": list(ids), "date": date, "lat": lat, "lon": lon,
            "source": source}


def test_cistus_milk_caps_do_not_count_as_red_pine():
    rule = RECORD_RULES["lde"]
    assert classify(rec("Lactarius tesquorum"), rule) is None
    assert classify(rec("Lactarius cistophilus"), rule) is None
    assert classify(rec("Lactarius deliciosus"), rule) == "strong"
    assert classify(rec("Lactarius", "genus"), rule) == "strong"


def test_white_brittlegill_needs_delica_or_brevipes():
    rule = RECORD_RULES["rde"]
    assert classify(rec("Russula delica"), rule) == "strong"
    assert classify(rec("Russula chloroides", ids=[48340, 1167951, 5]), rule) == "strong"
    assert classify(rec("Russula", "genus"), rule) == "weak"
    assert classify(rec("Russula albonigra"), rule) is None


def test_agaricus_is_genus_only():
    assert classify(rec("Agaricus campestris"), RECORD_RULES["aca"]) == "weak"


def test_same_day_same_place_is_one_event():
    rs = [{**rec("Morchella importuna", date="2026-02-28", lat=35.61, lon=34.39), "strength": "strong"}
          for _ in range(23)]
    rs.append({**rec("Morchella", date="2026-03-10", lat=34.96, lon=32.44), "strength": "strong"})
    ev = find_events(rs)
    assert len(ev) == 2
    assert ev[0]["records"] == 23


def test_two_places_same_day_are_two_events():
    rs = [{**rec("Suillus", lat=35.6, lon=34.36), "strength": "strong"},
          {**rec("Suillus collinitus", lat=35.05, lon=32.36), "strength": "strong"}]
    assert len(find_events(rs)) == 2


def test_open_offset():
    o = np.array([0, 0, 1, 1, 0, 0, 0, 0], bool)
    assert nearest_open_offset(o, 2) == 0
    assert nearest_open_offset(o, 5) == -2          # closed 2 days before (last open day was day 3)
    assert nearest_open_offset(o, 0) == 2           # opens 2 days later
    assert nearest_open_offset(np.zeros(5, bool), 2) is None


def test_fair_score_compares_hits_with_base_rate():
    ev = [{"open_5km": True, "open_days_share_5km": 0.5}, {"open_5km": False, "open_days_share_5km": 0.5}]
    f = fair_score(ev)
    assert f["hit_rate"] == 0.5 and f["base_rate"] == 0.5 and f["gap"] == 0.0
    assert fair_score([])["events"] == 0
