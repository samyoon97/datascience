"""실적 캘린더 빌드.

    python -m earnings_calendar plan <search_files 결과.json ...> [--drive-dir drive]
    python -m earnings_calendar build [--drive-dir drive] [--out out] [--months 2026.11 ...] [--all]

입력: 구글 드라이브 '실적 캘린더' 폴더를 내려받은 로컬 미러 (drive_input.py 참고)
  실적예정일/<26년 3분기>/*.xlsx|txt   발표일, 기업명, (내용)
  재무데이터/<26년 3분기>/**/<기업명> (단위 억, %배).xlsx|txt

설정 (config/)
  sheets.json   spreadsheet_id, drive 폴더 ID, tabs({"2026.10": sheetId}), content_px(탭별 칸 높이), skip_months
  colors.json   기업별 브랜드 색 (없으면 기본 남색)
  aliases.json  기업명 표기 변형 -> 정식 이름 (띄어쓰기 차이는 자동 처리)
  notes.json    기업별 수동 주석 (없으면 회계기준을 보고 자동 생성)
  units.json    기업별 단위 배수 강제 (파일명 '단위 십억' 과 양식 자동 판정이 둘 다 틀릴 때만)

출력 (out/)
  <탭>/NN_*.json        Sheets batchUpdate requests, 파일명 순서대로 전송
  calendar_events.json  구글 캘린더 일정
  report.json           탭별 칸 구성, 재무 누락 기업, 이름 보정 내역 등
"""
import argparse
import datetime as dt
import json
import sys
from pathlib import Path

from . import drive_input, gcal
from .sheet_requests import month_batches

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_COLOR = "1F4E79"
DOC_EXT = (".xlsx", ".xls", ".csv")


def read_json(path, default):
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def plan(args):
    """search_files 결과들로 폴더 트리를 만들어, 내려받을 파일과 저장 경로 목록을 만든다."""
    sheets = read_json(Path(args.config) / "sheets.json", {})
    root = sheets["drive_folder_id"]
    files = {}
    for p in args.search_json:
        data = read_json(p, {})
        for f in data.get("files", data if isinstance(data, list) else []):
            files[f["id"]] = f
    children = {}
    for f in files.values():
        children.setdefault(f.get("parentId"), []).append(f)
    is_folder = lambda f: f["mimeType"] == "application/vnd.google-apps.folder"

    out, missing_dirs = [], []
    for top in (drive_input.SCHEDULE_DIR, drive_input.FIN_DIR):
        tops = [f for f in children.get(root, []) if is_folder(f) and f["title"].strip() == top]
        if not tops:
            missing_dirs.append(top)
            continue
        for qf in [f for f in children.get(tops[0]["id"], []) if is_folder(f)]:
            stack = [qf["id"]]
            while stack:                                # 분기 폴더 아래 하위 폴더까지 전부
                for f in children.get(stack.pop(), []):
                    if is_folder(f):
                        stack.append(f["id"])
                    elif f["title"].lower().endswith(DOC_EXT) or f["mimeType"].endswith("spreadsheet"):
                        stem = Path(f["title"]).stem if f["title"].lower().endswith(DOC_EXT) else f["title"]
                        out.append({"id": f["id"], "title": f["title"], "modified": f.get("modifiedTime", ""),
                                    "folder_id": qf["id"],
                                    "path": f"{top}/{qf['title'].strip()}/{stem}.txt"})
    seen = {}
    for o in out:                                       # 같은 이름 파일이 하위 폴더에 여럿이면 경로 충돌 방지
        n = seen.setdefault(o["path"], 0)
        seen[o["path"]] += 1
        if n:
            o["path"] = o["path"][:-4] + f"__{n}.txt"
    drive = Path(args.drive_dir)
    drive.mkdir(parents=True, exist_ok=True)
    (drive / "manifest.json").write_text(json.dumps([{"path": o["path"], "id": o["id"], "modified": o["modified"]} for o in out],
                                                    ensure_ascii=False, indent=1), encoding="utf-8")
    known = {o["folder_id"] for o in out}
    print(json.dumps({"files": out, "missing_top_folders": missing_dirs,
                      "folders_to_list": sorted({f["id"] for f in files.values() if is_folder(f)} - known - set(children))},
                     ensure_ascii=False, indent=1))


