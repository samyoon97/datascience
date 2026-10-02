# datascience

실적 캘린더 자동화 저장소. 사용자는 한국어로 대화한다.

- 실적 캘린더 갱신 요청(일정 추가, 재무 엑셀 업로드, "업데이트해줘")은 `.claude/skills/earnings-calendar/SKILL.md` 절차를 따른다.
- 코드: `earnings_calendar/` (엑셀 파싱 → 체크 포인트 텍스트 → Sheets batchUpdate 요청 JSON 생성).
- 설정: `config/` (시트/폴더 ID, 일정 캐시, 브랜드 색, 수동 주석, 단위 보정).
- 테스트: `python -m pytest -q tests` (pytest 가 없으면 `pip install pytest openpyxl`).
- 재무 엑셀 원본(CHECK/FnGuide 데이터)은 커밋하지 않는다.
