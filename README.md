# kt-ir — KT IR 자료 축적

KT IR 자료(프레젠테이션·재무 데이터·가입자 현황)를 kt.com 공개 IR 데이터 페이지에서
정기적으로 수집해 **메타데이터**로 축적한다.

- 저장소: `puhapuru/kt-ir` (비공개)
- 수집 대상: `https://m.corp.kt.com/html/investors/resources/data.html`
- 실행 방식: `collect.py` + GitHub Actions 정기 실행
- 축적물: `metadata/ir_metadata.json` (원본 파일은 저장소에 커밋하지 않음)

## 수집 대상

모바일 IR 데이터 페이지의 세 탭이 수집 대상이다.

| 구분 (genlCtgType) | 이름 | 대표 자료 |
|---|---|---|
| 01 | 가입자 현황 | IR Factsheet (월별 XLSX) |
| 02 | 재무 데이터 | Financial Indicator (분기별 XLSX) |
| 03 | 프리젠테이션 | NDR·실적 발표 자료 (분기별 PDF) |

## API (실제 확인된 엔드포인트)

### 목록 조회

```
POST https://m.rdi.kt.com/corp/reports/v1.0/BS00000008/files
Content-Type: application/x-www-form-urlencoded

genlCtgType=03&limit=100&offset=1&page=1
```

- `genlCtgType`: 01(가입자현황) / 02(재무데이터) / 03(프리젠테이션)
- `limit` / `offset` / `page`: 페이지네이션
- `yyInfo`: (선택) 연도 필터 예 `2026`
- 응답 `data.reportList[]` 에 `bno`, `btitle`, `regDate`, `atcFileList[0].saveFilePath + saveFileNm` 등 포함

### 연도 목록

```
POST https://m.rdi.kt.com/corp/reports/v1.0/BS00000008/years
genlCtgType=03
```

### 실제 파일 다운로드

```
https://corp.kt.com/attach/irdata/<bno>/<saveFileNm>
```

예: `https://corp.kt.com/attach/irdata/10893/2Q26_KT_NDR_PT_KOR_0811_FF.pdf`

파일명에 공백 등 있으면 URL 인코딩 필요. 브라우저에서 직접 열면 PDF·XLSX가 정상 다운로드된다.

> **주의**: `/attach/record/<년도>/<파일명>` 패턴은 사용하지 않는다. 200을 반환하지만 실제 파일이 아니라 HTML(1832바이트)이다.

### 옛 실적자료(2021년 이전) 실제 파일 경로

IR 데이터 페이지(`data.html`) API로 조회되는 초창기 항목(bno 60~ 등)은
목록에는 실존하지만 **실제 파일 다운로드 URL(`/attach/irdata/<bno>/...`)이
현재 1832바이트 HTML을 반환**한다 — "주의" 절과 같은 함정이다.

2021년(포함) 이전 분기 실적 발표 PDF·XLSX는 아래 **old 실적자료 페이지**에서
연도 행 → 분기 셀 안의 다운로드 링크로 실제 파일을 받을 수 있다.

- 페이지: `https://m.corp.kt.com/html/investors/resources/earnings_old_data.html`
- 연도 `<select>`(id=searchYear)에서 목표 연도를 선택한 뒤 표시되는 표에서
  각 분기 셀의 "다운로드" 링크를 확인한다.
- URL 호스트/경로가 IR 데이터 페이지 API의 `/attach/irdata/<bno>/...`와 다르다
  (`/data/attach/<attachNo>/...` 형태).

**실제 파일 다운로드 예 — 2011년(프레젠테이션/NDR 국문)**

| 분기 | 파일명 | 실제 다운로드 URL |
|------|--------|-------------------|
| 1Q | `kthp1325772162638.pdf` | `https://m.corp.kt.com/data/attach/207/kthp1325772162638.pdf` |
| 2Q | `KT_FY11_2Q_Earnings_Kor_FIN.pdf` | `https://m.corp.kt.com/data/attach/207/KT_FY11_2Q_Earnings_Kor_FIN.pdf` |
| 3Q | `kthp1320663199637.pdf` | `https://m.corp.kt.com/data/attach/207/kthp1320663199637.pdf` |
| 4Q(PDF) | `kthp132919182992.pdf` | `https://m.corp.kt.com/data/attach/207/kthp132919182992.pdf` |
| 4Q(XLSX) | `kthp1328489845513.XLSX` | `https://m.corp.kt.com/data/attach/document/kthp1328489845513.XLSX` |

- 크로미움으로 위 페이지를 열어 연도 행을 선택한 뒤 분기 셀의 `download` 링크를
  클립보드로 얻거나, 위 표처럼 수동 확인해 `collect.py --download` 대안 경로로
  내려받는다.
- 내려받은 파일은 `data/`에 임시 저장하며 커밋 대상이 아니다(`.gitignore`).
- 메타데이터를 보강할 값(bno와 old 페이지 attachNo의 대응 등)은 별도 이슈로 다룬다.


## 메타데이터 스키마

`metadata/ir_metadata.json` 의 항목 하나:

```json
{
  "bno": "10893",
  "genlCtgType": "03",
  "genlCtgTypeNm": "프리젠테이션",
  "btitle": "2026년 2분기 국문 NDR 자료",
  "regDate": "2026.08.12 09:52:17:359",
  "fileNo": "12027",
  "saveFileNm": "2Q26_KT_NDR_PT_KOR_0811_FF.pdf",
  "saveFileSize": "1002945",
  "downloadUrl": "https://corp.kt.com/attach/irdata/10893/2Q26_KT_NDR_PT_KOR_0811_FF.pdf",
  "collectedAt": "2026-08-14T08:48:07.864653+00:00"
}
```

루트에 `lastCollected`, `apiVersion`, `counts`(탭별 건수) 도 함께 둔다.

## 실행 방법

```bash
# 전체 수집 (기본)
python3 collect.py

# 특정 탭만
python3 collect.py --tab 03              # 프리젠테이션만
python3 collect.py --tab 01 --year 2026 # 가입자현황 2026년분만

# 목록만 출력 (저장하지 않음)
python3 collect.py --list-only

# 신규 항목 미리 보기 (저장하지 않음)
python3 collect.py --dry-run

# 신규 파일을 data/에 임시 다운로드 (검증용, 커밋 대상 아님)
python3 collect.py --download
```

`data/` 폴더는 `.gitignore` 로 무시한다. 원본 파일은 `data/`에 임시로 내려받을 수 있지만, 커밋하지 않는다.

## 시크릿

지금은 시크릿이 필요 없다. KT IR 공개 자료라 인증 없이 수집된다.

## 저장소 구성

```
kt-ir/
├── collect.py                 # 수집 스크립드
├── metadata/
│   └── ir_metadata.json       # 축적 메타데이터 (커밋 대상)
├── data/                      # 원본 파일 임시 저장 (gitignore)
├── .github/workflows/
│   └── kt-ir-collect.yml      # GitHub Actions 정기 실행
├── .gitignore
├── README.md
└── CLAUDE.md
```

## Qwen 위임 정책

코딩은 원칙적으로 Qwen이 먼저 하고 Claude가 검증한다. 더 상세한 정책은 각 프로젝트의 CLAUDE.md와 노트북 최상위 `~/CLAUDE.md` "0.6" 절 참고.

호출: `./scripts/ask_qwen.sh "명세"` 또는 `-f spec.md` (원본은 `voxbot/scripts/ask_qwen.sh`, 없으면 복사해 온다). 위임 결과는 검토 후 커밋한다.
