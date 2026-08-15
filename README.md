# kt-ir — KT IR 자료 축적

KT IR 페이지의 **프레젠테이션(NDR)** · **재무 데이터** · **가입자 현황(Factsheet)**
을 정기적으로 받아, 원본과 추출 수치를 함께 쌓는다. 목적은 **분기 실적 분석**이다.

## 무엇이 어디에 있나

```
raw/2026Q2/2Q26_KT_NDR_PT_KOR.pdf   원본 그대로 (전체 약 300MB, 분기당 1~2MB)
data/reports.csv                     자료 원장 — 어디서 받았고 무엇인지
data/facts.csv                       ★ 추출한 수치 (long 형식)
data/metrics.csv                     지표 사전 (표준 id ↔ 뜻)
build/kt_ir.sqlite                   조회용. CSV 에서 만든다 (커밋 안 함)
```

**CSV 가 정본이고 SQLite 는 산출물이다.** 텍스트로 둬야 git diff 가 읽히고
사람이 리뷰할 수 있다. 질의는 SQL 이 편하니 필요할 때 만들어 쓴다.

## 쓰는 법

```bash
python3 collect.py --dry-run              # 새로 올라온 것만 본다
python3 collect.py --download             # 신규 원본을 raw/ 에 받는다
python3 collect.py --download --all       # 누적 전체 (이미 받은 것은 건너뛴다)

python3 -m venv .venv && .venv/bin/pip install openpyxl     # 처음 한 번
.venv/bin/python scripts/extract_findicator.py --report     # 진단만
.venv/bin/python scripts/extract_findicator.py              # facts.csv 를 쓴다

python3 scripts/build_db.py --check       # CSV → SQLite, 끊긴 참조 점검
python3 scripts/test_period.py            # 기간 파싱 회귀 시험 (인터넷 안 씀)
```

지금 담긴 것: **손익·CAPEX 14,636개** (2008~2025, 연결·별도). Financial
Indicator(XLSX) 59개 분기에서 뽑았다. ARPU·가입자 수는 Factsheet 에 있고
아직 안 뽑았다.

```bash
sqlite3 build/kt_ir.sqlite \
  "SELECT period, value FROM facts WHERE metric_id='arpu_wireless' ORDER BY period"
```

## `facts.csv` — 수치 한 개가 한 줄

```
report_id,period,period_type,basis,consolidation,metric_id,label_raw,value,unit,page,confidence
ndr_2026Q2_10893,2026Q2,quarter,단일분기,연결,revenue_total,영업수익,67890,억원,4,verified
```

| 칸 | 뜻 |
|---|---|
| `report_id` | **어느 보고서가 그렇게 말했는지.** 재작성 추적의 핵심 |
| `period` | `2026Q2`(분기) 또는 `2026-06`(월) |
| `basis` | `단일분기` / `누적` — KT 는 누적으로 싣는 표가 많다 |
| `consolidation` | `연결` / `별도` |
| `metric_id` | 표준 지표 id (`metrics.csv` 참조) |
| `label_raw` | **그 보고서의 실제 표기.** `무선서비스매출` ↔ `무선사업 수익` |
| `page` | 근거 페이지. 인용할 때 필요하다 |
| `confidence` | `auto`(기계 추출) / `verified`(사람 확인) |

### 넓은 표로 만들지 않은 이유

분기가 행이고 지표가 열인 표는 **KT 가 지표 이름을 바꾸거나 사업부를 재편할
때마다 깨진다.** 2010년부터 15년치를 다루면 반드시 겪는다.

### 같은 분기가 여러 줄인 것은 정상이다 ★

**KT 는 과거 수치를 재작성한다.** K-IFRS 전면 도입(2011), IFRS15 수익인식
변경(2018), KT클라우드 분할(2022), 연결 범위 변동 — 그때마다 이전 분기 매출이
바뀐다. `2015Q3 매출 = X` 라고 한 줄만 저장하면 나중에 왜 숫자가 안 맞는지
영영 알 수 없다.

