import numpy as np
import pandas as pd


def test_clean_fact_reconciles_to_raw_extract(close):
    q = close.quality.set_index("check")
    r = close.reconciliation.iloc[0]
    dropped = q.loc["re-sent duplicate lines (dropped)", "net_local"]
    quarantined = q.loc["unknown SKU codes (quarantined)", "net_local"]
    assert np.isclose(r.raw_net_local - dropped - quarantined, r.fact_net_local, atol=0.01)


def test_quality_checks_find_the_planted_problems(close):
    q = close.quality.set_index("check")
    assert q.loc["re-sent duplicate lines (dropped)", "lines"] == 25
    assert q.loc["unknown SKU codes (quarantined)", "lines"] == 3
    assert q.loc["unknown SKU codes (quarantined)", "detail"] == "RC1K"
    assert q.loc["credit notes (netted)", "lines"] == 60
    assert q.loc["markets without an FX rate", "lines"] == 0
    assert q.loc["sales with no budget (new products)", "detail"] == "RC-MP"


def test_budget_carries_through_unchanged(raw, close):
    b = pd.read_csv(raw / "budget.csv")
    assert close.fact.b_units.sum() == b.units.sum()
    assert np.isclose(close.fact.b_material.sum(), (b.units * b.material_cost_per_unit_usd).sum())
    # USD markets: budget revenue is units x price; foreign markets are converted at the budget rate
    usd = close.fact[close.fact.currency == "USD"]
    assert np.isclose(usd.b_revenue.sum(),
                      (b.units * b.net_price_local)[~b.region.isin(["Eurozone", "UK"])].sum())


def test_fact_has_one_row_per_week_sku_region(close):
    assert not close.fact.duplicated(["week", "sku", "region"]).any()
