from fpa.commentary import drill, margin_watch, money, narrative
from fpa.variance import bridge


def test_money_format():
    assert money(-1_148_420) == "-$1.15M" and money(417_541) == "+$418k" and money(-63) == "-$63"


def test_drill_walks_down_to_the_planted_price_cut(close):
    path, tail = drill(bridge(close.fact), "price")
    assert [s.group for s in path] == ["Retail", "South", "Premium"]
    assert all(s.share > 0.9 for s in path) and tail.startswith("spread across")


def test_drill_stops_when_nothing_dominates(close):
    path, tail = drill(bridge(close.fact), "materials")
    assert path[0].group == "Long-grain paddy" and tail is not None


def test_mix_drills_to_premium_and_margin_watch_flags_value(close):
    cells = bridge(close.fact)
    path, _ = drill(cells, "mix")
    assert [s.group for s in path[:2]] == ["Retail", "Premium"]
    watch = margin_watch(cells)
    assert ("Food Service", "Value") in watch.index
    assert "Gross margin" in narrative(cells, "YTD")
