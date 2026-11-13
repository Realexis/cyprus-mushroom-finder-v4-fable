"""v0.3 soil helpers: water capacity and drainage classes."""
import numpy as np

from shroomy import config
from shroomy.habitat.v03 import awc_layer, drainage_class


def test_awc_layer_basic():
    # 0.30 at field capacity, 0.15 at wilting point, no stones, 100 mm thick -> 15 mm
    assert np.isclose(awc_layer(0.30, 0.15, 0.0, 100), 15.0)


def test_awc_layer_stones_reduce_water():
    assert np.isclose(awc_layer(0.30, 0.15, 0.5, 100), 7.5)


def test_awc_layer_never_negative():
    assert awc_layer(0.10, 0.20, 0.0, 100) == 0


def test_awc_missing_stones_counts_as_none():
    assert np.isclose(awc_layer(0.30, 0.10, np.nan, 50), 10.0)


def test_drainage_classes():
    d = config.load("soil")["drainage"]
    sand = np.array([70.0, 30.0, 30.0, 20.0, np.nan])
    clay = np.array([10.0, 25.0, 40.0, 12.0, 20.0])
    assert drainage_class(sand, clay, d).tolist() == [1, 2, 3, 1, 0]


def test_soil_effect_is_gentle():
    assert 0.8 <= config.load("soil")["soil_effect"]["min_factor"] < 1.0
