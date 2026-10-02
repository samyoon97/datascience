# 실적 캘린더 자동화

구글 드라이브 `실적 캘린더` 폴더에 넣은 **실적 발표 예정일**과 **재무 엑셀**을 읽어
구글 시트 "실적 캘린더 2026" 의 월별 달력과 "이달 체크 포인트"를 자동으로 다시 그립니다.

## 사용자가 하는 일
```
실적 캘린더/
  실적예정일/26년 3분기/<아무 이름>.xlsx      A열 발표일(예: 10월 22일), B열 기업명, C열 내용(선택)
  재무데이터/26년 3분기/<기업명> (단위 억, %배).xlsx   CHECK/FnGuide 에서 받은 엑셀
```
1. 분기마다 두 폴더 안에 `26년 4분기` 처럼 분기 폴더를 만들고 파일을 넣습니다. (하위 폴더가 더 있어도 됩니다)
2. 재무 파일 이름은 `기업명 (단위 억, %배).xlsx` 처럼 **기업명으로 시작**하고, 단위가 십억이면 `단위 십억` 을 적어 둡니다.
3. Claude 에게 **"실적 캘린더 업데이트해줘"** 라고 말합니다.

기업명 띄어쓰기·오타(예: `HLB 제약`, `퓨쳐켐`)는 자동으로 맞추고, 맞춘 내역을 알려 드립니다.

## Claude 가 하는 일
`.claude/skills/earnings-calendar/SKILL.md` 참고. 드라이브 목록 → 파일 읽기 →
`python -m earnings_calendar build` → 생성된 요청을 시트에 전송 → 확인/보고.

## 구조
```
earnings_calendar/
  drive_input.py    드라이브 폴더 구조, 발표일·분기·파일명 해석, 기업명 보정
  loader.py         CHECK/FnGuide 엑셀(또는 드라이브 텍스트) 파싱, 회계기준 주석
  formatting.py     조/억 표기, YoY(흑전/적전/적자축소/적자확대)
  panel.py          체크 포인트 텍스트·서식, 칸 나누기
  sheet_requests.py 월 탭 전체(달력+체크 포인트) Sheets 요청 생성
  gcal.py           구글 캘린더 일정
  cli.py            plan / build 명령
config/
  sheets.json   시트·드라이브 폴더 ID, 월 탭 sheetId, 탭별 칸 높이
  colors.json   기업 브랜드 색
  aliases.json  기업명 표기 변형
  notes.json    수동 주석(자동 주석보다 우선)
  units.json    단위 강제 보정
```

```bash
python -m earnings_calendar build --drive-dir drive --out out
python -m pytest -q tests
```
