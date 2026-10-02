"""구글 캘린더 일정(종일) 페이로드 생성."""
import datetime as dt

from .formatting import rgb
from .panel import company_parts

# Google Calendar 이벤트 색상 프리셋 (colorId -> hex)
EVENT_COLORS = {
    "1": "7986CB", "2": "33B679", "3": "8E24AA", "4": "E67C73", "5": "F6BF26", "6": "F4511E",
    "7": "039BE5", "8": "616161", "9": "3F51B5", "10": "0B8043", "11": "D50000",
}


def nearest_color_id(hex_color):
    c = rgb(hex_color)
    def dist(h):
        o = rgb(h)
        return sum((c[k] - o[k]) ** 2 for k in c)
    return min(EVENT_COLORS, key=lambda k: dist(EVENT_COLORS[k]))


def event(date, name, note, color, fin=None, fin_note=None):
    desc = ""
    if fin is not None:
        lines = "".join(t for t, _, _ in company_parts(1, fin, color, fin_note)).splitlines()
        desc = "\n".join(l.strip() for l in lines[1:] if l.strip())
    return {
        "summary": f"{name}: {note}",
        "start": {"date": date.isoformat()},
        "end": {"date": (date + dt.timedelta(days=1)).isoformat()},
        "colorId": nearest_color_id(color),
        "description": desc,
    }
