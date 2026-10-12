"""Written variance commentary: for each driver, follow the money down the hierarchy.

At each level the drill keeps the group that carries most of the parent's effect (in the
direction of the effect) and stops when no single group carries at least half of it, so the
commentary says "spread across ..." instead of naming a group that does not explain much.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import pandas as pd

from .variance import EFFECTS, LABELS, summarize

DRILL_ORDER = {
    "materials": ("material", "business_unit", "category", "region"),
    "mix": ("business_unit", "category", "region", "name"),
    "fx": ("currency", "business_unit", "category"),
    "new": ("business_unit", "name", "region"),
    "discontinued": ("business_unit", "name", "region"),
}
DEFAULT_ORDER = ("business_unit", "region", "category", "name")
LEVEL_NAMES = {"business_unit": "business units", "region": "regions", "category": "categories",
               "name": "SKUs", "material": "materials", "currency": "currencies"}


def money(x: float) -> str:
    sign = "-" if x < 0 else "+"
    x = abs(x)
    if x >= 1e6:
        return f"{sign}${x / 1e6:.2f}M"
    if x >= 1e3:
        return f"{sign}${x / 1e3:.0f}k"
    return f"{sign}${x:.0f}"


@dataclass
class Step:
    level: str
    group: str
    value: float
    share: float          # of the parent's effect


def drill(cells: pd.DataFrame, effect: str, order: Sequence[str] | None = None,
          min_share: float = 0.5) -> tuple[list[Step], str | None]:
    """Path from the total down to the narrowest group that still explains most of the effect."""
    order = order or DRILL_ORDER.get(effect, DEFAULT_ORDER)
    sub, path = cells, []
    parent_total = sub[effect].sum()
    for level in order:
        by = sub.groupby(level)[effect].sum()
        if parent_total == 0 or len(by) == 0:
            break
        top = by.idxmin() if parent_total < 0 else by.idxmax()
        share = by[top] / parent_total
        if len(by) > 1 and share < min_share:
            return path, f"spread across {len(by)} {LEVEL_NAMES.get(level, level)}"
        if len(by) > 1:
            path.append(Step(level, str(top), float(by[top]), float(share)))
        sub = sub[sub[level] == top]
        parent_total = by[top]
    return path, None


def describe(cells: pd.DataFrame, effect: str) -> str:
    total = cells[effect].sum()
    path, tail = drill(cells, effect)
    parts = [f"**{LABELS[effect]} {money(total)}**"]
    for s in path:
        parts.append(f"{s.group} {money(s.value)} ({s.share:.0%})")
    text = " → ".join(parts)
    return text + (f", {tail}" if tail else "")


def margin_watch(cells: pd.DataFrame, by: Sequence[str] = ("business_unit", "category"),
                 drop_pts: float = 5.0) -> pd.DataFrame:
    """Groups whose gross-margin percentage fell by more than `drop_pts` points against budget."""
    s = summarize(cells, by)
    s = s[s.b_revenue > 0]
    out = pd.DataFrame({"budget GM %": 100 * s.b_gm / s.b_revenue, "actual GM %": 100 * s.a_gm / s.a_revenue})
    out["change, pts"] = out["actual GM %"] - out["budget GM %"]
    return out[out["change, pts"] < -drop_pts].sort_values("change, pts")


def narrative(cells: pd.DataFrame, title: str, materiality: float = 0.005) -> str:
    """Markdown commentary: the headline, then every material driver with its drill path."""
    t = summarize(cells).iloc[0]
    lines = [f"### {title}", "",
             f"Gross margin **${t.a_gm / 1e6:.2f}M** against a budget of ${t.b_gm / 1e6:.2f}M: "
             f"**{money(t.variance)}** ({t.variance / t.b_gm:+.1%}). Margin "
             f"{100 * t.a_gm / t.a_revenue:.1f}% of revenue against {100 * t.b_gm / t.b_revenue:.1f}% budgeted.", ""]
    floor = materiality * abs(t.b_gm)
    for effect in sorted(EFFECTS, key=lambda e: -abs(t[e])):
        if abs(t[effect]) >= floor:
            lines.append(f"- {describe(cells, effect)}")
    watch = margin_watch(cells)
    if len(watch):
        lines += ["", "Margin watch (down more than 5 points):"]
        for (bu, cat), r in watch.iterrows():
            lines.append(f"- {bu} {cat}: {r['actual GM %']:.1f}% against {r['budget GM %']:.1f}% budget")
    return "\n".join(lines)
