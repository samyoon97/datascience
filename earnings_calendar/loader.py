"""CHECK / FnGuide 재무 엑셀 파서.

두 가지 양식을 자동으로 구분한다.

* wide   : A1 비어 있고 B1 = '항목'. 라벨은 B열, 단위 억원.
           헤더 예: '2026 Q4(E)', '2026 Q2' ... / '주재무제표' 행에 IFRS(연결)/IFRS(별도)
* compact: A1 = '구분'. 라벨은 A열, 단위 10억원(×10 해서 억원으로 변환).
           연간('2025 Y', '2026 Y(E)')과 분기 열이 섞여 있고 2행에 IFRS(연결) 등.

결과는 모두 억원 단위.
"""
import csv
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

LABELS = {
    "rev": ["매출액", "영업수익"],
    "op": ["영업이익"],
    "np": ["당기순이익(지배)", "순이익(지배)", "지배주주순이익"],
}


@dataclass
class Financials:
    name: str
    quarters: dict = field(default_factory=dict)   # metric -> {(y, q): val}
    est: set = field(default_factory=set)            # {(y, q)} 컨센서스 분기
    annual: dict = field(default_factory=dict)       # metric -> {y: val}
    annual_est: set = field(default_factory=set)     # {y}
    basis: dict = field(default_factory=dict)        # (y, q) -> 'IFRS(연결)' 등

    def get(self, metric, q):
        return self.quarters.get(metric, {}).get(q)


def _rows(path):
    path = Path(path)
    if path.suffix.lower() == ".json":
        return [tuple(r) for r in json.loads(path.read_text(encoding="utf-8"))]
    if path.suffix.lower() == ".csv":
        with open(path, encoding="utf-8-sig") as f:
            return [tuple(_num(c) for c in r) for r in csv.reader(f)]
    import openpyxl
    ws = openpyxl.load_workbook(path, data_only=True).active
    return [tuple(r) for r in ws.iter_rows(values_only=True)]


def _num(c):
    if c is None:
        return None
    s = str(c).strip().replace(",", "")
    try:
        return float(s)
    except ValueError:
        return c


def _period(h):
    """'2026 Q3(E)' -> ('Q', (2026, 3), True); '2026 Y(E)' -> ('Y', 2026, True)."""
    s = str(h or "")
    est = "(E)" in s
    m = re.match(r"\s*(\d{4})\s*Q(\d)", s)
    if m:
        return "Q", (int(m[1]), int(m[2])), est
    m = re.match(r"\s*(\d{4})\s*Y", s)
    if m:
        return "Y", int(m[1]), est
    return None


def load(path, name=None, unit=None):
    """재무 파일을 읽어 Financials 반환. unit 을 주면 자동 판정 대신 그 배수를 쓴다."""
    rows = [r for r in _rows(path) if r and any(v not in (None, "") for v in r)]
    first = rows[0]
    if str(first[0] or "").strip() == "구분":
        label_col, mult = 0, 10
    else:
        label_col, mult = 1, 1
    if unit is not None:
        mult = unit
    hdr = first
    cols = {i: _period(h) for i, h in enumerate(hdr) if _period(h)}
    fin = Financials(name=name or Path(path).stem)

    # 회계 기준 행: wide 는 D열 '주재무제표', compact 는 IFRS(...) 가 들어 있는 2행
    for r in rows[1:4]:
        tags = [str(r[i]) for i in cols if i < len(r) and r[i] is not None]
        if tags and all(re.search(r"IFRS|GAAP", t) for t in tags):
            for i, (kind, key, _) in cols.items():
                if kind == "Q" and i < len(r) and r[i]:
                    fin.basis[key] = str(r[i])
            break

    for r in rows:
        if label_col >= len(r) or not isinstance(r[label_col], str):
            continue
        lab = r[label_col].strip()
        for metric, names in LABELS.items():
            if lab in names and metric not in fin.quarters:
                fin.quarters[metric], fin.annual[metric] = {}, {}
                for i, (kind, key, est) in cols.items():
                    v = r[i] if i < len(r) else None
                    v = v * mult if isinstance(v, (int, float)) else None
                    (fin.quarters if kind == "Q" else fin.annual)[metric][key] = v
    for i, (kind, key, est) in cols.items():
        if est:
            (fin.est if kind == "Q" else fin.annual_est).add(key)
    for metric in LABELS:
        fin.quarters.setdefault(metric, {})
        fin.annual.setdefault(metric, {})
    return fin


def is_standalone(basis):
    return bool(re.search(r"별도|개별", basis or ""))


def auto_note(fin, shown, compared):
    """표시 분기(shown)와 YoY 비교 분기(compared)의 회계 기준을 보고 주석을 만든다."""
    b = fin.basis
    shown_b = {q: b[q] for q in shown if q in b}
    if not shown_b:
        return None
    sep = {q for q, t in shown_b.items() if is_standalone(t)}
    est_q = [q for q in shown_b if q in fin.est]
    act_q = [q for q in shown_b if q not in fin.est]
    if sep and len(sep) == len(shown_b):
        return "* IFRS 별도 기준"
    if est_q and act_q and all(q in sep for q in est_q) and not any(q in sep for q in act_q):
        return "* (E)는 별도 기준, 확정치는 연결 기준"
    if sep:
        last = max(sep)
        return f"* {last[0]}.{last[1]}Q 이전은 별도 기준, 이후 연결 기준"
    cmp_sep = sorted(q for q in compared if is_standalone(b.get(q)))
    if cmp_sep:
        last = cmp_sep[-1]
        return f"* {last[0]}.{last[1]}Q 이전은 별도 기준, 이후 연결 기준 (YoY 비교 시 참고)"
    return None
