#!/usr/bin/env python3
"""DART 에서 재무제표와 직원 현황을 받아 `facts.csv` 에 넣는다.

    .venv/bin/python scripts/collect_dart.py --years 2015-2025
    .venv/bin/python scripts/collect_dart.py --years 2024 --report   # 안 쓰고 진단만

**IR 자료로는 못 얻는 것을 여기서 가져온다** — 특히 `종업원급여`(인건비)와
직원 현황(정규직·계약직 수, 평균 근속, 연간급여총액, 1인평균급여).
IR 프레젠테이션에는 인건비 세부가 없다.

## 계정 매핑은 한글 이름이 아니라 XBRL id 로 한다 ★

`account_nm`(한글)은 회사·연도마다 흔들린다 — `매출액` · `수익(매출액)` ·
`영업수익` 이 다 같은 것이다. `account_id`(예: `ifrs-full_Revenue`)는 표준이라
훨씬 안정적이다. **id 를 먼저 보고, 없을 때만 한글 이름으로 넘어간다.**

## 분기 값은 누계로 온다

DART 분기보고서의 `thstrm_amount` 는 **그 분기 3개월**이고
`thstrm_add_amount` 가 **연초부터 누계**다. 손익 항목은 둘 다 담아
`basis` 로 구분한다. 재무상태표(자산·부채)는 시점 값이라 누계가 없다.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dart  # noqa: E402
import factstore as FS  # noqa: E402

PREFIX = "dart_"

# ── 계정 매핑 ────────────────────────────────────────────────────────────────
# XBRL 표준 id 우선. 값은 (metric_id, 손익인지).
BY_ID = {
    "ifrs-full_Revenue":                                    ("revenue_total", True),
    "ifrs-full_ProfitLoss":                                 ("net_profit", True),
    "ifrs-full_ProfitLossAttributableToOwnersOfParent":     ("net_profit_controlling", True),
    "dart_OperatingIncomeLoss":                             ("operating_profit", True),
    "ifrs-full_Assets":                                     ("assets_total", False),
    "ifrs-full_Liabilities":                                ("liabilities_total", False),
    "ifrs-full_Equity":                                     ("equity_total", False),
    "ifrs-full_EmployeeBenefitsExpense":                    ("opex_labor", True),
    "ifrs-full_DepreciationAndAmortisationExpense":         ("opex_depreciation", True),
}

# id 가 `-표준계정코드 미사용-` 으로 오는 일이 흔하다. 그때만 한글로 본다.
BY_NAME = {
    "수익(매출액)": ("revenue_total", True),
    "매출액": ("revenue_total", True),
    "영업수익": ("revenue_total", True),
    "영업이익": ("operating_profit", True),
    "영업이익(손실)": ("operating_profit", True),
    "당기순이익": ("net_profit", True),
    "당기순이익(손실)": ("net_profit", True),
    "종업원급여": ("opex_labor", True),
    "급여": ("opex_labor", True),
    "감가상각비": ("opex_depreciation", True),
    "영업비용": ("opex_total", True),
    "자산총계": ("assets_total", False),
    "부채총계": ("liabilities_total", False),
    "자본총계": ("equity_total", False),
}

FS_DIV = {"CFS": "연결", "OFS": "별도"}


def map_account(row: dict) -> tuple[str, bool] | None:
    """계정 한 줄 → `(metric_id, 손익인지)`. 지도에 없으면 None."""
    aid = (row.get("account_id") or "").strip()
    hit = BY_ID.get(aid)
    if hit:
        return hit
    return BY_NAME.get((row.get("account_nm") or "").strip())


def period_of(year: int, reprt: str) -> str:
    """`(2024, '11014')` → `2024Q3`. 사업보고서는 연간이라 `2024`."""
    q, _ = dart.REPRT[reprt]
    return str(year) if reprt == "11011" else f"{year}{q}"


def fin_facts(rows: list[dict], report_id: str, year: int, reprt: str,
              consolidation: str) -> list[dict]:
    """재무제표 응답 → facts 줄들."""
    out = []
    annual = reprt == "11011"
    for r in rows:
        hit = map_account(r)
        if hit is None:
            continue
        metric, is_pl = hit

        # 손익은 (그 분기, 누계) 둘 다, 재무상태표는 시점 값 하나.
        cands = [("thstrm_amount", "연간" if annual else "단일분기")]
        if is_pl and not annual:
            cands.append(("thstrm_add_amount", "누적"))

        for field, basis in cands:
            v = dart.to_number(r.get(field))
            if v is None:
                continue
            out.append({
                "report_id": report_id,
                "period": period_of(year, reprt),
                "period_type": "year" if annual else "quarter",
                "basis": basis if is_pl else "시점",
                "consolidation": consolidation,
                "accounting": "K-IFRS",
                "metric_id": metric,
                "label_raw": (r.get("account_nm") or "").strip(),
                "value": round(v * dart.WON_TO_억, 2),
                "unit": "억원",
                "page": "",
                "confidence": "auto",
            })
    return out


def emp_facts(rows: list[dict], report_id: str, year: int, reprt: str) -> list[dict]:
    """직원 현황 → facts 줄들. **조합이 가장 볼 만한 숫자들이다.**

    사업부문·성별로 여러 줄이 오므로 **합계**를 낸다. 급여 금액은 원 단위다.
    """
    period = period_of(year, reprt)
    ptype = "year" if reprt == "11011" else "quarter"
    tot = {"employees": 0.0, "employees_regular": 0.0, "employees_contract": 0.0,
           "opex_labor_disclosed": 0.0}
    seen = False
    for r in rows:
        for key, field in (("employees", "sm"),
                           ("employees_regular", "rgllbr_co"),
                           ("employees_contract", "cnttk_co")):
            v = dart.to_number(r.get(field))
            if v is not None:
                tot[key] += v
                seen = True
        v = dart.to_number(r.get("fyer_salary_totamt"))
        if v is not None:
            tot["opex_labor_disclosed"] += v
            seen = True
    if not seen:
        return []

    out = []
    for metric, value in tot.items():
        if not value:
            continue
        # 인원은 명, 급여는 원 → 억원
        unit = "명" if metric.startswith("employees") else "억원"
        val = value if unit == "명" else round(value * dart.WON_TO_억, 2)
        out.append({
            "report_id": report_id, "period": period, "period_type": ptype,
            "basis": "시점" if unit == "명" else "연간",
            "consolidation": "별도", "accounting": "",
            "metric_id": metric, "label_raw": "직원 현황(사업보고서)",
            "value": val, "unit": unit, "page": "", "confidence": "auto",
        })
    return out


def parse_years(spec: str) -> list[int]:
    if "-" in spec:
        a, b = spec.split("-", 1)
        return list(range(int(a), int(b) + 1))
    return [int(spec)]


def main() -> None:
    ap = argparse.ArgumentParser(description="DART → facts.csv")
    ap.add_argument("--years", default="2015-2025", help="예: 2015-2025 또는 2024")
    ap.add_argument("--report", action="store_true", help="파일을 쓰지 않고 진단만")
    ap.add_argument("--annual-only", action="store_true", help="사업보고서만 (빠르다)")
    args = ap.parse_args()

    years = parse_years(args.years)
    reprts = ["11011"] if args.annual_only else list(dart.REPRT)

    corp = dart.corp_code()
    print(f"KT 고유번호 {corp} · 연도 {years[0]}~{years[-1]} · 보고서 {len(reprts)}종")

    facts: list[dict] = []
    reports: list[dict] = []
    skipped = 0

    for year in years:
        for reprt in reprts:
            _, reprt_name = dart.REPRT[reprt]
            for fs_div, cons in FS_DIV.items():
                rid = f"{PREFIX}{year}_{reprt}_{fs_div}"
                try:
                    rows = dart.financials(corp, year, reprt, fs_div)
                except dart.DartError as e:
                    print(f"  건너뜀 {rid}: {e}", file=sys.stderr)
                    skipped += 1
                    continue
                if not rows:
                    skipped += 1
                    continue
                got = fin_facts(rows, rid, year, reprt, cons)
                facts.extend(got)
                reports.append({
                    "report_id": rid, "doc_kind": "dart_financial",
                    "period": period_of(year, reprt),
                    "period_type": "year" if reprt == "11011" else "quarter",
                    "published_at": "", "title": f"{year} {reprt_name} ({cons})",
                    "category": "DART", "filename": "", "sha256": "", "bytes": "",
                    "local_path": "",
                    "url": f"https://dart.fss.or.kr/dsab007/main.do?corpCode={corp}",
                })
                print(f"  {rid}: 계정 {len(rows)}줄 → 수치 {len(got)}개")

        # 직원 현황은 사업보고서에만 실린다
        if "11011" in reprts:
            rid = f"{PREFIX}{year}_emp"
            try:
                rows = dart.employees(corp, year, "11011")
            except dart.DartError as e:
                print(f"  건너뜀 {rid}: {e}", file=sys.stderr)
                rows = []
            got = emp_facts(rows, rid, year, "11011")
            if got:
                facts.extend(got)
                reports.append({
                    "report_id": rid, "doc_kind": "dart_employees",
                    "period": str(year), "period_type": "year", "published_at": "",
                    "title": f"{year} 직원 현황", "category": "DART",
                    "url": f"https://dart.fss.or.kr/dsab007/main.do?corpCode={corp}",
                    "filename": "", "sha256": "", "bytes": "", "local_path": "",
                })
                print(f"  {rid}: 직원 현황 {len(got)}개")

    print(f"\n수치 {len(facts):,}개 · 자료 {len(reports)}건 · 건너뜀 {skipped}건")

    metrics = sorted({f["metric_id"] for f in facts})
    print("담긴 지표:", ", ".join(metrics) if metrics else "(없음)")

    if args.report:
        print("\n(--report 라 파일을 쓰지 않았다)")
        return

    removed, added = FS.replace_facts(PREFIX, facts)
    FS.upsert_reports(reports)
    print(f"\nfacts.csv — dart 줄 {removed}개 걷어내고 {added}개 넣음")


if __name__ == "__main__":
    main()
