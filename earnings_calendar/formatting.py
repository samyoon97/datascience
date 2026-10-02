"""Number/YoY formatting shared by the check-point panel and calendar events."""

UP, DOWN, MUTE, BLACK = "E60012", "0070C0", "7F7F7F", "000000"


def amt(v):
    """억원 값을 '1.23조' / '1,234억' / '3.4억' 형태로."""
    if v is None:
        return "-"
    if abs(v) >= 10000:
        return f"{v / 10000:.2f}조"
    if abs(v) >= 10:
        return f"{round(v):,}억"
    return f"{v:.1f}억"


def yoy(cur, prev):
    """전년 동기 대비 증감률. (cur-prev)/|prev|, 부호가 바뀌거나 둘 다 적자면 태그를 붙인다.

    Returns (text, hex color).
    """
    if cur is None or prev is None or prev == 0:
        return "-", MUTE
    p = (cur - prev) / abs(prev) * 100
    color = UP if p >= 0 else DOWN
    if prev > 0 and cur > 0:
        return f"{p:+,.1f}%", color
    if prev < 0 < cur:
        tag = "흑전"
    elif cur <= 0 < prev:
        tag = "적전"
    else:
        tag = "적자축소" if abs(cur) < abs(prev) else "적자확대"
    return f"{p:+,.1f}%, {tag}", color


def rgb(hex_color):
    h = hex_color.lstrip("#")
    return {"red": int(h[0:2], 16) / 255, "green": int(h[2:4], 16) / 255, "blue": int(h[4:6], 16) / 255}


def rgb_compact(hex_color):
    """Sheets API 페이로드를 줄이기 위해 0인 채널은 생략."""
    return {k: round(x, 3) for k, x in rgb(hex_color).items() if x}
