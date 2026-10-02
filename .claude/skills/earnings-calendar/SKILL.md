---
name: earnings-calendar
description: 실적 캘린더(구글 시트 "실적 캘린더 2026")를 갱신한다. 사용자가 "실적 캘린더 업데이트", "캘린더 반영", "재무 데이터 올렸어", 기업/발표일 추가·변경, 재무 엑셀(CHECK/FnGuide) 업로드를 언급하면 사용.
---

# 실적 캘린더 업데이트

사용자는 한국어로 대화한다. 답변도 한국어로.

## 무엇을 만드는가
구글 시트 `config/sheets.json` 의 `spreadsheet_id` 에 월별 탭(`YYYY.MM`)이 있다.
- 왼쪽: 달력. 날짜 칸에 `기업명: N분기 실적 발표 예정` (기업명은 브랜드 색, 굵게). 모든 주의 칸 높이는 같다.
- 오른쪽(J열~): "이달 체크 포인트". 발표일 순으로 기업별 `기간 매출(YoY)/ 영업익(YoY)/ 순익(YoY)`
  — 컨센서스 분기(E) 먼저, 그 아래 최근 확정 5개 분기. 단위 조/억. 증가 빨강(E60012), 감소 파랑(0070C0), 없음 회색.
  YoY = (당기-전기)/|전기|, 부호가 바뀌면 흑전/적전, 둘 다 적자면 적자축소/적자확대 태그.
  줄이 넘치면 아래로 늘리지 않고 오른쪽에 새 칸(4열+간격 1열)을 만든다.
모든 로직은 `earnings_calendar/` 에 있다. 손으로 텍스트를 만들지 말고 반드시 코드를 실행해 생성한다.

## 입력 위치
1. **일정**: 시트의 `입력` 탭 (A 발표일, B 기업명, C 내용(선택), D 색상 HEX(선택)). 이게 원본이다.
2. **재무 엑셀**: 구글 드라이브 `실적 캘린더/재무데이터` 폴더(`fin_folder_id`)에 `기업명.xlsx`.
   - 사용자가 채팅에 직접 올린 파일(`/root/.claude/uploads/...`)도 같은 방식으로 쓴다.
   - 파일 이름이 깨져 있으면(예: `3991285e-____.xlsx`) 숫자로 기업을 추정한다:
     매출 규모, 시가총액, EPS로 역산한 주식 수(순이익/EPS), 영업이익률, 별도/연결 기준, 상장 시점(시가총액 시작 분기).
     `입력` 탭의 기업 중 아직 재무가 없는 기업 후보와 대조하고, 근거를 사용자에게 표로 보고한다. 애매하면 물어본다.

## 절차
1. `mcp__Google_Sheets__get_values` 로 `'입력'!A1:D300` 을 읽어 scratchpad 에 JSON 저장 →
   `python -m earnings_calendar import-schedule <json>` (config/schedule.csv 갱신).
2. 재무 파일 모으기 → scratchpad 의 `fin/` 디렉터리에 `기업명.xlsx` 로 둔다.
   - 드라이브: `mcp__Google_Drive__search_files` (`parentId = '<fin_folder_id>'`) → 각 파일
     `mcp__Google_Drive__download_file_content` → base64 를 파일로 저장 후 `base64 -d > fin/기업명.xlsx`.
     파일 하나 ~11KB 이므로 이번에 필요한(새로 추가/수정된) 기업만 받는다. modifiedTime 으로 판단.
   - 이미 반영된 기업도 탭을 다시 그릴 때 필요하므로, 해당 월의 모든 기업 파일이 `fin/` 에 있어야 한다.
3. 현재 탭 목록 확인: `mcp__Google_Sheets__get_spreadsheet` (fields `sheets.properties.sheetId`, `sheets.properties.title`).
   `config/sheets.json` 의 `tabs` 와 다르면 고친다(월 탭만, `입력` 탭 제외).
4. 빌드: `python -m earnings_calendar build --fin-dir <scratchpad>/fin --out <scratchpad>/out [--months 2026.12]`
   - 출력 report 의 `missing_financials` / `no_financials` 는 사용자에게 알린다(그 기업은 달력에만 나오고 체크 포인트엔 빠짐).
   - 새 기업에 브랜드 색이 없으면 기본 남색이 들어간다. 기업 CI 색을 골라 `config/colors.json` 에 추가하고 다시 빌드.
   - 회계 기준 주석은 자동 생성된다. 자동 문구가 부적절하면 `config/notes.json` 에 수동 문구를 넣는다.
   - 단위 자동 판정(`구분` 양식=10억원 ×10, `항목` 양식=억원)이 틀리면 `config/units.json` 에 `{"기업명": 1}`.
5. 전송: 바뀐 월만, `out/<탭>/` 의 JSON 을 **파일명 순서대로** 하나씩 `cat` 해서
   `mcp__Google_Sheets__update_spreadsheet` 의 `requests` 로 그대로 보낸다. 내용을 손으로 고치지 않는다.
   - 새 탭(report 의 `new_tabs`)은 00 파일이 `addSheet`(sheetId=YYYYMM) 를 포함한다. 성공하면 `config/sheets.json` tabs 에 추가.
6. 확인: `get_values` 로 각 칸 첫 줄(예: `'2026.11'!J5`, `O5` ...)을 읽어 기업 순서가 맞는지 본다.
7. (선택) 구글 캘린더: `config/sheets.json` 의 `calendar_id` 가 있으면 `out/calendar_events.json` 의 일정을
   `mcp__Google_Calendar__create_event` 로 등록(이미 있는 일정은 search 후 update). 없으면 사용자에게 "실적 캘린더"
   캘린더를 만들어 달라고 안내(Claude 는 캘린더 자체를 만들 수 없음).
8. 변경한 config 는 커밋/푸시한다. 재무 엑셀 원본은 저장소에 올리지 않는다(.gitignore).
9. 결과 보고: 반영한 기업, 판단 근거(파일 이름이 깨졌던 경우), 칸 구성, 남은 미반영 기업, 시트 링크.

## 주의
- 탭은 매번 통째로 다시 그린다(idempotent). 사용자가 탭에 손으로 적은 내용은 지워질 수 있으니, 그런 흔적이 보이면 먼저 묻는다.
- `content_px`(달력 일정 칸 높이)는 `config/sheets.json` 에 탭별로 고정돼 있다. 새 달은 일정 수에 맞춰 자동 계산.
- `skip_months` 의 달(예: 9/30 IR 하나뿐인 2026.09)은 탭을 만들지 않는다.
- 페이로드가 커서 한 번에 여러 파일을 합치지 말 것. 파일 하나 = 호출 하나.
