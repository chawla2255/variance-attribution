"""Run the weekly close end to end: extracts -> checked fact table -> bridge -> pack.

Writes to docs/: the data-quality report, the year-to-date bridge by market, the written
commentary for every period and year to date, a waterfall chart, and dashboard.html, a single
self-contained page that drills from the headline variance to SKU level.
"""
from __future__ import annotations

import html
import json
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from fpa import etl
from fpa.commentary import money, narrative
from fpa.generate import RAW, generate
from fpa.variance import EFFECTS, LABELS, PERIOD_OF_WEEK, bridge, check, summarize, weeks_in

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
TEMPLATE = Path(__file__).resolve().parent / "dashboard_template.html"
DIMS = ["business_unit", "region", "category", "name"]


def md_to_html(md: str) -> str:
    out, in_list = [], False
    for line in md.splitlines():
        text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html.escape(line.lstrip("-# ").strip()))
        if line.startswith("- "):
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{text}</li>")
            continue
        if in_list:
            out.append("</ul>")
            in_list = False
        if line.startswith("###"):
            continue          # the dashboard shows its own title
        if text:
            out.append(f"<p>{text}</p>")
    if in_list:
        out.append("</ul>")
    return "\n".join(out)


def waterfall_png(cells, title: str, path: Path) -> None:
    t = summarize(cells).iloc[0]
    steps = [e for e in EFFECTS if abs(t[e]) > 1]
    labels = ["Budget GM", *[LABELS[e] for e in steps], "Actual GM"]
    fig, ax = plt.subplots(figsize=(10, 4.2), dpi=130)
    run = t.b_gm
    ax.bar(0, t.b_gm / 1e6, color="#8d99ae")
    for i, e in enumerate(steps, start=1):
        v = t[e]
        ax.bar(i, v / 1e6, bottom=run / 1e6, color="#2a9d8f" if v >= 0 else "#e76f51")
        ax.text(i, (run + max(v, 0)) / 1e6 + 0.04, money(v).replace("$", ""), ha="center", fontsize=8)
        run += v
    ax.bar(len(steps) + 1, t.a_gm / 1e6, color="#264653")
    for i, v in ((0, t.b_gm), (len(steps) + 1, t.a_gm)):
        ax.text(i, v / 1e6 + 0.04, f"${v / 1e6:.2f}M", ha="center", fontsize=8, fontweight="bold")
    ax.set_xticks(range(len(labels)), labels, fontsize=8)
    ax.set_ylim(min(t.a_gm, t.b_gm) / 1e6 * 0.85, max(t.a_gm, t.b_gm) / 1e6 * 1.06)
    ax.set_ylabel("gross margin, $M (axis cut)")
    ax.set_title(title, loc="left", fontsize=10)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def main() -> None:
    if not (RAW / "sales_lines.csv").exists():
        generate()
    close = etl.run()
    fact = close.fact
    DOCS.mkdir(exist_ok=True)
    close.quality.to_csv(DOCS / "data_quality.csv", index=False, float_format="%.2f")
    close.reconciliation.to_csv(DOCS / "reconciliation.csv", index=False, float_format="%.2f")

    ytd = bridge(fact)
    assert check(ytd) < 1e-6
    summarize(ytd, ["business_unit", "region"]).round(0).to_csv(DOCS / "bridge_by_market.csv")
    waterfall_png(ytd, "Meadowfield Foods (fictional), gross margin budget to actual, FY2025", DOCS / "waterfall.png")

    # Every view the dashboard offers: each period on its own, and year to date through it.
    dims = {d: sorted(fact[d].unique()) for d in DIMS}
    index = {d: {v: i for i, v in enumerate(vals)} for d, vals in dims.items()}
    views, pack = {}, []
    for p in range(1, 13):
        wk = weeks_in(p)
        for key, weeks, title in ((f"P{p}", wk, f"Period {p} (weeks {wk[0]}-{wk[-1]})"),
                                  (f"YTD{p}", weeks_in(ytd_to=p), f"Year to date, P1-P{p}")):
            cells = bridge(fact, weeks)
            cells = cells[(cells.a_units != 0) | (cells.b_units != 0)]
            md = narrative(cells, title)
            pack.append(md)
            rows = [[*(index[d][r[d]] for d in DIMS), *(round(float(r[c])) for c in
                     ("b_gm", "a_gm", "b_revenue", "a_revenue", *EFFECTS))] for _, r in cells.iterrows()]
            views[key] = {"title": title, "commentary": md_to_html(md), "rows": rows}
    (DOCS / "commentary.md").write_text("# Close commentary, FY2025 (synthetic data)\n\n"
                                        + "\n\n".join(pack[::-1]) + "\n")
    data = {
        "dims": dims, "dimLabels": ["Business unit", "Region", "Category", "SKU"],
        "effects": EFFECTS, "labels": LABELS, "views": views,
        "quality": close.quality.replace({np.nan: None}).to_dict("records"),
        "periods": int(PERIOD_OF_WEEK.max()),
    }
    page = TEMPLATE.read_text().replace("/*DATA*/null", json.dumps(data, separators=(",", ":")))
    (DOCS / "dashboard.html").write_text(page)
    # GitHub Pages serves docs/: the site root opens the dashboard.
    (DOCS / "index.html").write_text('<!doctype html><meta charset="utf-8"><title>Gross-Margin Bridge</title>'
                                     '<meta http-equiv="refresh" content="0; url=dashboard.html">'
                                     '<a href="dashboard.html">Open the dashboard</a>\n')
    (DOCS / ".nojekyll").touch()
    print(f"wrote docs/ ({len(page) / 1e3:.0f} kB dashboard)")


if __name__ == "__main__":
    main()