def build(args):
    cfg = Path(args.config)
    sheets = read_json(cfg / "sheets.json", {})
    colors = read_json(cfg / "colors.json", {})
    aliases = read_json(cfg / "aliases.json", {})
    notes = read_json(cfg / "notes.json", {})
    units = read_json(cfg / "units.json", {})
    tabs = dict(sheets.get("tabs", {}))
    if args.tabs_json:
        tabs.update(read_json(args.tabs_json, {}))
    px_cfg = sheets.get("content_px", {})

    resolve = drive_input.Resolver(list(colors) + list(notes) + list(units), aliases)
    events = drive_input.read_schedules(args.drive_dir, resolve)
    by_q, latest, log = drive_input.read_financials(args.drive_dir, resolve, units)
    color = lambda n: colors.get(n, DEFAULT_COLOR)

    def fin_for(e):
        return by_q.get((e.quarter, e.company)) or latest.get(e.company)

    today = dt.date.fromisoformat(args.today) if args.today else dt.date.today()
    skip = set(sheets.get("skip_months", []))
    months = {f"{e.date.year}.{e.date.month:02d}" for e in events} - skip
    if not args.all:                                     # 지난 달 탭은 기록으로 두고 다시 그리지 않음
        months = {t for t in months if t >= f"{today.year}.{today.month:02d}"}
    if args.months:
        months = set(args.months)
    out = Path(args.out)
    report = {"months": {}, "new_tabs": {}, "name_fixes": resolve.fuzzy, "log": log,
              "no_color": sorted({e.company for e in events if e.company not in colors}),
              "missing_financials": sorted({e.company for e in events if not fin_for(e)}),
              "events": len(events)}
    cal_cells = {}
    for e in events:
        cal_cells.setdefault(e.date, []).append((e.company, color(e.company), e.note))

    for title in sorted(months):
        y, m = map(int, title.split("."))
        exists = title in tabs
        sid = tabs.get(title, y * 100 + m)
        if not exists:
            report["new_tabs"][title] = sid
        entries, seen = [], set()
        for e in events:
            if (e.date.year, e.date.month) == (y, m) and e.company not in seen:
                seen.add(e.company)
                f = fin_for(e)
                if f:
                    entries.append((f, color(e.company), notes.get(e.company)))
        batches, info = month_batches(y, m, sid, exists, cal_cells, entries, px_cfg.get(title))
        tab_dir = out / title
        tab_dir.mkdir(parents=True, exist_ok=True)
        for old in tab_dir.glob("*.json"):
            old.unlink()
        files = []
        for i, b in enumerate(batches):
            f = tab_dir / (f"{i:02d}_structure.json" if i == 0 else f"{i:02d}_panel{i}.json")
            f.write_text(json.dumps(b, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            files.append({"file": str(f), "bytes": f.stat().st_size})
        report["months"][title] = {"sheetId": sid, "exists": exists, **info, "files": files}

    cal = [gcal.event(e.date, e.company, e.note, color(e.company), fin_for(e), notes.get(e.company)) for e in events]
    out.mkdir(parents=True, exist_ok=True)
    (out / "calendar_events.json").write_text(json.dumps(cal, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=1))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="earnings_calendar")
    ap.add_argument("--config", default=str(ROOT / "config"))
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan", help="드라이브 search_files 결과 -> 내려받을 파일 목록과 manifest")
    p.add_argument("search_json", nargs="+")
    p.add_argument("--drive-dir", default="drive")
    b = sub.add_parser("build")
    b.add_argument("--drive-dir", default="drive")
    b.add_argument("--tabs-json", default=None, help='현재 시트의 {"탭이름": sheetId} (config 값보다 우선)')
    b.add_argument("--months", nargs="*", help="이 탭들만 다시 그림 (예: 2026.11 2026.12)")
    b.add_argument("--all", action="store_true", help="지난 달 탭도 다시 그림")
    b.add_argument("--today", default=None, help="기준일 (테스트용, YYYY-MM-DD)")
    b.add_argument("--out", default="out")
    args = ap.parse_args(argv)
    {"plan": plan, "build": build}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
