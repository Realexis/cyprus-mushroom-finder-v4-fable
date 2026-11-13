"""Species filters, the S7 general-map rule, photo licences and nearest track/road."""
import geopandas as gpd
import numpy as np
from shapely.geometry import LineString

from shroomy import config
from shroomy.export.roads import Nearest
from shroomy.export.species import allowed_photos
from shroomy.score import species as SP
from shroomy.score.factors import FACTORS, combine

W = {"rain_total": 0.20, "rain_pulse": 0.15, "temperature": 0.25,
     "soil_moisture": 0.15, "season_altitude": 0.15, "shade": 0.10}
SPEC = {"trees": [1, 2], "bands": [2, 3], "months": [10, 11, 12, 1]}


def test_general_habitat_drops_other_broadleaf():
    hf = np.array([1, 1, 1, 1, 0])
    tree = np.array([1, 3, 4, 2, 1])
    assert SP.general_habitat(hf, tree, [1, 2, 3]).tolist() == [True, True, False, True, False]


def test_config_general_trees_follow_s7():
    assert 4 not in config.load("scoring")["score"]["general_map_trees"]


def test_species_habitat_needs_tree_and_band():
    hf = np.ones(4)
    tree = np.array([1, 1, 3, 2])
    band = np.array([1, 2, 2, 3])
    assert SP.species_habitat(hf, tree, band, SPEC).tolist() == [False, True, False, True]


def test_species_habitat_respects_closed_reserves():
    assert not SP.species_habitat(np.array([0]), np.array([1]), np.array([2]), SPEC)[0]


def test_season_window_wraps_new_year():
    assert SP.in_season(1, SPEC) and SP.in_season(10, SPEC)
    assert not SP.in_season(3, SPEC)


def test_species_score_is_zero_out_of_season():
    f = {k: np.array([1.0]) for k in FACTORS}
    assert SP.species_score(f, W, np.array([1]), 6, SPEC)[0] == 0


def test_species_score_equals_general_with_full_season():
    """Inside the window the species score is the general formula with season = 1."""
    f = {k: np.array([0.3, 0.8]) for k in FACTORS}
    f1 = dict(f, season_altitude=np.array([1.0, 1.0]))
    s = SP.species_score(f, W, np.array([1, 1]), 11, SPEC)
    assert np.allclose(s, combine(f1, W, np.array([1, 1])))


def test_base_plus_season_rebuilds_general_score():
    f = {k: np.array([0.4]) for k in FACTORS}
    f["season_altitude"] = np.array([0.5])
    general = combine(f, W, np.array([1]))
    rebuilt = SP.base_score(f, W) + SP.season_share(W) * 0.5
    assert np.allclose(general, rebuilt)


def test_months_text():
    assert SP.months_text([10, 11, 12, 1]) == "Oct-Jan"
    assert SP.months_text([3, 4]) == "Mar-Apr"


def test_every_species_uses_known_trees_bands_months():
    for s in config.load("species")["species"]:
        assert set(s["trees"]) <= {1, 2, 3, 4}, s["code"]
        assert set(s["bands"]) <= {1, 2, 3}, s["code"]
        assert set(s["months"]) <= set(range(1, 13)), s["code"]
        assert s["bands"] and s["months"], s["code"]
        # v0.3: field, fennel and scrub species have no partner tree.
        assert s["trees"] or s["code"] in {"pfe", "cco", "aca", "ter"}, s["code"]


def test_only_morels_use_other_broadleaf():
    """[S7] 'Other broadleaf' counts only for the morel filter."""
    for s in config.load("species")["species"]:
        assert (4 in s["trees"]) == (s["code"] == "mor"), s["code"]


def test_photo_licence_filter():
    taxon = {"taxon_photos": [
        {"photo": {"id": 1, "license_code": "cc-by-nc-nd", "attribution": "a", "medium_url": "u1"}},
        {"photo": {"id": 2, "license_code": None, "attribution": "b", "medium_url": "u2"}},
        {"photo": {"id": 3, "license_code": "cc-by-nc", "attribution": "c", "medium_url": "u3"}},
        {"photo": {"id": 4, "license_code": "cc0", "attribution": "d", "medium_url": "u4"}},
        {"photo": {"id": 5, "license_code": "cc-by-sa", "attribution": "e", "medium_url": "u5"}},
    ]}
    got = allowed_photos(taxon, 5)
    assert [p["licence"] for p in got] == ["CC BY-NC", "CC0", "CC BY-SA"]
    assert all(p["attribution"] and p["page"].endswith(str(i)) for p, i in zip(got, [3, 4, 5]))


def test_lookalikes_never_use_soft_words():
    """Every lookalike is labelled deadly or toxic, nothing softer."""
    for lk in config.load("lookalikes")["lookalikes"]:
        assert lk["severity"] in {"deadly", "toxic"}


def test_nearest_track_and_road():
    gdf = gpd.GeoDataFrame({
        "kind": ["path", "minor_road", "minor_road"],
        "kind_detail": ["track", "unclassified", "service"],
        "name": ["", "Forest Road", ""], "name:en": ["", "", ""],
    }, geometry=[LineString([(0, 100), (1000, 100)]), LineString([(0, 500), (1000, 500)]),
                 LineString([(0, 10), (1000, 10)])])
    n = Nearest(gdf)
    d = n.describe(500, 0)
    assert d == {"track_km": 0.1, "road_km": 0.5, "road": "Forest Road"}   # service roads ignored
