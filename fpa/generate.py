"""Synthetic ERP extracts for a fictional packaged-rice company, Meadowfield Foods.

Nothing here is real company data. The generator writes the CSVs a finance team would pull
from its ERP each week: a SKU master, a market list, a weekly budget, weekly sales lines
(with the usual mess: duplicated lines, a mistyped SKU code, credit notes) and FX rates.

Actuals are the budget plus noise plus six planted business events, so the attribution engine
can be checked against a known answer:

    PRICE      Retail South Premium: 6% deeper promotional discount from week 14
    VOLUME     Food Service West: a lost contract cuts volume 35% from week 20
    MIX        Retail, all regions: shoppers trade down from week 27 (Premium -12%, Value +18%)
    COST       Long-grain paddy costs 15% more from week 26 (basmati unchanged)
    FX         The euro weakens about 6% against the budget rate over the year
    NEW        A 250 g microwave pouch launches in Retail from week 30, with no budget
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

WEEKS = 52
YEAR = 2025
RAW = Path(__file__).resolve().parent.parent / "data" / "raw"

BUDGET_FX = {"USD": 1.0, "EUR": 1.08, "GBP": 1.27}          # USD per unit of currency
MATERIAL_PRICE = {"Basmati paddy": 1.10, "Long-grain paddy": 0.60}   # budget USD per kg

MARKETS = [  # (business unit, region, currency, demand weight)
    ("Retail", "North", "USD", 1.00), ("Retail", "South", "USD", 0.85),
    ("Retail", "East", "USD", 0.95), ("Retail", "West", "USD", 0.75),
    ("Food Service", "North", "USD", 0.80), ("Food Service", "South", "USD", 0.60),
    ("Food Service", "East", "USD", 0.70), ("Food Service", "West", "USD", 0.90),
    ("Export", "Eurozone", "EUR", 1.00), ("Export", "UK", "GBP", 0.70),
]

# (sku, name, business unit, category, kg per unit, budget net price per kg in local currency,
#  conversion cost USD per kg, base weekly units per market)
SKUS = [
    ("RP-1K", "Royal Basmati 1 kg", "Retail", "Premium", 1.0, 3.40, 0.55, 2600),
    ("RP-2K", "Royal Basmati 2 kg", "Retail", "Premium", 2.0, 3.15, 0.45, 1500),
    ("RP-5K", "Royal Basmati 5 kg", "Retail", "Premium", 5.0, 2.90, 0.35, 600),
    ("RP-BR", "Brown Basmati 1 kg", "Retail", "Premium", 1.0, 3.60, 0.60, 900),
    ("RC-1K", "Everyday Long Grain 1 kg", "Retail", "Classic", 1.0, 2.10, 0.45, 3800),
    ("RC-2K", "Everyday Long Grain 2 kg", "Retail", "Classic", 2.0, 1.95, 0.38, 2100),
    ("RC-5K", "Everyday Long Grain 5 kg", "Retail", "Classic", 5.0, 1.80, 0.30, 900),
    ("RC-PB", "Parboiled 1 kg", "Retail", "Classic", 1.0, 2.20, 0.48, 1200),
    ("RV-1K", "Value Rice 1 kg", "Retail", "Value", 1.0, 1.45, 0.35, 3000),
    ("RV-2K", "Value Rice 2 kg", "Retail", "Value", 2.0, 1.35, 0.30, 1900),
    ("RV-5K", "Value Rice 5 kg", "Retail", "Value", 5.0, 1.25, 0.25, 1000),
    ("RV-10", "Value Rice 10 kg", "Retail", "Value", 10.0, 1.18, 0.22, 400),
    ("FP-10", "Chef's Basmati 10 kg", "Food Service", "Premium", 10.0, 2.70, 0.25, 520),
    ("FP-25", "Chef's Basmati 25 kg", "Food Service", "Premium", 25.0, 2.55, 0.20, 230),
    ("FC-10", "Kitchen Long Grain 10 kg", "Food Service", "Classic", 10.0, 1.65, 0.20, 900),
    ("FC-25", "Kitchen Long Grain 25 kg", "Food Service", "Classic", 25.0, 1.55, 0.16, 520),
    ("FC-PB", "Kitchen Parboiled 25 kg", "Food Service", "Classic", 25.0, 1.60, 0.17, 300),
    ("FV-10", "Catering Value 10 kg", "Food Service", "Value", 10.0, 1.15, 0.18, 700),
    ("FV-25", "Catering Value 25 kg", "Food Service", "Value", 25.0, 1.08, 0.14, 450),
    ("FV-50", "Catering Value 50 kg", "Food Service", "Value", 50.0, 1.02, 0.12, 150),
    ("EP-1K", "Royal Basmati Export 1 kg", "Export", "Premium", 1.0, 3.30, 0.60, 2400),
    ("EP-5K", "Royal Basmati Export 5 kg", "Export", "Premium", 5.0, 2.85, 0.42, 700),
    ("EP-BR", "Brown Basmati Export 1 kg", "Export", "Premium", 1.0, 3.55, 0.62, 800),
    ("EP-10", "Basmati Export 10 kg", "Export", "Premium", 10.0, 2.60, 0.30, 300),
    ("EC-1K", "Long Grain Export 1 kg", "Export", "Classic", 1.0, 2.05, 0.50, 1400),
    ("EC-5K", "Long Grain Export 5 kg", "Export", "Classic", 5.0, 1.75, 0.36, 500),
]
NEW_SKU = ("RC-MP", "Microwave Pouch 250 g", "Retail", "Classic", 0.25, 6.20, 1.40, 5200)
LAUNCH_WEEK = 30

# Export local prices are per kg in the market's currency; GBP list prices are set lower.
GBP_PRICE_FACTOR = 0.86
YIELD = 1.45   # kg of paddy per kg of milled, packed rice


def material_for(category: str) -> str:
    return "Basmati paddy" if category == "Premium" else "Long-grain paddy"


def sku_master() -> pd.DataFrame:
    rows = [dict(sku=s[0], name=s[1], business_unit=s[2], category=s[3], kg_per_unit=s[4],
                 material=material_for(s[3]), material_kg_per_unit=round(s[4] * YIELD, 4))
            for s in SKUS + [NEW_SKU]]
    return pd.DataFrame(rows)


def markets() -> pd.DataFrame:
    return pd.DataFrame(MARKETS, columns=["business_unit", "region", "currency", "weight"])


def _seasonality(week: np.ndarray) -> np.ndarray:
    """A mild summer dip and a strong festive Q4."""
    return 1 + 0.06 * np.sin(2 * np.pi * (week - 10) / 52) + 0.15 * (week >= 44)


def _fx_paths(rng: np.random.Generator) -> pd.DataFrame:
    week = np.arange(1, WEEKS + 1)
    eur = BUDGET_FX["EUR"] * (1 - 0.06 * np.clip((week - 5) / 30, 0, 1)) * np.exp(np.cumsum(rng.normal(0, 0.004, WEEKS)))
    gbp = BUDGET_FX["GBP"] * np.exp(np.cumsum(rng.normal(0, 0.004, WEEKS)))
    rows = [(w, c, BUDGET_FX[c], r) for c, path in (("EUR", eur), ("GBP", gbp)) for w, r in zip(week, path)]
    rows += [(w, "USD", 1.0, 1.0) for w in week]
    return pd.DataFrame(rows, columns=["week", "currency", "budget_rate", "actual_rate"]).round({"actual_rate": 5})


def generate(seed: int = 7, out: Path = RAW) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    sku, mkt = sku_master(), markets()
    week = np.arange(1, WEEKS + 1)
    budget_rows, actual_rows = [], []
    for s in SKUS + [NEW_SKU]:
        code, _, bu, cat, kg, price_kg, conv_kg, base = s
        for m in mkt[mkt.business_unit == bu].itertuples():
            local_price = price_kg * kg * (GBP_PRICE_FACTOR if m.currency == "GBP" else 1.0)
            mat_cost = kg * YIELD * MATERIAL_PRICE[material_for(cat)]
            conv_cost = conv_kg * kg
            units = base * m.weight * _seasonality(week)
            is_new = code == NEW_SKU[0]
            if not is_new:
                for w, u in zip(week, units):
                    budget_rows.append((w, code, m.region, round(u), round(local_price, 4),
                                        round(mat_cost, 4), round(conv_cost, 4)))
            # ---- actuals: budget assumptions, planted events, noise
            a_units = units * np.exp(rng.normal(0, 0.04, WEEKS))
            discount = np.full(WEEKS, 0.08)                     # list price = net / (1 - 8%)
            mat_price = np.full(WEEKS, MATERIAL_PRICE[material_for(cat)])
            if bu == "Retail" and m.region == "South" and cat == "Premium":
                discount = np.where(week >= 14, 0.08 + 0.06, discount)
            if bu == "Food Service" and m.region == "West":
                a_units = np.where(week >= 20, a_units * 0.65, a_units)
            if bu == "Retail" and cat == "Premium":
                a_units = np.where(week >= 27, a_units * 0.88, a_units)
            if bu == "Retail" and cat == "Value":
                a_units = np.where(week >= 27, a_units * 1.18, a_units)
            if material_for(cat) == "Long-grain paddy":
                mat_price = np.where(week >= 26, mat_price * 1.15, mat_price)
            if is_new:
                a_units = np.where(week >= LAUNCH_WEEK, a_units, 0.0)
            list_price = local_price / (1 - 0.08) * np.exp(rng.normal(0, 0.004, WEEKS))
            for i, w in enumerate(week):
                u = int(round(a_units[i]))
                if u <= 0:
                    continue
                gross = u * list_price[i]
                actual_rows.append(dict(
                    week=w, sku=code, region=m.region, units=u,
                    gross_sales_local=round(gross, 2), discounts_local=round(gross * discount[i], 2),
                    material_cost_usd=round(u * kg * YIELD * mat_price[i], 2),
                    conversion_cost_usd=round(u * conv_cost * np.exp(rng.normal(0, 0.02)), 2)))
    actuals = pd.DataFrame(actual_rows)
    actuals = _add_mess(actuals, rng)
    budget = pd.DataFrame(budget_rows, columns=["week", "sku", "region", "units", "net_price_local",
                                                "material_cost_per_unit_usd", "conversion_cost_per_unit_usd"])
    tables = {"sku_master": sku, "markets": mkt.drop(columns="weight"), "budget": budget,
              "sales_lines": actuals, "fx_rates": _fx_paths(rng)}
    out.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        df.to_csv(out / f"{name}.csv", index=False)
    return tables


def _add_mess(lines: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """What real extracts look like: credit notes, re-sent lines and a typo."""
    lines = lines.copy()
    lines.insert(0, "doc_id", [f"INV{100000 + i}" for i in range(len(lines))])
    # Credit notes: returns booked as negative lines against an earlier invoice.
    idx = rng.choice(len(lines), 60, replace=False)
    credits = lines.iloc[idx].copy()
    share = rng.uniform(0.02, 0.10, len(credits))
    credits["units"] = -np.maximum(1, np.round(credits["units"] * share)).astype(int)
    for col in ("gross_sales_local", "discounts_local", "material_cost_usd", "conversion_cost_usd"):
        credits[col] = (lines.iloc[idx][col].to_numpy() * credits["units"].to_numpy()
                        / lines.iloc[idx]["units"].to_numpy()).round(2)
    credits["doc_id"] = [f"CN{200000 + i}" for i in range(len(credits))]
    # Interface re-sent 25 lines, and someone keyed 'RC1K' instead of 'RC-1K' on 3 lines.
    dupes = lines.iloc[rng.choice(len(lines), 25, replace=False)]
    typo = lines.index[lines.sku == "RC-1K"][:3]
    lines.loc[typo, "sku"] = "RC1K"
    return pd.concat([lines, credits, dupes], ignore_index=True).sort_values(["week", "doc_id"], ignore_index=True)


if __name__ == "__main__":
    t = generate()
    print({k: len(v) for k, v in t.items()})
