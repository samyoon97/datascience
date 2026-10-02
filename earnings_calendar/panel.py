"""'이달 체크 포인트' 블록 텍스트와 서식 run 생성."""
from .formatting import BLACK, MUTE, amt, rgb_compact, yoy
from .loader import auto_note

HEADER = "(단위: 조/억원, 괄호: 전년 동기 대비 증감률 %, (E): 컨센서스)\n\n"
METRICS = ("rev", "op", "np")
N_ACTUAL = 5


def shown_quarters(fin):
    qs = sorted((q for q in fin.quarters["rev"].keys() | fin.quarters["op"].keys() | fin.quarters["np"].keys()
                 if any(fin.get(m, q) is not None for m in METRICS)), reverse=True)
    return [q for q in qs if q in fin.est] + [q for q in qs if q not in fin.est][:N_ACTUAL]


def company_parts(idx, fin, color, note=None):
    """한 기업 블록을 (text, hex color, bold) 조각 리스트로."""
    parts = [(f"{idx}. ", BLACK, True), (fin.name, color, True), (" 실적 추이\n", BLACK, True),
             ("   (기간/ 매출/ 영업익/ 순익)\n", MUTE, False)]

    def line(label, vals, prevs):
        parts.append((f"   {label} ", BLACK, False))
        for k, (v, pv) in enumerate(zip(vals, prevs)):
            sep = "/ " if k < 2 else "\n"
            if v is None:
                parts.append(("-" + sep, BLACK, False))
                continue
            t, c = yoy(v, pv)
            parts.extend([(amt(v) + "(", BLACK, False), (t, c, False), (")" + sep, BLACK, False)])

    qs = shown_quarters(fin)
    # 분기 컨센서스가 없고 연간 컨센서스만 있으면 연간 라인을 맨 위에
    if not any(q in fin.est for q in qs) and fin.annual_est:
        y = min(fin.annual_est)
        line(f"{y}년(E)", [fin.annual[m].get(y) for m in METRICS], [fin.annual[m].get(y - 1) for m in METRICS])
    for q in qs:
        lab = f"{q[0]}.{q[1]}Q" + ("(E)" if q in fin.est else "")
        line(lab, [fin.get(m, q) for m in METRICS], [fin.get(m, (q[0] - 1, q[1])) for m in METRICS])
    note = note or auto_note(fin, qs, [(q[0] - 1, q[1]) for q in qs])
    if note:
        parts.append(("   " + note + "\n", MUTE, False))
    parts.append(("\n", BLACK, False))
    return parts


def render(parts):
    """조각 리스트 -> (text, textFormatRuns). startIndex 는 UTF-16 기준."""
    text, runs, pos = "", [], 0
    for t, color, bold in parts:
        fmt = {}
        if bold:
            fmt["bold"] = True
        c = rgb_compact(color)
        if c:
            fmt["foregroundColorStyle"] = {"rgbColor": c}
        if not (runs and runs[-1]["format"] == fmt) and (runs or fmt):
            runs.append({"startIndex": pos, "format": fmt})
        text += t
        pos += len(t.encode("utf-16-le")) // 2
    text = text.rstrip("\n")
    end = len(text.encode("utf-16-le")) // 2
    return text, [r for r in runs if r["startIndex"] < end]


def block(entries, start, header):
    """entries: [(Financials, color, note)] -> (text, runs)."""
    parts = [(HEADER, MUTE, False)] if header else []
    for i, (fin, color, note) in enumerate(entries, start):
        parts += company_parts(i, fin, color, note)
    if not entries and header:
        parts.append(("재무 데이터 대기 중", MUTE, False))
    return render(parts)


def split_blocks(entries, max_lines):
    """발표일 순서를 유지하며 줄 수 한도(max_lines) 안에서 칸을 나눈다."""
    blocks, cur, start = [], [], 1

    def n_lines(es, st, hdr):
        return block(es, st, hdr)[0].count("\n") + 1

    for e in entries:
        hdr = not blocks
        if cur and n_lines(cur + [e], start, hdr) > max_lines:
            blocks.append((cur, start, hdr))
            start += len(cur)
            cur = []
        cur.append(e)
    blocks.append((cur, start, not blocks))
    return blocks
