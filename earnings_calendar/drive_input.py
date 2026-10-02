"""구글 드라이브 '실적 캘린더' 폴더 구조를 읽는다.

드라이브 구조 (사용자가 관리)
    실적 캘린더/
      실적예정일/<26년 3분기>/<아무 이름>.xlsx      A열 발표일('10월 22일' 등), B열 기업명, C열 내용(선택)
      재무데이터/<26년 3분기>/.../<기업명> (단위 억, %배).xlsx   CHECK/FnGuide 엑셀

로컬 미러 (Claude 가 드라이브에서 받아 만든다)
    <drive_dir>/manifest.json         [{"path": 상대경로, "id": 파일ID, "modified": modifiedTime}]
    <drive_dir>/실적예정일/<분기>/<파일>.txt|xlsx
    <drive_dir>/재무데이터/<분기>/<파일>.txt|xlsx   (분기 폴더 아래 하위 폴더는 평평하게 풀어서 저장)
    .txt 는 Drive read_file_content 결과 원문.
"""
import csv
import datetime as dt
import difflib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from . import loader

SCHEDULE_DIR, FIN_DIR = "실적예정일", "재무데이터"


def parse_quarter(label):
    """'26년 3분기' / '2026년 3분기' / '2026 Q3' -> (2026, 3)."""
    m = re.search(r"(\d{2,4})\s*년?\s*(\d)\s*분기", label) or re.search(r"(\d{2,4})\s*Q(\d)", label, re.I)
    if not m:
        return None
    y = int(m[1])
    return (y + 2000 if y < 100 else y), int(m[2])


def announce_date(raw, quarter):
    """'10월 22일', '10/22', '2026-10-22', date ... -> date. 연도가 없으면 분기로 추정."""
    if isinstance(raw, dt.datetime):
        return raw.date()
    if isinstance(raw, dt.date):
        return raw
    if isinstance(raw, (int, float)) and 20000 < raw < 80000:        # 엑셀 날짜 일련번호
        return dt.date(1899, 12, 30) + dt.timedelta(days=int(raw))
    nums = [int(x) for x in re.findall(r"\d+", str(raw or ""))]
    if len(nums) >= 3 and nums[0] > 31:
        y, m, d = nums[:3]
        return dt.date(y + 2000 if y < 100 else y, m, d)
    if len(nums) >= 2:
        m, d = nums[:2]
        qy, qn = quarter
        # 분기 마지막 달 이후면 같은 해(3분기 -> 10~12월), 아니면 다음 해(4분기 -> 1~3월)
        return dt.date(qy if m > 3 * qn else qy + 1, m, d)
    return None


def fin_file_info(filename):
    """'LB 세미콘 (단위 십억, % 배).xlsx' -> ('LB 세미콘', 10)."""
    stem = Path(filename).stem
    name = re.split(r"[\(（\[]", stem)[0].strip()
    unit = None
    m = re.search(r"단위\s*([^,)\s]*)", stem)
    if m:
        u = m[1]
        unit = 10 if "십억" in u else 100 if "백억" in u else 1 if "억" in u else None
    return name, unit


def norm(name):
    return re.sub(r"[\s·.\-_]", "", str(name)).upper()


class Resolver:
    """표기가 제각각인 기업명(띄어쓰기, 오타)을 정해진 이름으로 맞춘다."""

    def __init__(self, known, aliases):
        self.known = {norm(k): k for k in known}
        self.aliases = {norm(a): c for a, c in aliases.items()}
        self.fuzzy = {}

    def __call__(self, raw):
        n = norm(raw)
        if n in self.known:
            return self.known[n]
        if n in self.aliases:
            return self.aliases[n]
        hit = difflib.get_close_matches(n, list(self.known), n=1, cutoff=0.75)
        if hit:
            self.fuzzy[raw] = self.known[hit[0]]
            return self.known[hit[0]]
        name = re.sub(r"\s+", "", str(raw).strip())
        self.known[n] = name           # 처음 보는 기업: 띄어쓰기만 없앤 이름으로 등록
        return name


@dataclass
class Event:
    date: dt.date
    company: str
    note: str
    quarter: tuple
    source: str


