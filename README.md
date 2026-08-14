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


### 프레젠테이션 축적 목록 (2010~2026, 연도별·분기별)

현재 `metadata/ir_metadata.json`에 쌓인 프레젠테이션(genlCtgType=03) 중
2010~2026년 항목을 제목 기준 연도·분기로 정리했다 (66건).

> **실제 파일 위치 주의**
> - 2010~2011년 항목(bno 60~68)은 IR 데이터 페이지 API `/attach/irdata/<bno>/...`
>   URL이 현재 실제 파일 대신 1832바이트 HTML을 반환할 수 있다.
>   실제 파일은 [옛 실적자료 페이지](#옛-실적자료2021년-이전-실제-파일-경로)에서 확인한다.
> - 2012년 이후 항목(bno 68~)은 API URL이 실제 PDF로 연결된다(수집 시 확인 필요).

| 연도 | 분기 | 제목 | bno | 파일명 | API URL |
|------|------|------|-----|--------|--------|
| 2010 | 1Q | 2010년 1분기 국내 NDR 자료 | 61 | olleh_kt_IR_PT_1Q10_Final(Korean).pdf | https://corp.kt.com/attach/irdata/61/olleh_kt_IR_PT_1Q10_Final%28Korean%29.pdf |
| 2010 | 2Q | 2010년 2분기 국내 NDR 자료 | 62 | olleh_kt_IR_PT_2Q10_실적발표_Final.pdf | https://corp.kt.com/attach/irdata/62/olleh_kt_IR_PT_2Q10_%EC%8B%A4%EC%A0%81%EB%B0%9C%ED%91%9C_Final.pdf |
| 2010 | 3Q | 2010년 3분기 국내 NDR 자료 | 63 | olleh_kt_IR_PT_3Q10_실적발표_kor_Final.pdf | https://corp.kt.com/attach/irdata/63/olleh_kt_IR_PT_3Q10_%EC%8B%A4%EC%A0%81%EB%B0%9C%ED%91%9C_kor_Final.pdf |
| 2010 | 4Q | 2010년 4분기 국내 NDR 자료 | 64 | IR_PT_2011_02_14_KOR_1.pdf | https://corp.kt.com/attach/irdata/64/IR_PT_2011_02_14_KOR_1.pdf |
| 2011 | 1Q | 2011년 1분기 국내 NDR 자료  | 65 | kthp1314690005566.pdf | https://corp.kt.com/attach/irdata/65/kthp1314690005566.pdf |
| 2011 | 2Q | 2011년 2분기 국내 NDR 자료  | 66 | kthp1314690030656.pdf | https://corp.kt.com/attach/irdata/66/kthp1314690030656.pdf |
| 2011 | 3Q | 2011년 3분기 국내 NDR 자료  | 67 | kthp1322725208014.pdf | https://corp.kt.com/attach/irdata/67/kthp1322725208014.pdf |
| 2011 | 4Q | 2011년 4분기 국내 NDR 자료 | 68 | kthp1329719441012.pdf | https://corp.kt.com/attach/irdata/68/kthp1329719441012.pdf |
| 2012 | 1Q | 2012년 1분기 국내 NDR 자료 | 69 | kthp1359009902840.pdf | https://corp.kt.com/attach/irdata/69/kthp1359009902840.pdf |
| 2012 | 2Q | 2012년 2분기 국내 NDR 자료 | 70 | kthp1359010021319.pdf | https://corp.kt.com/attach/irdata/70/kthp1359010021319.pdf |
| 2012 | 3Q | 2012년 3분기 국내 NDR 자료 | 71 | kthp1359010059593.pdf | https://corp.kt.com/attach/irdata/71/kthp1359010059593.pdf |
| 2012 | 4Q | 2012년 4분기 국내 NDR 자료 | 72 | kthp1360060814430.pdf | https://corp.kt.com/attach/irdata/72/kthp1360060814430.pdf |
| 2013 | 1Q | 2013년 1분기 국내 NDR 자료 | 73 | kthp1374028318174.pdf | https://corp.kt.com/attach/irdata/73/kthp1374028318174.pdf |
| 2013 | 2Q | 2013년 2분기 국내 NDR 자료  | 74 | kthp1380090544447.pdf | https://corp.kt.com/attach/irdata/74/kthp1380090544447.pdf |
| 2013 | 3Q | 2013년 3분기 국내 NDR 자료  | 75 | kthp1384134021865.pdf | https://corp.kt.com/attach/irdata/75/kthp1384134021865.pdf |
| 2013 | 4Q | 2013년 4분기 국내 NDR 자료  | 76 | kthp1393221600331.pdf | https://corp.kt.com/attach/irdata/76/kthp1393221600331.pdf |
| 2014 | 1Q | 2014년 1분기 국내 NDR 자료  | 77 | kthp1400576341208.pdf | https://corp.kt.com/attach/irdata/77/kthp1400576341208.pdf |
| 2014 | 2Q | 2014년 2분기 국내 NDR 자료  | 78 | kthp1407398238162.pdf | https://corp.kt.com/attach/irdata/78/kthp1407398238162.pdf |
| 2014 | 3Q | 2014년 3분기 국내 NDR 자료  | 79 | kthp1415060769335.pdf | https://corp.kt.com/attach/irdata/79/kthp1415060769335.pdf |
| 2014 | 4Q | 2014년 4분기 국내 NDR 자료  | 80 | kthp1423102199122.pdf | https://corp.kt.com/attach/irdata/80/kthp1423102199122.pdf |
| 2015 | 1Q | 2015년 1분기 국내 NDR 자료  | 81 | kthp1431407235610.pdf | https://corp.kt.com/attach/irdata/81/kthp1431407235610.pdf |
| 2015 | 2Q | 2015년 2분기 국내 NDR 자료  | 82 | kthp1439865011162.pdf | https://corp.kt.com/attach/irdata/82/kthp1439865011162.pdf |
| 2015 | 3Q | 2015년 3분기 국내 NDR 자료  | 83 | kthp1446789817467.pdf | https://corp.kt.com/attach/irdata/83/kthp1446789817467.pdf |
| 2015 | 4Q | 2015년 4분기 국내 NDR 자료 | 84 | kthp1455601198446.pdf | https://corp.kt.com/attach/irdata/84/kthp1455601198446.pdf |
| 2016 | 1Q | 2016년 1분기 국내 NDR 자료 | 85 | kthp1462880801695.pdf | https://corp.kt.com/attach/irdata/85/kthp1462880801695.pdf |
| 2016 | 2Q | 2016년 2분기 국내 NDR 자료 | 86 | kthp1471847401895.pdf | https://corp.kt.com/attach/irdata/86/kthp1471847401895.pdf |
| 2016 | 3Q | 2016년 3분기 국내 NDR 자료 | 87 | kthp1478154647388.pdf | https://corp.kt.com/attach/irdata/87/kthp1478154647388.pdf |
| 2016 | 4Q | 2016년 4분기 국내 NDR 자료 | 88 | kthp1486347210830.pdf | https://corp.kt.com/attach/irdata/88/kthp1486347210830.pdf |
| 2017 | 1Q | 2017년 1분기 국내 NDR 자료 | 89 | kthp1494585198060.pdf | https://corp.kt.com/attach/irdata/89/kthp1494585198060.pdf |
| 2017 | 2Q | 2017년 2분기 국내 NDR 자료 | 90 | kthp1501207425513.pdf | https://corp.kt.com/attach/irdata/90/kthp1501207425513.pdf |
| 2017 | 3Q | 2017년 3분기 국내 NDR 자료 | 10032 | 150994560823600009.pdf | https://corp.kt.com/attach/irdata/10032/150994560823600009.pdf |
| 2017 | 4Q | 2017년 4분기 국내 NDR 자료 | 10073 | 4Q17_KT_NDR_PT_KOR F.pdf | https://corp.kt.com/attach/irdata/10073/4Q17_KT_NDR_PT_KOR%20F.pdf |
| 2018 | 1Q | 2018년 1분기 국내 NDR 자료 | 10108 | 1Q18_NDR PT_KOR-FIN.pdf | https://corp.kt.com/attach/irdata/10108/1Q18_NDR%20PT_KOR-FIN.pdf |
| 2018 | 2Q | 2018년 2분기 국내 NDR 자료 | 10122 | 2Q18_NDR PT_KOR_f.pdf | https://corp.kt.com/attach/irdata/10122/2Q18_NDR%20PT_KOR_f.pdf |
| 2018 | 3Q | 2018년 3분기 국내 NDR 자료 | 10169 | 3Q18_NDR PT_KOR_Fin.pdf | https://corp.kt.com/attach/irdata/10169/3Q18_NDR%20PT_KOR_Fin.pdf |
| 2018 | 4Q | 2018년 4분기 국내 NDR 자료 | 10184 | 4Q18_KT_NDR_PT_KOR_f.pdf | https://corp.kt.com/attach/irdata/10184/4Q18_KT_NDR_PT_KOR_f.pdf |
| 2019 | 1Q | 2019년 1분기 국내 NDR 자료 | 10200 | 1Q19_KT_NDR_PT_KOR_FF_190509.pdf | https://corp.kt.com/attach/irdata/10200/1Q19_KT_NDR_PT_KOR_FF_190509.pdf |
| 2019 | 2Q | 2019년 2분기 국내 NDR 자료 | 10232 | 2Q19_KT_NDR_PT_KOR_FF_190808.pdf | https://corp.kt.com/attach/irdata/10232/2Q19_KT_NDR_PT_KOR_FF_190808.pdf |
| 2019 | 3Q | 2019년 3분기 국내 NDR 자료 | 10248 | 3Q19_KT_NDR_PT_KOR_fin_v3.pdf | https://corp.kt.com/attach/irdata/10248/3Q19_KT_NDR_PT_KOR_fin_v3.pdf |
| 2019 | 4Q | 2019년 4분기 국내 NDR 자료 | 10290 | 4Q19_KT_NDR_PT_KOR_FIN_0211.pdf | https://corp.kt.com/attach/irdata/10290/4Q19_KT_NDR_PT_KOR_FIN_0211.pdf |
| 2020 | 1Q | 2020년 1분기 국내 NDR 자료 | 10307 | 1Q20_KT_NDR_PT_KOR_F.pdf | https://corp.kt.com/attach/irdata/10307/1Q20_KT_NDR_PT_KOR_F.pdf |
| 2020 | 2Q | 2020년 2분기 국문 NDR 자료 | 10350 | KT 20Q2 NDR PT KOR.pdf | https://corp.kt.com/attach/irdata/10350/KT%2020Q2%20NDR%20PT%20KOR.pdf |
| 2020 | 3Q | 2020년 3분기 국문 NDR 자료 | 10383 | KT 20Q3 NDR PT KOR_F_HP.PDF | https://corp.kt.com/attach/irdata/10383/KT%2020Q3%20NDR%20PT%20KOR_F_HP.PDF |
| 2020 | 4Q | 2020년 4분기 국문 NDR 자료 | 10402 | 4Q20 KT NDR PT KOR_FIN.pdf | https://corp.kt.com/attach/irdata/10402/4Q20%20KT%20NDR%20PT%20KOR_FIN.pdf |
| 2021 | 1Q | 2021년 1분기 국문 NDR 자료 | 10425 | 1Q21 KT NDR PT KOR F.pdf | https://corp.kt.com/attach/irdata/10425/1Q21%20KT%20NDR%20PT%20KOR%20F.pdf |
| 2021 | 2Q | 2021년 2분기 국문 NDR 자료 | 10451 | 2Q21 KT NDR PT KOR_FFF.pdf | https://corp.kt.com/attach/irdata/10451/2Q21%20KT%20NDR%20PT%20KOR_FFF.pdf |
| 2021 | 3Q | 2021년 3분기 국문 NDR 자료 | 10503 | 3Q21 KT NDR PT KOR_FIN.PDF | https://corp.kt.com/attach/irdata/10503/3Q21%20KT%20NDR%20PT%20KOR_FIN.PDF |
| 2021 | 4Q | 2021년 4분기 국문 NDR 자료 | 10520 | (FFINAL)KT NDR PT 4Q21 KORv1.pdf | https://corp.kt.com/attach/irdata/10520/%28FFINAL%29KT%20NDR%20PT%204Q21%20KORv1.pdf |
| 2022 | 1Q | 2022년 1분기 국문 NDR 자료 | 10540 | KT 1Q22_NDR PT_KOR_FF.PDF | https://corp.kt.com/attach/irdata/10540/KT%201Q22_NDR%20PT_KOR_FF.PDF |
| 2022 | 2Q | 2022년 2분기 국문 NDR 자료 | 10568 | KT 2Q22_NDR PT_KOR_FIN.PDF | https://corp.kt.com/attach/irdata/10568/KT%202Q22_NDR%20PT_KOR_FIN.PDF |
| 2022 | 3Q | 2022년 3분기 국문 NDR 자료 | 10601 | KT 3Q22_NDR PT_KOR_FIN.PDF | https://corp.kt.com/attach/irdata/10601/KT%203Q22_NDR%20PT_KOR_FIN.PDF |
| 2022 | 4Q | 2022년 4분기 국문 NDR 자료 | 10615 | KT 4Q22_NDR PT_KOR_F.pdf | https://corp.kt.com/attach/irdata/10615/KT%204Q22_NDR%20PT_KOR_F.pdf |
| 2023 | 1Q | 2023년 1분기 국문 NDR 자료 | 10652 | KT 1Q23_NDR_KOR_F.pdf | https://corp.kt.com/attach/irdata/10652/KT%201Q23_NDR_KOR_F.pdf |
| 2023 | 2Q | 2023년 2분기 국문 NDR 자료 | 10679 | KT 2Q23_NDR_KOR_F.pdf | https://corp.kt.com/attach/irdata/10679/KT%202Q23_NDR_KOR_F.pdf |
| 2023 | 3Q | 2023년 3분기 국문 NDR 자료 | 10700 | KT 3Q23_NDR_KOR_F.pdf | https://corp.kt.com/attach/irdata/10700/KT%203Q23_NDR_KOR_F.pdf |
| 2023 | 4Q | 2023년 4분기 국문 NDR 자료 | 10731 | 4Q23_KT_NDR_PT_KOR_240408_FIN.pdf | https://corp.kt.com/attach/irdata/10731/4Q23_KT_NDR_PT_KOR_240408_FIN.pdf |
| 2024 | 1Q | 2024년 1분기 국문 NDR 자료 | 10752 | 1Q24_KT_NDR_PT_KOR_FF.pdf | https://corp.kt.com/attach/irdata/10752/1Q24_KT_NDR_PT_KOR_FF.pdf |
| 2024 | 2Q | 2024년 2분기 국문 NDR 자료 | 10767 | 2Q24_KT_NDR_PT_KOR_FF.pdf | https://corp.kt.com/attach/irdata/10767/2Q24_KT_NDR_PT_KOR_FF.pdf |
| 2024 | 3Q | 2024년 3분기 국문 NDR 자료 | 10794 | 3Q24_KT_NDR_PT_KOR_FF.pdf | https://corp.kt.com/attach/irdata/10794/3Q24_KT_NDR_PT_KOR_FF.pdf |
| 2024 | 4Q | 2024년 4분기 국문 NDR 자료 | 10810 | 4Q24_KT_NDR_PT_KOR_FF.pdf | https://corp.kt.com/attach/irdata/10810/4Q24_KT_NDR_PT_KOR_FF.pdf |
| 2025 | 1Q | 2025년 1분기 국문 NDR 자료 | 10824 | 1Q25_KT_NDR_PT_KOR_FFIN.pdf | https://corp.kt.com/attach/irdata/10824/1Q25_KT_NDR_PT_KOR_FFIN.pdf |
| 2025 | 2Q | 2025년 2분기 국문 NDR 자료 | 10839 | 2Q25_KT_NDR_PT_KOR_FIN.pdf | https://corp.kt.com/attach/irdata/10839/2Q25_KT_NDR_PT_KOR_FIN.pdf |
| 2025 | 3Q | 2025년 3분기 국문 NDR 자료 | 10851 | 3Q25_KT_NDR_PT_KOR_F.pdf | https://corp.kt.com/attach/irdata/10851/3Q25_KT_NDR_PT_KOR_F.pdf |
| 2025 | 4Q | 2025년 4분기 국문 NDR 자료 | 10868 | 4Q25_KT_NDR_PT_KOR_FFIN_업로드용.pdf | https://corp.kt.com/attach/irdata/10868/4Q25_KT_NDR_PT_KOR_FFIN_%EC%97%85%EB%A1%9C%EB%93%9C%EC%9A%A9.pdf |
| 2026 | 1Q | 2026년 1분기 국문 NDR 자료 | 10882 | 1Q26_KT_NDR_PT_KOR_260512_FIN.pdf | https://corp.kt.com/attach/irdata/10882/1Q26_KT_NDR_PT_KOR_260512_FIN.pdf |
| 2026 | 2Q | 2026년 2분기 국문 NDR 자료 | 10893 | 2Q26_KT_NDR_PT_KOR_0811_FF.pdf | https://corp.kt.com/attach/irdata/10893/2Q26_KT_NDR_PT_KOR_0811_FF.pdf |

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
