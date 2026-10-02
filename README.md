# 실적 캘린더 자동화

구글 시트 "실적 캘린더 2026" 의 월별 달력과 "이달 체크 포인트"를 일정표 + 재무 엑셀로부터 자동 생성합니다.

## 사용자가 하는 일
1. 시트의 **`입력` 탭**에 `발표일 | 기업명 | 내용(선택) | 색상(선택)` 을 한 줄씩 적습니다.
2. CHECK / FnGuide 에서 받은 재무 엑셀을 구글 드라이브 **`실적 캘린더/재무데이터`** 폴더에 **`기업명.xlsx`** 로 저장합니다.
   (구글 드라이브 데스크톱을 쓰면 PC 폴더에 저장만 해도 올라갑니다.)
3. Claude 에게 **"실적 캘린더 업데이트해줘"** 라고 말합니다.

## Claude 가 하는 일
`.claude/skills/earnings-calendar/SKILL.md` 참고. 요약하면:
일정 읽기 → 재무 파일 받기 → `python -m earnings_calendar build` → 생성된 요청을 시트에 전송 → 확인/보고.

## 구조
```
earnings_calendar/
  loader.py         CHECK/FnGuide 엑셀 파싱(양식·단위·회계기준 자동 판정)
  formatting.py     조/억 표기, YoY(흑전/적전/적자축소/적자확대)
  panel.py          체크 포인트 텍스트·서식, 칸 나누기
  sheet_requests.py 월 탭 전체(달력+체크 포인트) Sheets 요청 생성
  gcal.py           구글 캘린더 일정 페이로드
  cli.py            build / import-schedule 명령
config/
  sheets.json   시트·폴더 ID, 월 탭 sheetId, 탭별 칸 높이, 건너뛸 달
  schedule.csv  '입력' 탭 캐시
  colors.json   기업 브랜드 색
  notes.json    수동 주석(자동 주석보다 우선)
```

```bash
python -m earnings_calendar build --fin-dir <재무폴더> --out out
python -m pytest -q tests
```