def _sheet_rows(path):
    path = Path(path)
    if path.suffix.lower() == ".txt":
        text = path.read_text(encoding="utf-8").strip()
        text = text.split(" ", 1)[1] if " " in text else ""
        # 일정 파일은 셀에 공백이 있어 행 경계 구분이 어려우므로 '날짜 패턴'으로 끊는다
        rows = []
        for m in re.finditer(r"(\d{1,2}\s*월\s*\d{1,2}\s*일|\d{4}[-./]\s*\d{1,2}[-./]\s*\d{1,2}|\d{1,2}/\d{1,2}(?:/\d{2,4})?)\s*,([^,]*?)(?:,([^,]*?))?(?=\s+(?:\d{1,2}\s*월|\d{4}[-./]|\d{1,2}/\d)|\s*$)",
                             text):
            rows.append((m[1], m[2], m[3] or ""))
        return rows
    import openpyxl
    ws = openpyxl.load_workbook(path, data_only=True).active
    return [tuple(r) for r in ws.iter_rows(values_only=True)]


def read_schedules(drive_dir, resolve):
    events = []
    base = Path(drive_dir) / SCHEDULE_DIR
    for qdir in sorted(p for p in base.iterdir() if p.is_dir()) if base.exists() else []:
        q = parse_quarter(qdir.name)
        if not q:
            continue
        for f in sorted(qdir.rglob("*")):
            if f.suffix.lower() not in (".xlsx", ".txt", ".csv"):
                continue
            rows = list(csv.reader(open(f, encoding="utf-8-sig"))) if f.suffix == ".csv" else _sheet_rows(f)
            for r in rows:
                r = list(r) + [None, None, None]
                if not r[1] or not str(r[1]).strip():
                    continue
                d = announce_date(r[0], q)
                if not d:
                    continue                      # 머리글 등
                note = str(r[2]).strip() if r[2] else f"{q[1]}분기 실적 발표 예정"
                events.append(Event(d, resolve(str(r[1]).strip()), note, q, str(f)))
    events.sort(key=lambda e: (e.date, e.source))
    seen, out = set(), []
    for e in events:                              # 같은 날 같은 기업 중복 제거
        if (e.date, e.company, e.note) not in seen:
            seen.add((e.date, e.company, e.note))
            out.append(e)
    return out


def read_financials(drive_dir, resolve, unit_override=None):
    """-> {(분기, 기업명): Financials}, {기업명: Financials(가장 최근 파일)}, 로그."""
    unit_override = unit_override or {}
    base = Path(drive_dir) / FIN_DIR
    manifest = {}
    mf = Path(drive_dir) / "manifest.json"
    if mf.exists():
        manifest = {m["path"]: m.get("modified", "") for m in json.loads(mf.read_text(encoding="utf-8"))}
    picked = {}
    log = []
    for f in sorted(base.rglob("*")) if base.exists() else []:
        if f.suffix.lower() not in (".xlsx", ".txt", ".csv", ".json"):
            continue
        rel = f.relative_to(drive_dir).as_posix()
        q = parse_quarter(f.relative_to(base).parts[0]) if len(f.relative_to(base).parts) > 1 else None
        raw, unit = fin_file_info(f.name)
        name = resolve(raw)
        key = (q, name)
        mod = manifest.get(rel, "")
        if key in picked and picked[key][0] >= mod:
            log.append(f"중복 파일 무시(더 오래됨): {rel}")
            continue
        if key in picked:
            log.append(f"중복 파일 무시(더 오래됨): {picked[key][1]}")
        picked[key] = (mod, rel, f, unit)
    by_q, latest = {}, {}
    for (q, name), (mod, rel, f, unit) in picked.items():
        try:
            fin = loader.load(f, name=name, unit=unit_override.get(name, unit))
        except Exception as e:                      # 파일 하나가 깨져도 나머지는 진행
            log.append(f"읽기 실패 {rel}: {e}")
            continue
        by_q[(q, name)] = fin
        if name not in latest or latest[name][0] < mod:
            latest[name] = (mod, fin)
    return by_q, {n: v[1] for n, v in latest.items()}, log
