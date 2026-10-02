"""월별 탭(달력 + 이달 체크 포인트)을 통째로 다시 그리는 Sheets batchUpdate 요청 생성.

탭 하나를 매번 처음부터 다시 그리므로(idempotent) 기업이 추가/삭제되거나
발표일이 바뀌어도 같은 명령으로 갱신된다.
"""
import calendar
import datetime as dt

from .formatting import BLACK, rgb_compact
from .panel import block, split_blocks

# 레이아웃(px)
COL_A, DAY_W, GAP_W, PANEL_W, PANEL_GAP = 13, 181, 20, 125, 20
PANEL_COL = 9          # J열
DATE_PX = 21
RED, GRAY = "E60012", "A6A6A6"
HDR_FILL = {"red": 0.616, "green": 0.765, "blue": 0.902}
BORDER = {"style": "SOLID", "color": {"red": 0.31, "green": 0.506, "blue": 0.741}}  # 4F81BD
WEEKDAYS = "일월화수목금토"
CLEAR_ROWS = 40


def weeks_of(year, month):
    return calendar.Calendar(firstweekday=6).monthdatescalendar(year, month)


def content_px(events_by_day, override=None):
    if override:
        return override
    most = max((len(v) for v in events_by_day.values()), default=0)
    return max(126, 15 * most + 12)


def max_panel_lines(n_weeks, px):
    return int((n_weeks * (px + DATE_PX) - 10) / 15.5)


def _rng(sid, r0, r1, c0, c1):
    return {"sheetId": sid, "startRowIndex": r0, "endRowIndex": r1, "startColumnIndex": c0, "endColumnIndex": c1}


def _box(sid, r0, r1, c0, c1, inner_v=False):
    req = {"range": _rng(sid, r0, r1, c0, c1), "top": BORDER, "bottom": BORDER, "left": BORDER, "right": BORDER}
    if inner_v:
        req["innerVertical"] = BORDER
    return {"updateBorders": req}


def _width(sid, c0, c1, px):
    return {"updateDimensionProperties": {"range": {"sheetId": sid, "dimension": "COLUMNS", "startIndex": c0, "endIndex": c1},
                                          "properties": {"pixelSize": px}, "fields": "pixelSize"}}


def _height(sid, r0, r1, px):
    return {"updateDimensionProperties": {"range": {"sheetId": sid, "dimension": "ROWS", "startIndex": r0, "endIndex": r1},
                                          "properties": {"pixelSize": px}, "fields": "pixelSize"}}


def _fmt(sid, r0, r1, c0, c1, fmt):
    return {"repeatCell": {"range": _rng(sid, r0, r1, c0, c1), "cell": {"userEnteredFormat": fmt}, "fields": "userEnteredFormat"}}


def _event_cell(events):
    """[(name, color, note)] -> 셀 값(서식 run 포함)."""
    text, runs, pos = "", [], 0
    for k, (name, color, note) in enumerate(events):
        for t, fmt in ((("\n" if k else "") , {}), (name, {"bold": True, "foregroundColorStyle": {"rgbColor": rgb_compact(color)}}),
                       (f": {note}", {})):
            if not t:
                continue
            if not (runs and runs[-1]["format"] == fmt) and (runs or fmt):
                runs.append({"startIndex": pos, "format": fmt})
            text += t
            pos += len(t.encode("utf-16-le")) // 2
    if not text:
        return {}
    cell = {"userEnteredValue": {"stringValue": text}}
    if runs:
        cell["textFormatRuns"] = runs
    return cell