그래서 **값이 아니라 "어느 보고서가 뭐라고 했는지"** 를 저장한다. 최신 기준이
필요하면 `published_at` 이 가장 늦은 보고서를 고르면 되고, 재작성 자체를
분석 재료로 쓸 수도 있다.

## 자료 종류와 기간

`scripts/period.py` 가 제목·파일명에서 뽑는다. 25년치라 표기가 여러 번 바뀌었다.

| `doc_kind` | 주기 | 건수 | 무엇이 들었나 |
|---|---|---|---|
| `ndr` | 분기 | 74 | 실적 발표 자료(PDF). 사업부별 매출·CAPEX |
| `financial_indicator` | 분기 | 59 | **XLSX — 표라서 추출이 쉽다.** 손익·재무 |
| `factsheet` | **월** | 298 | 가입자 수·ARPU |
| `conference` | 없음 | 51 | 2005년 이전 로드쇼·주주방문 자료 |

**컨퍼런스 자료에는 기간을 붙이지 않는다.** 제목의 날짜는 행사일이지 실적
기간이 아니다 — `해외 주요 주주방문(2004.2)` 를 2004Q1 로 적으면 그 분기를
찾을 때 엉뚱한 자료가 섞인다.

## 수치는 어디서 가져오는 게 나은가

| 무엇 | 어디서 | 왜 |
|---|---|---|
| 매출·영업이익·비용·자산·인건비 | **DART OpenAPI** | XBRL 구조화, 무료, 재작성 이력까지. PDF 파싱 불필요 |
| ARPU·가입자 수·무선/유선 세부·CAPEX | **IR 자료** | DART 에 없는 영업지표 |

재무 수치를 PDF 에서 긁는 것은 먼 길이다. `financial_indicator` 가 XLSX 라
그쪽이 IR 자료 중에서는 가장 쉽다.

## 추출에서 가장 조심할 것 — 단위 ★

**머리글의 `(Billion KRW)` 는 거짓이다.** 실제 단위가 **칸마다** 다르다.
2020Q4 별도 시트 실측:

    Revenue       2015 = 16942.4      2016 = 17,028,868   ← 같은 줄인데 바뀐다
    Capex         2015 = 2397         2016 = 2359         ← 이 줄은 안 바뀐다
    Depreciation  2015 = 3010.2       2016 = 3,005,383    ← 이 줄은 바뀐다

열로도 행으로도 못 가른다. 그래서 **값 하나하나**를 지표별 상식 범위
(`METRIC_RANGE_억`)에 견주어 십억원인지 백만원인지 정한다. 둘 다 맞거나 둘 다
안 맞으면 **그 값을 버리고 경고를 남긴다** — 넘겨짚느니 빠지는 편이 낫다.

**검산이 그물이다.** 분기 4개 합이 연간과 맞는지 본다. 1000배 어긋나면
`[단위의심]`(추출 잘못), 몇 % 어긋나면 `[값차이]`(KT 가 연간만 재작성한 것)로
갈라 센다. 지금 **단위의심 0건 · 값차이 6건**이고, 그 6건은 2023년 서비스/상품
매출 재분류라 합계는 맞는다(263,762 = 263,763).

## 조심할 것

**같은 파일을 다시 받아 덮어쓰지 않는다.** git 은 바이너리를 버전마다 통째로
저장한다. 매번 다시 받으면 1비트만 달라도 사본이 계속 쌓인다. IR 자료는 한 번
공시되면 안 바뀌므로 `download_file()` 이 **파일이 있으면 건너뛴다.**

**서버가 200 으로 오류 페이지를 준다.** 실제로 `1,832바이트` 짜리 HTML 이
`.pdf` 이름을 달고 들어와 있었다. 최소 크기(5,000바이트)와 파일 앞머리
(`%PDF`·`PK`·OLE)를 둘 다 본다.

**`.gitignore` 는 기본 차단 + 필요한 것만 열기다.** `raw/**` 와 `data/*.csv`
만 열려 있다. 다른 폴더에 떨어진 자료 파일이 실수로 커밋되지 않게 하려는 것.
