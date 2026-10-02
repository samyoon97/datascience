"""실적 캘린더 빌드.

    python -m earnings_calendar build --fin-dir DIR [--schedule config/schedule.csv] [--out out] [--months 2026.11 ...]

입력
  config/schedule.csv     발표일,기업명,내용(선택),색상(선택, HEX) — 시트 '입력' 탭을 csv 로 저장한 것
  config/sheets.json      spreadsheet_id, tabs({"2026.10": sheetId}), content_px(탭별 고정 높이, 선택),
                          skip_months(탭을 따로 만들지 않을 달, 예: 9/30 IR 하나뿐인 9월)
  config/colors.json      기업별 브랜드 색 (없으면 기본색)
  config/notes.json       기업별 수동 주석 (없으면 회계기준을 보고 자동 생성)
  config/units.json       기업별 단위 배수 강제 (자동 판정이 틀릴 때만)
  DIR/<기업명>.xlsx|csv|json  재무 파일 (CHECK/FnGuide 엑셀 그대로)

출력 (out/)
  <탭>/NN_*.json   Sheets batchUpdate requests, 파일명 순서대로 전송
  calendar_events.json  구글 캘린더 일정
  report.json      탭별 칸 구성, 재무 데이터 누락 기업 등
"""
import argparse
import csv
import json
import sys
from pathlib import Path

from . import gcal, loader
from .sheet_requests import default_note, month_batches, parse_date

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_COLOR = "1F4E79"


def read_json(path, default):
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def read_schedule(path):
    """A~D열 = 발표일, 기업명, 내용(선택), 색상(선택). 첫 줄은 머리글. E열 이후(사용법 등)는 무시."""
    rows = []
    with open(path, encoding="utf-8-sig") as f:
        for r in list(csv.reader(f))[1:]:
            r = (r + ["", "", "", ""])[:4]
            if not (r[0].strip() and r[1].strip()):
                continue
            d = parse_date(r[0])
            rows.append((d, r[1].strip(), r[2].strip() or default_note(d), r[3].strip().lstrip("#").upper() or None))
    return sorted(rows, key=lambda x: x[0])


def find_fin_file(fin_dir, name):
    for ext in (".xlsx", ".csv", ".json"):
        p = Path(fin_dir) / f"{name}{ext}"
        if p.exists():
            return p
    return None


def build(args):
    cfg = Path(args.config)
    sheets = read_json(cfg / "sheets.json", {})
    colors = read_json(cfg / "colors.json", {})
    notes = read_json(cfg / "notes.json", {})
    units = read_json(cfg / "units.json", {})
    tabs = dict(sheets.get("tabs", {}))
    if args.tabs_json:
        tabs.update(read_json(args.tabs_json, {}))
    px_cfg = sheets.get("content_px", {})

    schedule = read_schedule(args.schedule)
    for _, n, _, c in schedule:          # 일정표의 색상 칸이 config 보다 우선
        if c:
            colors[n] = c
    schedule = [(d, n, note) for d, n, note, _ in schedule]
    fins, missing = {}, []
    for name in dict.fromkeys(n for _, n, _ in schedule):
        p = find_fin_file(args.fin_dir, name) if args.fin_dir else None
        if p:
            fins[name] = loader.load(p, name=name, unit=units.get(name))
        else:
            missing.append(name)
    color = lambda n: colors.get(n, DEFAULT_COLOR)

    skip = set(sheets.get("skip_months", []))
    months = sorted(({f"{d.year}.{d.month:02d}" for d, _, _ in schedule} - skip) | set(args.months or []))
    out = Path(args.out)
    report = {"months": {}, "missing_financials": missing, "new_tabs": {}}
    events = {}
    for d, n, note in schedule:
        events.setdefault(d, []).append((n, color(n), note))

    for title in months:
        y, m = map(int, title.split("."))
        exists = title in tabs
        sid = tabs.get(title, y * 100 + m)
        if not exists:
            report["new_tabs"][title] = sid
        order = []
        for d, n, _ in schedule:
            if (d.year, d.month) == (y, m) and n not in order:
                order.append(n)
        entries = [(fins[n], color(n), notes.get(n)) for n in order if n in fins]
        batches, info = month_batches(y, m, sid, exists, events, entries, px_cfg.get(title))
        tab_dir = out / title
        tab_dir.mkdir(parents=True, exist_ok=True)
        for old in tab_dir.glob("*.json"):
            old.unlink()
        files = []
        for i, b in enumerate(batches):
            f = tab_dir / (f"{i:02d}_structure.json" if i == 0 else f"{i:02d}_panel{i}.json")
            f.write_text(json.dumps(b, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            files.append({"file": str(f), "bytes": f.stat().st_size})
        report["months"][title] = {"sheetId": sid, "exists": exists, **info, "files": files,
                                   "no_financials": [n for n in order if n not in fins]}

    cal = [gcal.event(d, n, note, color(n), fins.get(n), notes.get(n)) for d, n, note in schedule]
    (out / "calendar_events.json").write_text(json.dumps(cal, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=1))


def import_schedule(args):
    """시트 '입력' 탭 get_values 결과(JSON)를 config/schedule.csv 로 저장."""
    data = json.loads(Path(args.json).read_text(encoding="utf-8"))
    values = data.get("values", data) if isinstance(data, dict) else data
    out = Path(args.out)
    with open(out, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        for r in values:
            w.writerow((list(r) + ["", "", "", ""])[:4])
    n = len(read_schedule(out))
    print(f"{out}: 일정 {n}건")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="earnings_calendar")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--schedule", default=str(ROOT / "config" / "schedule.csv"))
    b.add_argument("--fin-dir", default=None)
    b.add_argument("--config", default=str(ROOT / "config"))
    b.add_argument("--tabs-json", default=None, help='현재 시트의 {"탭이름": sheetId} (config 값보다 우선)')
    b.add_argument("--months", nargs="*", help="일정이 없어도 다시 그릴 탭 (예: 2026.12)")
    b.add_argument("--out", default="out")
    imp = sub.add_parser("import-schedule", help="'입력' 탭 get_values JSON -> schedule.csv")
    imp.add_argument("json")
    imp.add_argument("--out", default=str(ROOT / "config" / "schedule.csv"))
    args = ap.parse_args(argv)
    if args.cmd == "build":
        build(args)
    elif args.cmd == "import-schedule":
        import_schedule(args)


if __name__ == "__main__":
    sys.exit(main())