def month_batches(year, month, sheet_id, exists, events, entries, px_override=None):
    """
    events : {date: [(name, color, note)]}   달력에 찍을 일정(인접 월 날짜 포함 가능)
    entries: [(Financials, color, note)]      체크 포인트에 넣을 기업, 발표일 순
    반환: 요청 배치 리스트 (첫 배치 = 탭 구조 + 달력, 이후 = 체크 포인트 칸 하나씩)
    """
    sid = sheet_id
    weeks = weeks_of(year, month)
    in_grid = {d for w in weeks for d in w}
    by_day = {d: v for d, v in events.items() if d in in_grid}
    px = content_px(by_day, px_override)
    blocks = split_blocks(entries, max_panel_lines(len(weeks), px))
    n_blocks = len(blocks)
    last_col = PANEL_COL + n_blocks * 5 - 1          # 마지막 칸 다음 열(exclusive)
    n_cols = max(26, last_col + 1)
    end_row = 4 + 2 * len(weeks)

    reqs = []
    props = {"sheetId": sid, "title": f"{year}.{month:02d}",
             "gridProperties": {"rowCount": 100, "columnCount": n_cols, "hideGridlines": True}}
    if exists:
        reqs.append({"updateSheetProperties": {"properties": {"sheetId": sid, "gridProperties": {"columnCount": n_cols, "hideGridlines": True}},
                                               "fields": "gridProperties.columnCount,gridProperties.hideGridlines"}})
        reqs.append({"unmergeCells": {"range": _rng(sid, 0, CLEAR_ROWS, 0, n_cols)}})
        reqs.append({"repeatCell": {"range": _rng(sid, 0, CLEAR_ROWS, 0, n_cols), "cell": {},
                                    "fields": "userEnteredValue,userEnteredFormat"}})
    else:
        reqs.append({"addSheet": {"properties": props}})

    # 크기
    reqs += [_width(sid, 0, 1, COL_A), _width(sid, 1, 8, DAY_W), _width(sid, 8, 9, GAP_W)]
    for b in range(n_blocks):
        c0 = PANEL_COL + 5 * b
        reqs.append(_width(sid, c0, c0 + 4, PANEL_W))
        if b < n_blocks - 1:
            reqs.append(_width(sid, c0 + 4, c0 + 5, PANEL_GAP))
    reqs += [_height(sid, 0, 1, 20), _height(sid, 1, 2, 45), _height(sid, 2, 4, 20)]
    for w in range(len(weeks)):
        reqs += [_height(sid, 4 + 2 * w, 5 + 2 * w, DATE_PX), _height(sid, 5 + 2 * w, 6 + 2 * w, px)]
    reqs.append(_height(sid, end_row, CLEAR_ROWS, 21))

    # 제목
    reqs.append({"mergeCells": {"range": _rng(sid, 1, 2, 1, 8), "mergeType": "MERGE_ALL"}})
    reqs.append({"repeatCell": {"range": _rng(sid, 1, 2, 1, 8),
                                "cell": {"userEnteredValue": {"stringValue": f"{year}년 {month}월 실적발표 캘린더"},
                                         "userEnteredFormat": {"horizontalAlignment": "CENTER", "verticalAlignment": "MIDDLE",
                                                               "textFormat": {"bold": True, "fontSize": 16}}},
                                "fields": "userEnteredValue,userEnteredFormat"}})

    # 요일 + 날짜/일정 셀: 공통 서식은 범위로 깔고, 셀에는 값과 글자색만 넣어 페이로드를 줄인다
    reqs.append(_fmt(sid, 3, 4, 1, 8, {"backgroundColor": HDR_FILL, "horizontalAlignment": "CENTER",
                                       "verticalAlignment": "MIDDLE", "textFormat": {"bold": True}}))
    for w in range(len(weeks)):
        reqs.append(_fmt(sid, 4 + 2 * w, 5 + 2 * w, 1, 8, {"verticalAlignment": "MIDDLE", "textFormat": {"bold": True}}))
        reqs.append(_fmt(sid, 5 + 2 * w, 6 + 2 * w, 1, 8,
                         {"wrapStrategy": "WRAP", "verticalAlignment": "TOP", "textFormat": {"fontSize": 9}}))

    def colored(value, color):
        cell = {"userEnteredValue": value}
        if color != BLACK:
            cell["userEnteredFormat"] = {"textFormat": {"foregroundColor": rgb_compact(color)}}
        return cell

    rows = [{"values": [colored({"stringValue": d}, RED if i in (0, 6) else BLACK) for i, d in enumerate(WEEKDAYS)]}]
    for week in weeks:
        date_row = [colored({"numberValue": day.day},
                            GRAY if day.month != month else (RED if i in (0, 6) else BLACK)) for i, day in enumerate(week)]
        rows += [{"values": date_row}, {"values": [_event_cell(by_day.get(day, [])) for day in week]}]
    reqs.append({"updateCells": {"start": {"sheetId": sid, "rowIndex": 3, "columnIndex": 1}, "rows": rows,
                                 "fields": "userEnteredValue,userEnteredFormat.textFormat.foregroundColor,textFormatRuns"}})
    reqs.append(_box(sid, 3, 4, 1, 8, inner_v=True))
    for w in range(len(weeks)):
        reqs.append(_box(sid, 4 + 2 * w, 6 + 2 * w, 1, 8, inner_v=True))

    # 이달 체크 포인트 머리글
    reqs.append({"mergeCells": {"range": _rng(sid, 3, 4, PANEL_COL, last_col), "mergeType": "MERGE_ALL"}})
    reqs.append({"repeatCell": {"range": _rng(sid, 3, 4, PANEL_COL, last_col),
                                "cell": {"userEnteredValue": {"stringValue": "이달 체크 포인트"},
                                         "userEnteredFormat": {"backgroundColor": HDR_FILL, "horizontalAlignment": "CENTER",
                                                               "verticalAlignment": "MIDDLE", "textFormat": {"bold": True, "fontSize": 13}}},
                                "fields": "userEnteredValue,userEnteredFormat"}})
    reqs.append(_box(sid, 3, 4, PANEL_COL, last_col))

    batches = [reqs]
    for b, (es, start, header) in enumerate(blocks):
        c0 = PANEL_COL + 5 * b
        text, runs = block(es, start, header)
        cell = {"userEnteredValue": {"stringValue": text},
                "userEnteredFormat": {"wrapStrategy": "WRAP", "verticalAlignment": "TOP", "textFormat": {"fontSize": 9}}}
        if runs:
            cell["textFormatRuns"] = runs
        batches.append([
            {"mergeCells": {"range": _rng(sid, 4, end_row, c0, c0 + 4), "mergeType": "MERGE_ALL"}},
            {"updateCells": {"start": {"sheetId": sid, "rowIndex": 4, "columnIndex": c0}, "rows": [{"values": [cell]}],
                             "fields": "userEnteredValue,userEnteredFormat,textFormatRuns"}},
            _box(sid, 4, end_row, c0, c0 + 4),
        ])
    return batches, {"content_px": px, "blocks": [[e[0].name for e in es] for es, _, _ in blocks]}


def reported_quarter(d):
    """발표일 기준으로 몇 분기 실적인지 (1~3월 발표 -> 4분기)."""
    return (d.month - 1) // 3 or 4


def default_note(d):
    return f"{reported_quarter(d)}분기 실적 발표 예정"


def parse_date(s):
    """'2026-10-22', '2026.10.22', '2026. 10. 22', '2026/10/22', date 객체 모두 허용."""
    import re
    if isinstance(s, dt.datetime):
        return s.date()
    if isinstance(s, dt.date):
        return s
    y, m, d = map(int, re.findall(r"\d+", str(s))[:3])
    return dt.date(y, m, d)
