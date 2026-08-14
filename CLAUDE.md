# kt-ir — KT IR 자료 축적

kt.com IR 데이터 페이지(`m.corp.kt.com/html/investors/resources/data.html`)에서
**프레젠테이션**(NDR·실적 발표 자료), **재무 데이터**, **가입자 현황** 자료를
정기적으로 내려받아 구조화된 메타데이터와 원본 파일로 축적한다.

**아직 서버가 없다. 일단은 크롤러 스크립트 + GitHub Actions 기반 정기 실행으로 시작한다.**

## IR 데이터 페이지 구조

- 모바일 페이지: `https://m.corp.kt.com/html/investors/resources/data.html`
- 탭: 가입자 현황 · 재무 데이터 · 프레젠테이션
- 목록 JS 동작: `rowCount=10`, 페이지네이션 있음, `params` 기반 로딩
- 실제 목록 엔드포인트는 `sub.js`·`mKTGlobal.js` 외에 데이터 페이지 내부의 `init()`/`load()` 루틴에서 결정됨

## 저장소에 없는 것

- 원본 PDF·PPT 등 바이너리 실적자료는 **용량·라이선스 이슈로 저장소에 커밋하지 않는다.**
  - 축적 대상은 **메타데이터**(날짜·구분·자료명·파일명·다운로드 URL·수집 일시) 중심으로 둔다.
  - 원본 파일은 별도 저장소/외장 저장소를 고려한다 — 결정되면 이 문서에 갱신.

## 시크릿 (아직 없음)

- 필요해지면 `.env` 또는 GitHub Actions 시크릿으로 둔다.
- 크롤러 인증·쿠키 처리가 필요하면 여기서 논의한다.

## Qwen 위임 정책 ★

**전 프로젝트 공통 정책은 노트북 최상위 `~/CLAUDE.md`의 "0.6 나는 PM, 로컬 Qwen은 초·중급 프로그래머" 참고.**
요약: 코딩은 원칙적으로 Qwen이 먼저 하고 Claude가 검증한다. 인터페이스·데이터 모델 설계, 동시성/에러 처리 전략, 디버깅, 여러 파일에 걸친 변경은 Claude가 직접 한다.

호출: `./scripts/ask_qwen.sh "명세"` 또는 `-f spec.md` (원본은 `voxbot/scripts/ask_qwen.sh`, 없으면 복사해 온다).
Qwen 출력은 반드시 검토 후 커밋하고, 위임할 때마다 `~/qwen-delegation-log.md`에 성과를 기록한다(당분간 유지).
