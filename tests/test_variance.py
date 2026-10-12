import numpy as np
import pandas as pd
import pytest

from fpa.variance import EFFECTS, PERIOD_OF_WEEK, bridge, check, summarize, weeks_in


def test_four_four_five_calendar():
    assert len(PERIOD_OF_WEEK) == 52
    assert list(weeks_in(3)) == list(range(9, 14))
    assert len(weeks_in(ytd_to=12)) == 52 and len(weeks_in(ytd_to=6)) == 26


@pytest.mark.parametrize("mix_within", [(), ("business_unit",), ("business_unit", "region")])
@pytest.mark.parametrize("weeks", [None, weeks_in(1), weeks_in(ytd_to=7)])
def test_effects_add_up_exactly_in_every_cell_and_group(close, weeks, mix_within):
    cells = bridge(close.fact, weeks, mix_within)
    assert check(cells) < 1e-6
    for by in (["business_unit"], ["region"], ["category", "material"]):
        s = summarize(cells, by)
        assert np.allclose(s.b_gm + s[EFFECTS].sum(axis=1), s.a_gm)


def test_hand_worked_example():
    """Two SKUs in one market; budget sells 100 + 100 kg, actual sells 150 + 30 kg."""
    base = dict(region="R", currency="USD", business_unit="B", material="m", name="n", week=1,
                a_material=0.0, a_conversion=0.0, b_material=0.0, b_conversion=0.0)
    rows = [
        dict(base, sku="cheap", category="c", a_units=150, a_kg=150, b_units=100, b_kg=100,
             b_revenue=100.0, a_revenue_budget_fx=150 * 0.9, a_revenue=150 * 0.9),   # margin 1/kg, price -10%
        dict(base, sku="rich", category="c", a_units=30, a_kg=30, b_units=100, b_kg=100,
             b_revenue=300.0, a_revenue_budget_fx=90.0, a_revenue=90.0),               # margin 3/kg, price flat
    ]
    cells = bridge(pd.DataFrame(rows)).set_index("sku")
    # total kg 180 vs 200: volume = -20 x 0.5 x margin; mix = (actual kg - 180 x 0.5) x margin
    assert np.isclose(cells.loc["cheap", "volume"], -10.0) and np.isclose(cells.loc["rich", "volume"], -30.0)
    assert np.isclose(cells.loc["cheap", "mix"], 60.0) and np.isclose(cells.loc["rich", "mix"], -180.0)
    assert np.isclose(cells.loc["cheap", "price"], -15.0) and np.isclose(cells.loc["rich", "price"], 0.0)
    assert np.isclose(cells.variance.sum(), (135 + 90) - (100 + 300))


@pytest.fixture(scope="module")
def ytd(close):
    return bridge(close.fact)


def _share_of_negative(s, col, key):
    neg = s[col].clip(upper=0)
    return neg.loc[key] / neg.sum()


def test_finds_the_price_cut(ytd, close):
    s = summarize(ytd, ["business_unit", "region", "category"])
    assert s.price.idxmin() == ("Retail", "South", "Premium")
    assert _share_of_negative(s, "price", ("Retail", "South", "Premium")) > 0.9
    before = summarize(bridge(close.fact, range(1, 14)), ["business_unit", "region", "category"])
    assert abs(before.loc[("Retail", "South", "Premium"), "price"]) < 2_000      # no false alarm


def test_finds_the_lost_contract(ytd):
    s = summarize(ytd, ["business_unit", "region"])
    assert s.volume.idxmin() == ("Food Service", "West")
    assert _share_of_negative(s, "volume", ("Food Service", "West")) > 0.95


def test_finds_the_trade_down_as_mix(ytd):
    s = summarize(ytd, ["business_unit", "category"])
    assert s.loc[("Retail", "Premium"), "mix"] < -100_000 < 0 < s.loc[("Retail", "Value"), "mix"]
    assert summarize(ytd, ["business_unit"]).mix.idxmin() == "Retail"


def test_cost_spike_hits_long_grain_only(ytd):
    s = summarize(ytd, ["material"])
    assert s.loc["Long-grain paddy", "materials"] < -900_000
    assert abs(s.loc["Basmati paddy", "materials"]) < 10      # cent rounding on invoice lines


def test_fx_loss_is_the_euro(ytd):
    s = summarize(ytd, ["region"])
    assert s.fx.idxmin() == "Eurozone" and s.loc["Eurozone", "fx"] < -100_000
    assert (s.drop(["Eurozone", "UK"]).fx == 0).all()


def test_launch_is_new_products(ytd):
    launched = ytd[ytd.sku == "RC-MP"]
    assert np.isclose(ytd.new.sum(), launched.a_gm.sum()) and launched.b_gm.sum() == 0
