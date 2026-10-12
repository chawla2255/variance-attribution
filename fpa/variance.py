"""Gross-margin bridge from budget to actual: volume, mix, price, cost, FX and new products.

Each cell is one SKU in one region. For a continuing cell, with A = actual, B = budget, u = units:

    price       = A_u x (actual net price at budget FX - budget net price)
    fx          = actual revenue - actual revenue at budget FX
    materials   = -A_u x (actual material cost per unit - budget)
    conversion  = -A_u x (actual conversion cost per unit - budget)
    volume+mix  = (A_u - B_u) x budget margin per unit

Volume and mix are split on kilograms, the common unit across pack sizes, within a parent
group P (by default the market: business unit x region), using the cell's budget share
s = B_kg / B_kg(P):

    volume      = (A_kg(P) - B_kg(P)) x s x budget margin per kg
    mix         = (A_kg - A_kg(P) x s) x budget margin per kg

so volume is "the market sold more or fewer tonnes, at budget mix" and mix is "it sold a
different blend of SKUs". Cells with no budget go to `new`; cells with budget but no
sales go to `discontinued`. The effects add up exactly to actual minus budget gross margin, in
every cell, so they also add up for any grouping: business unit, region, category or SKU.
"""
from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd

KEYS = ["business_unit", "region", "category", "material", "sku", "name", "currency"]
EFFECTS = ["volume", "mix", "price", "materials", "conversion", "fx", "new", "discontinued"]
LABELS = {"volume": "Volume", "mix": "Mix", "price": "Price", "materials": "Materials cost",
          "conversion": "Conversion cost", "fx": "FX", "new": "New products", "discontinued": "Discontinued"}
NUMERIC = ["a_units", "a_kg", "a_revenue", "a_revenue_budget_fx", "a_material", "a_conversion",
           "b_units", "b_kg", "b_revenue", "b_material", "b_conversion"]

# 4-4-5 fiscal calendar: 12 periods, 13-week quarters.
PERIOD_WEEKS = [4, 4, 5] * 4
PERIOD_OF_WEEK = np.repeat(np.arange(1, 13), PERIOD_WEEKS)


def weeks_in(period: int | None = None, ytd_to: int | None = None) -> np.ndarray:
    """Weeks of one fiscal period, or year to date through a period."""
    weeks = np.arange(1, 53)
    if period is not None:
        return weeks[PERIOD_OF_WEEK == period]
    return weeks[PERIOD_OF_WEEK <= (ytd_to or 12)]


def bridge(fact: pd.DataFrame, weeks: Sequence[int] | None = None,
           mix_within: Sequence[str] = ("business_unit", "region")) -> pd.DataFrame:
    """Per-cell bridge for the chosen weeks. `mix_within=()` measures mix across the whole company."""
    f = fact if weeks is None else fact[fact.week.isin(list(weeks))]
    g = f.groupby(KEYS, as_index=False)[NUMERIC].sum()
    g["a_gm"] = g.a_revenue - g.a_material - g.a_conversion
    g["b_gm"] = g.b_revenue - g.b_material - g.b_conversion
    g["variance"] = g.a_gm - g.b_gm

    new = (g.b_units <= 0) & (g.a_units > 0)
    gone = (g.a_units <= 0) & (g.b_units > 0)
    cont = (g.a_units > 0) & (g.b_units > 0)
    for e in EFFECTS:
        g[e] = 0.0
    g.loc[new, "new"] = g.variance[new]
    g.loc[gone, "discontinued"] = g.variance[gone]

    c = g[cont]
    per_unit = lambda col: c[col] / c.b_units
    g.loc[cont, "price"] = c.a_revenue_budget_fx - c.a_units * per_unit("b_revenue")
    g.loc[cont, "fx"] = c.a_revenue - c.a_revenue_budget_fx
    g.loc[cont, "materials"] = -(c.a_material - c.a_units * per_unit("b_material"))
    g.loc[cont, "conversion"] = -(c.a_conversion - c.a_units * per_unit("b_conversion"))

    margin_kg = c.b_gm / c.b_kg
    parent = list(mix_within)
    if parent:
        a_tot = c.groupby(parent).a_kg.transform("sum")
        b_tot = c.groupby(parent).b_kg.transform("sum")
    else:
        a_tot, b_tot = pd.Series(c.a_kg.sum(), c.index), pd.Series(c.b_kg.sum(), c.index)
    share = c.b_kg / b_tot
    g.loc[cont, "volume"] = (a_tot - b_tot) * share * margin_kg
    g.loc[cont, "mix"] = (c.a_kg - a_tot * share) * margin_kg
    return g


def summarize(cells: pd.DataFrame, by: Sequence[str] = ()) -> pd.DataFrame:
    """Budget GM, each effect and actual GM, totalled by any grouping (or overall)."""
    cols = ["b_gm", *EFFECTS, "a_gm", "variance", "b_revenue", "a_revenue", "b_kg", "a_kg"]
    if not by:
        return cells[cols].sum().to_frame("Total").T
    return cells.groupby(list(by))[cols].sum().sort_values("variance")


def check(cells: pd.DataFrame, tol: float = 1e-6) -> float:
    """Largest gap between a cell's variance and the sum of its effects (should be ~0)."""
    return float((cells.variance - cells[EFFECTS].sum(axis=1)).abs().max()) if len(cells) else 0.0
