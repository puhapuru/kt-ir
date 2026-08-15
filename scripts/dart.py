#!/usr/bin/env python3
"""DART OpenAPI(금융감독원) 얇은 클라이언트.

IR 자료로는 못 얻는 것을 여기서 가져온다 — **재무제표 전체**와 **직원 현황**
(정규직·계약직 수, 평균 근속, 연간급여총액, 1인평균급여). IR 프레젠테이션에는
인건비 세부가 없다.

    .env 에  DART_API_KEY=...        (opendart.fss.or.kr 에서 무료 발급)

## 왜 DART 를 함께 쓰나

| 무엇 | 어디서 | 왜 |
|---|---|---|
| 매출·영업이익·비용·자산·**인건비** | DART | XBRL 구조화. PDF 를 더듬을 필요가 없다 |
| ARPU·가입자 수·CAPEX 세부 | IR 자료 | DART 에 없다 |

## 보고서 코드

    11011 사업보고서(연간)   11012 반기   11013 1분기   11014 3분기

## 단위

DART 금액은 **원 단위**로 온다. 이 저장소의 표준은 억원이라 1억으로 나눈다.
"""

from __future__ import annotations

import io
import json
import os
import sys
import time
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
CACHE_DIR = REPO_DIR / "build" / "dart_cache"
BASE = "https://opendart.fss.or.kr/api"

KT_STOCK_CODE = "030200"     # KT 보통주

REPRT = {                    # 보고서 코드 → (분기 표기, 누적인지)
    "11013": ("Q1", "1분기보고서"),
    "11012": ("Q2", "반기보고서"),
    "11014": ("Q3", "3분기보고서"),
    "11011": ("Q4", "사업보고서"),
}

# 원 → 억원
WON_TO_억 = 1e-8


class DartError(RuntimeError):
    """DART 가 정상 응답(status 000)이 아닌 것을 돌려줬을 때."""


def load_key() -> str:
    """`DART_API_KEY` 를 환경변수나 `.env` 에서 읽는다. **값은 찍지 않는다.**"""
    key = os.environ.get("DART_API_KEY", "").strip()
    if key:
        return key
    env = REPO_DIR / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("DART_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    sys.exit(
        "DART_API_KEY 가 없다.\n"
        "  1) https://opendart.fss.or.kr 에서 무료 발급 (가입 → 인증키 신청)\n"
        "  2) kt-ir/.env 에  DART_API_KEY=발급받은키  한 줄로 넣는다\n"
        "  (.env 는 .gitignore 로 막혀 있다)"
    )


def _get(path: str, params: dict, *, raw: bool = False, tries: int = 4) -> bytes | dict:
    """DART 를 부른다. 재시도는 넉넉히 — 무료 API 라 간헐적으로 막힌다."""
    q = dict(params)
    q["crtfc_key"] = load_key()
    url = f"{BASE}/{path}?{urllib.parse.urlencode(q)}"
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "kt-ir/1.0"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                body = resp.read()
            if raw:
                return body
            d = json.loads(body)
            status = d.get("status")
            if status == "000":
                return d
            if status == "013":          # 조회된 데이터가 없음 — 오류가 아니다
                return {"status": "013", "list": []}
            raise DartError(f"{path}: status={status} {d.get('message','')}")
        except DartError:
            raise                         # 자격증명·요청 오류는 재시도해도 같다
        except Exception as e:
            last = e
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"{path}: 호출 실패 — {type(last).__name__}: {last}")


def corp_code(stock_code: str = KT_STOCK_CODE) -> str:
    """종목코드로 DART 고유번호(8자리)를 찾는다.

    전체 목록이 zip 으로 오고 3MB 쯤 된다. 자주 안 바뀌니 받아서 캐시해 둔다.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache = CACHE_DIR / "corp_code.xml"
    if not cache.exists():
        blob = _get("corpCode.xml", {}, raw=True)
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            cache.write_bytes(z.read(z.namelist()[0]))

    import xml.etree.ElementTree as ET
    root = ET.fromstring(cache.read_text(encoding="utf-8"))
    for el in root.iter("list"):
        if (el.findtext("stock_code") or "").strip() == stock_code:
            return (el.findtext("corp_code") or "").strip()
    raise DartError(f"종목코드 {stock_code} 를 DART 목록에서 못 찾음")


def financials(corp: str, year: int, reprt: str, fs_div: str) -> list[dict]:
    """단일회사 전체 재무제표. `fs_div` 는 `CFS`(연결) 또는 `OFS`(별도).

    2015년부터 제공된다. 그 이전은 IR 자료 쪽을 쓴다.
    """
    d = _get("fnlttSinglAcntAll.json", {
        "corp_code": corp, "bsns_year": str(year),
        "reprt_code": reprt, "fs_div": fs_div,
    })
    return d.get("list") or []


def employees(corp: str, year: int, reprt: str) -> list[dict]:
    """직원 현황 — 정규직·계약직 수, 평균 근속, **연간급여총액·1인평균급여**.

    사업보고서에만 실리는 항목이라 보통 `11011` 로 부른다.
    """
    d = _get("empSttus.json", {
        "corp_code": corp, "bsns_year": str(year), "reprt_code": reprt,
    })
    return d.get("list") or []


def officers(corp: str, year: int, reprt: str) -> list[dict]:
    """임원 보수 현황. 직원 급여와 견주려고 함께 받는다."""
    d = _get("hyslrSttus.json", {
        "corp_code": corp, "bsns_year": str(year), "reprt_code": reprt,
    })
    return d.get("list") or []


def to_number(text) -> float | None:
    """DART 가 주는 금액 문자열을 숫자로. `-` `1,234` `(1,234)` 를 다룬다.

    괄호는 음수다 — 회계 표기다. 이걸 놓치면 **적자가 흑자로 들어간다.**
    """
    if text is None:
        return None
    s = str(text).strip().replace(",", "").replace(" ", "")
    if s in ("", "-", "--"):
        return None
    neg = s.startswith("(") and s.endswith(")")
    if neg:
        s = s[1:-1]
    if s.startswith("-"):
        neg, s = True, s[1:]
    try:
        v = float(s)
    except ValueError:
        return None
    return -v if neg else v
