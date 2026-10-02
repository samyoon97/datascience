# datascience

실적 캘린더 자동화 저장소. 사용자는 한국어로 대화한다.

- 실적 캘린더 갱신 요청("업데이트해줘", 드라이브에 일정/재무 파일을 넣었다는 말)은 `.claude/skills/earnings-calendar/SKILL.md` 절차를 따른다.
- 입력은 구글 드라이브 `실적 캘린더/실적예정일/<분기>/`, `실적 캘린더/재무데이터/<분기>/` 폴더다.
- 코드: `earnings_calendar/` (드라이브 파일 파싱 → 체크 포인트 텍스트 → Sheets batchUpdate 요청 JSON 생성).
- 설정: `config/` (시트/폴더 ID, 브랜드 색, 기업명 별칭, 수동 주석, 단위 보정).
- 테스트: `python -m pytest -q tests` (pytest 가 없으면 `pip install pytest openpyxl`).
- 재무 엑셀 원본(CHECK/FnGuide 데이터)과 내려받은 파일은 커밋하지 않는다.
