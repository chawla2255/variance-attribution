"""Weekly close ETL: raw ERP extracts -> checked, reconciled fact table (DuckDB SQL).

The fact table has one row per week x SKU x region with actual and budget units, revenue,
material and conversion cost in USD. Data-quality checks run first and are reported, never
silently fixed: exact re-sent lines are dropped, lines with unknown SKU codes are quarantined
with their value, credit notes are netted, and the cleaned totals are reconciled to the raw ones.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import duckdb
import pandas as pd

from .generate import RAW

FACT_SQL = """
CREATE OR REPLACE TABLE fact AS
WITH lines AS (SELECT DISTINCT * FROM sales_lines),
clean AS (SELECT l.* FROM lines l SEMI JOIN sku_master s ON l.sku = s.sku),
act AS (
    SELECT week, sku, region,
           SUM(units)                                  AS a_units,
           SUM(gross_sales_local - discounts_local)    AS a_net_local,
           SUM(material_cost_usd)                      AS a_material,
           SUM(conversion_cost_usd)                    AS a_conversion
    FROM clean GROUP BY ALL
),
bud AS (
    SELECT week, sku, region,
           units                                       AS b_units,
           units * net_price_local                     AS b_net_local,
           units * material_cost_per_unit_usd          AS b_material,
           units * conversion_cost_per_unit_usd        AS b_conversion
    FROM budget
)
SELECT week, sku, region, s.business_unit, s.category, s.name, s.material, m.currency,
       s.kg_per_unit,
       COALESCE(a_units, 0)                          AS a_units,
       COALESCE(a_units, 0) * s.kg_per_unit          AS a_kg,
       COALESCE(a_net_local, 0)                      AS a_net_local,
       COALESCE(a_net_local, 0) * fx.actual_rate     AS a_revenue,
       COALESCE(a_net_local, 0) * fx.budget_rate     AS a_revenue_budget_fx,
       COALESCE(a_material, 0)                       AS a_material,
       COALESCE(a_conversion, 0)                     AS a_conversion,
       COALESCE(b_units, 0)                          AS b_units,
       COALESCE(b_units, 0) * s.kg_per_unit          AS b_kg,
       COALESCE(b_net_local, 0) * fx.budget_rate     AS b_revenue,
       COALESCE(b_material, 0)                       AS b_material,
       COALESCE(b_conversion, 0)                     AS b_conversion
FROM act FULL OUTER JOIN bud USING (week, sku, region)
JOIN sku_master s USING (sku)
JOIN markets m ON m.business_unit = s.business_unit AND m.region = region
JOIN fx_rates fx ON fx.week = week AND fx.currency = m.currency
ORDER BY week, sku, region
"""

# Raw lines in USD at the week's actual rate. Currency comes from the region (each region trades
# in one currency), so even lines with an unknown SKU code can be valued.
LINES_USD_SQL = """
CREATE OR REPLACE VIEW lines_usd AS
SELECT l.*, l.gross_sales_local - l.discounts_local AS net_local,
       (l.gross_sales_local - l.discounts_local) * fx.actual_rate AS net_usd, c.currency
FROM sales_lines l
JOIN (SELECT DISTINCT region, currency FROM markets) c USING (region)
JOIN fx_rates fx ON fx.week = l.week AND fx.currency = c.currency
"""

CHECKS = {
    "re-sent duplicate lines (dropped)": """
        SELECT COUNT(*) - (SELECT COUNT(*) FROM (SELECT DISTINCT * FROM lines_usd)) AS lines,
               SUM(net_usd) - (SELECT SUM(net_usd) FROM (SELECT DISTINCT * FROM lines_usd)) AS net_usd
        FROM lines_usd""",
    "unknown SKU codes (quarantined)": """
        SELECT COUNT(*) AS lines, SUM(net_usd) AS net_usd, STRING_AGG(DISTINCT sku, ', ') AS detail
        FROM (SELECT DISTINCT * FROM lines_usd) l ANTI JOIN sku_master s ON l.sku = s.sku""",
    "credit notes (netted)": """
        SELECT COUNT(*) AS lines, SUM(net_usd) AS net_usd
        FROM (SELECT DISTINCT * FROM lines_usd) WHERE units < 0""",
    "markets without an FX rate": """
        SELECT COUNT(*) AS lines FROM (SELECT DISTINCT b.week, m.currency FROM budget b
            JOIN sku_master s USING (sku) JOIN markets m ON m.business_unit = s.business_unit AND m.region = b.region)
            ANTI JOIN fx_rates USING (week, currency)""",
    "sales to a region the SKU is not sold in": """
        SELECT COUNT(*) AS lines FROM (SELECT DISTINCT * FROM sales_lines) l JOIN sku_master s USING (sku)
            ANTI JOIN markets m ON m.business_unit = s.business_unit AND m.region = l.region""",
    "budget lines with no sales": """
        SELECT COUNT(*) AS lines FROM budget b ANTI JOIN sales_lines l USING (week, sku, region)""",
    "sales with no budget (new products)": """
        SELECT COUNT(*) AS lines, SUM(net_usd) AS net_usd, STRING_AGG(DISTINCT sku, ', ') AS detail
        FROM (SELECT DISTINCT * FROM lines_usd) l SEMI JOIN sku_master s ON l.sku = s.sku
        ANTI JOIN budget b USING (week, sku, region)""",
}


@dataclass
class Close:
    fact: pd.DataFrame
    quality: pd.DataFrame
    reconciliation: pd.DataFrame


def run(raw: Path = RAW) -> Close:
    con = duckdb.connect()
    for name in ("sku_master", "markets", "budget", "sales_lines", "fx_rates"):
        con.execute(f"CREATE TABLE {name} AS SELECT * FROM read_csv_auto('{raw / (name + '.csv')}')")
    con.execute(LINES_USD_SQL)
    quality = pd.DataFrame([
        {"check": name, **con.execute(sql).df().iloc[0].to_dict()} for name, sql in CHECKS.items()
    ]).reindex(columns=["check", "lines", "net_usd", "detail"])
    con.execute(FACT_SQL)
    fact = con.execute("SELECT * FROM fact").df()
    # Per currency: raw lines = clean fact + dropped duplicates + quarantined lines.
    reconciliation = con.execute("""
        WITH raw AS (SELECT currency, SUM(net_local) AS raw_net_local, SUM(units) AS raw_units
                     FROM lines_usd GROUP BY currency),
        dedup AS (SELECT currency, SUM(net_local) AS dedup_net_local FROM (SELECT DISTINCT * FROM lines_usd) GROUP BY currency),
        quarantined AS (SELECT currency, SUM(net_local) AS quarantined_net_local
                        FROM (SELECT DISTINCT * FROM lines_usd) l ANTI JOIN sku_master s ON l.sku = s.sku GROUP BY currency),
        clean AS (SELECT currency, SUM(a_net_local) AS fact_net_local FROM fact GROUP BY currency)
        SELECT currency, raw_net_local, raw_net_local - dedup_net_local AS duplicates_net_local,
               COALESCE(quarantined_net_local, 0) AS quarantined_net_local, fact_net_local
        FROM raw JOIN dedup USING (currency) JOIN clean USING (currency)
        LEFT JOIN quarantined USING (currency) ORDER BY currency
    """).df()
    con.close()
    return Close(fact, quality, reconciliation)
