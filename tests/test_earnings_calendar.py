import datetime as dt

import openpyxl
import pytest

from earnings_calendar import loader
from earnings_calendar.formatting import amt, yoy
from earnings_calendar.panel import block, split_blocks
from earnings_calendar.sheet_requests import default_note, month_batches


def test_amt():
    assert amt(None) == "-"
    assert amt(12345) == "1.23조"
    assert amt(1234.4) == "1,234억"
    assert amt(3.44) == "3.4억"


@pytest.mark.parametrize("cur,prev,text", [
    (120, 100, "+20.0%"),
    (80, 100, "-20.0%"),
    (50, -20, "+350.0%, 흑전"),
    (-20, 50, "-140.0%, 적전"),
    (-10, -20, "+50.0%, 적자축소"),
    (-30, -20, "-50.0%, 적자확대"),
    (10, None, "-"),
])
def test_yoy(cur, prev, text):
    assert yoy(cur, prev)[0] == text


def _wide(path, basis="IFRS(연결)"):
    wb = openpyxl.Workbook()
    ws = wb.active
    hdr = ["2026 Q3(E)", "2026 Q2", "2026 Q1", "2025 Q4", "2025 Q3", "2025 Q2"]
    ws.append([None, "항목", None, None, *hdr])
    ws.append([None, None, None, "주재무제표", *[basis] * len(hdr)])
    ws.append([None, "매출액", None, None, 1200, 1100, 1000, 900, 1000, 950])
    ws.append([None, "영업이익", None, None, 120, 100, -10, 50, 80, 70])
    ws.append([None, "당기순이익(지배)", None, None, 90, 80, -20, 30, 60, 50])
    wb.save(path)


def _compact(path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["구분", "2025 Y", "2026 Y(E)", "2025 Q4", "2026 Q1", "2026 Q2"])
    ws.append([None, *["IFRS(연결)"] * 5])
    ws.append(["매출액", 651, 693, 184, 169, 156])
    ws.append(["영업이익", -124, -105, -52, -45, -16])
    ws.append(["순이익(지배)", -57, -74, -58, -33, -18])
    wb.save(path)


def test_load_wide(tmp_path):
    p = tmp_path / "테스트.xlsx"
    _wide(p)
    fin = loader.load(p)
    assert fin.name == "테스트"
    assert fin.est == {(2026, 3)}
    assert fin.get("rev", (2026, 2)) == 1100
    assert fin.get("np", (2025, 3)) == 60


def test_load_compact_scales_and_annual(tmp_path):
    p = tmp_path / "바이오.xlsx"
    _compact(p)
    fin = loader.load(p)
    assert fin.get("rev", (2026, 2)) == 1560          # 10억 -> 억
    assert fin.annual_est == {2026}
    text, _ = block([(fin, "EA002C", None)], 1, False)
    assert "2026년(E) 6,930억(+6.5%)" in text


def test_standalone_note(tmp_path):
    p = tmp_path / "별도.xlsx"
    _wide(p, basis="IFRS(별도)")
    text, _ = block([(loader.load(p), "000000", None)], 1, False)
    assert text.endswith("* IFRS 별도 기준")


def test_block_lines_and_runs(tmp_path):
    p = tmp_path / "가.xlsx"
    _wide(p)
    fin = loader.load(p)
    text, runs = block([(fin, "0054A6", None)], 1, True)
    assert "1. 가 실적 추이" in text
    assert "2026.3Q(E) 1,200억(+20.0%)/ 120억(+50.0%)/ 90억(+50.0%)" in text
    assert "2026.1Q" in text and "흑전" not in text.split("2026.1Q")[1].split("\n")[0]
    end = len(text.encode("utf-16-le")) // 2
    assert all(r["startIndex"] < end for r in runs)


def test_split_blocks_respects_limit(tmp_path):
    p = tmp_path / "가.xlsx"
    _wide(p)
    fin = loader.load(p)
    entries = [(fin, "000000", None)] * 6
    blocks = split_blocks(entries, 20)
    assert sum(len(b[0]) for b in blocks) == 6
    for es, start, hdr in blocks:
        assert block(es, start, hdr)[0].count("\n") + 1 <= 20 or len(es) == 1


def test_month_batches_new_tab(tmp_path):
    p = tmp_path / "가.xlsx"
    _wide(p)
    fin = loader.load(p)
    d = dt.date(2027, 1, 20)
    events = {d: [("가", "0054A6", default_note(d))]}
    batches, info = month_batches(2027, 1, 202701, False, events, [(fin, "0054A6", None)])
    assert batches[0][0]["addSheet"]["properties"]["title"] == "2027.01"
    assert default_note(d) == "4분기 실적 발표 예정"
    assert len(batches) == 1 + len(info["blocks"])
