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


# ---- 드라이브 폴더 입력 ----
from earnings_calendar import drive_input as di
from earnings_calendar.cli import main as cli_main

COMPACT_TXT = ("Sheet1 구분,2025 Y,2026 Y(E),2025 Q4,2026 Q1,2026 Q2 ,IFRS(연결),IFRS(연결),IFRS(연결),IFRS(연결),IFRS(연결) "
               "매출액,651,693,184,169,156 성장률,1,2,3,4,5 영업이익,-124,-105,-52,-45,-16 "
               "순이익(지배),-57,-74,-58,-33,-18 EPS(지배),\"-2,436\",-169,-37,\"-2,123\",161 Free Cash Flow,-,-,1,2,3")
WIDE_TXT = ("Sheet1 ,항목,,,2026 Q3(E),2026 Q2,2025 Q3,2025 Q2 ,,,3개월 결산,9/30/2026,6/30/2026,9/30/2025,6/30/2025 "
            ",,,주재무제표,IFRS(별도),IFRS(별도),IFRS(별도),IFRS(별도) ,매출액,,,\"1,200.5\",\"1,100.0\",\"1,000.0\",950 "
            ", 증가율(QoQ),,,1,2,3,4 ,영업이익,,,120,100,80,70 ,당기순이익(지배),,,90,80,60,50 ,배당수익률,,,-,-,-,-")


def test_parse_drive_text_compact_matches_xlsx(tmp_path):
    t = tmp_path / "바이오.txt"
    t.write_text(COMPACT_TXT, encoding="utf-8")
    x = tmp_path / "바이오.xlsx"
    _compact(x)
    a, b = loader.load(t), loader.load(x)
    assert a.quarters == b.quarters and a.annual == b.annual and a.annual_est == b.annual_est


def test_parse_drive_text_wide(tmp_path):
    t = tmp_path / "w.txt"
    t.write_text(WIDE_TXT, encoding="utf-8")
    fin = loader.load(t)
    assert fin.get("rev", (2026, 3)) == 1200.5
    assert fin.est == {(2026, 3)}
    assert fin.basis[(2025, 2)] == "IFRS(별도)"


@pytest.mark.parametrize("raw,q,expected", [
    ("10월 22일", (2026, 3), dt.date(2026, 10, 22)),
    ("11월 3일 ", (2026, 3), dt.date(2026, 11, 3)),
    ("2월 10일", (2026, 4), dt.date(2027, 2, 10)),
    ("5/14", (2027, 1), dt.date(2027, 5, 14)),
    ("2026-10-22", (2026, 3), dt.date(2026, 10, 22)),
    ("발표일", (2026, 3), None),
])
def test_announce_date(raw, q, expected):
    assert di.announce_date(raw, q) == expected


def test_quarter_and_filename():
    assert di.parse_quarter("26년 3분기") == (2026, 3)
    assert di.parse_quarter("2027년 1분기 재무데이터") == (2027, 1)
    assert di.fin_file_info("LB 세미콘 (단위 십억,  % 배).xlsx") == ("LB 세미콘", 10)
    assert di.fin_file_info("주성엔지니어링(단위 억, %배).xlsx") == ("주성엔지니어링", 1)
    assert di.fin_file_info("티엘비.xlsx") == ("티엘비", None)


def test_resolver():
    r = di.Resolver(["SK하이닉스", "HLB제약", "퓨처켐"], {"퓨쳐켐": "퓨처켐"})
    assert r("sk 하이닉스") == "SK하이닉스"
    assert r("HLB 제약") == "HLB제약"
    assert r("퓨쳐켐") == "퓨처켐"
    assert r("새 회사") == "새회사"


def _drive(tmp_path):
    d = tmp_path / "drive"
    (d / "실적예정일" / "26년 3분기").mkdir(parents=True)
    (d / "실적예정일" / "26년 3분기" / "일정.txt").write_text(
        "Sheet1 10월 22일,바이 오 10월 23일 ,가 나 다", encoding="utf-8")
    fd = d / "재무데이터" / "26년 3분기" / "하위폴더"
    fd.mkdir(parents=True)
    (fd / "바이오 (단위 십억, %).txt").write_text(COMPACT_TXT, encoding="utf-8")
    return d


def test_build_from_drive(tmp_path, capsys):
    d = _drive(tmp_path)
    out = tmp_path / "out"
    cli_main(["--config", str(tmp_path / "noconfig"), "build", "--drive-dir", str(d), "--out", str(out), "--today", "2026-10-01"])
    import json
    rep = json.loads((out / "report.json").read_text(encoding="utf-8"))
    assert rep["events"] == 2
    assert rep["missing_financials"] == ["가나다"]
    assert rep["months"]["2026.10"]["blocks"] == [["바이오"]]
    assert rep["new_tabs"] == {"2026.10": 202610}


def test_plan(tmp_path, capsys):
    import json
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    (cfg / "sheets.json").write_text(json.dumps({"drive_folder_id": "ROOT"}), encoding="utf-8")
    F = "application/vnd.google-apps.folder"
    X = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    files = [
        {"id": "S", "parentId": "ROOT", "title": "실적예정일", "mimeType": F},
        {"id": "Q1", "parentId": "S", "title": "26년 3분기", "mimeType": F},
        {"id": "s1", "parentId": "Q1", "title": "일정.xlsx", "mimeType": X, "modifiedTime": "t1"},
        {"id": "FD", "parentId": "ROOT", "title": "재무데이터", "mimeType": F},
        {"id": "Q2", "parentId": "FD", "title": "26년 3분기", "mimeType": F},
        {"id": "SUB", "parentId": "Q2", "title": "26년 3분기 재무데이터", "mimeType": F},
        {"id": "f1", "parentId": "SUB", "title": "티엘비 (단위 억, % 배).xlsx", "mimeType": X, "modifiedTime": "t2"},
    ]
    sj = tmp_path / "s.json"
    sj.write_text(json.dumps({"files": files}), encoding="utf-8")
    cli_main(["--config", str(cfg), "plan", str(sj), "--drive-dir", str(tmp_path / "drive")])
    res = json.loads(capsys.readouterr().out)
    paths = sorted(f["path"] for f in res["files"])
    assert paths == ["실적예정일/26년 3분기/일정.txt", "재무데이터/26년 3분기/티엘비 (단위 억, % 배).txt"]
