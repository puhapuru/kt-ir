#!/usr/bin/env python3
"""DART 변환 로직 회귀 시험. **인터넷도 API 키도 쓰지 않는다.**

    python3 scripts/test_dart.py

키가 있어야 실제 호출을 해 볼 수 있으니, 그 전에 **순수 계산 부분**만이라도
고정해 둔다 — 금액 파싱, 계정 매핑, 기간 표기, 직원 현황 합산.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dart
import collect_dart as CD

FAIL = 0


def check(label, got, want):
    global FAIL
    if got != want:
        FAIL += 1
        print(f"  실패 | {label}\n         받은값 {got!r}\n         기대값 {want!r}")
    else:
        print(f"  통과 | {label}")


# ── 금액 파싱 ─────────────────────────────────────────────────────────────
check("쉼표를 뗀다", dart.to_number("1,234,567"), 1234567.0)
check("빈 값은 None", dart.to_number(""), None)
check("하이픈은 None", dart.to_number("-"), None)
check("None 은 None", dart.to_number(None), None)
check("음수 부호", dart.to_number("-1,234"), -1234.0)
# 회계 표기에서 괄호는 음수다. 이걸 놓치면 **적자가 흑자로 들어간다.**
check("괄호는 음수", dart.to_number("(1,234)"), -1234.0)
check("괄호 안 큰 수", dart.to_number("(7,194,000,000)"), -7194000000.0)

# ── 계정 매핑 — id 가 이름보다 먼저다 ─────────────────────────────────────
check("XBRL id 로 매출",
      CD.map_account({"account_id": "ifrs-full_Revenue", "account_nm": "아무거나"}),
      ("revenue_total", True))
check("XBRL id 로 영업이익",
      CD.map_account({"account_id": "dart_OperatingIncomeLoss", "account_nm": "영업이익"}),
      ("operating_profit", True))
check("인건비(종업원급여)",
      CD.map_account({"account_id": "ifrs-full_EmployeeBenefitsExpense",
                      "account_nm": "종업원급여"}),
      ("opex_labor", True))
# DART 는 id 자리에 `-표준계정코드 미사용-` 을 흔히 준다. 그때만 한글로 본다.
check("id 가 없으면 한글 이름으로",
      CD.map_account({"account_id": "-표준계정코드 미사용-", "account_nm": "영업수익"}),
      ("revenue_total", True))
check("자산총계는 손익이 아니다",
      CD.map_account({"account_id": "ifrs-full_Assets", "account_nm": "자산총계"}),
      ("assets_total", False))
check("모르는 계정은 None",
      CD.map_account({"account_id": "ifrs-full_Whatever", "account_nm": "기타포괄손익"}),
      None)

# ── 기간 표기 ─────────────────────────────────────────────────────────────
check("사업보고서는 연간", CD.period_of(2024, "11011"), "2024")
check("1분기", CD.period_of(2024, "11013"), "2024Q1")
check("반기는 Q2", CD.period_of(2024, "11012"), "2024Q2")
check("3분기", CD.period_of(2024, "11014"), "2024Q3")

# ── 재무제표 → facts ──────────────────────────────────────────────────────
ROWS = [
    {"sj_div": "IS", "account_id": "ifrs-full_Revenue", "account_nm": "수익(매출액)",
     "thstrm_amount": "6,500,000,000,000", "thstrm_add_amount": "13,000,000,000,000"},
    {"sj_div": "BS", "account_id": "ifrs-full_Assets", "account_nm": "자산총계",
     "thstrm_amount": "40,000,000,000,000"},
    {"sj_div": "IS", "account_id": "ifrs-full_Whatever", "account_nm": "모르는계정",
     "thstrm_amount": "1,000"},
]
q = CD.fin_facts(ROWS, "dart_2024_11012_CFS", 2024, "11012", "연결")
# 손익은 단일분기+누적 둘, 재무상태표는 시점 하나, 모르는 계정은 버린다 → 3줄
check("분기 보고서에서 3줄", len(q), 3)
check("원 → 억원 (6.5조 = 65,000억)",
      next(f["value"] for f in q if f["basis"] == "단일분기"), 65000.0)
check("누계도 함께 담는다",
      next(f["value"] for f in q if f["basis"] == "누적"), 130000.0)
check("재무상태표는 시점",
      next(f["basis"] for f in q if f["metric_id"] == "assets_total"), "시점")
check("기간이 2024Q2", q[0]["period"], "2024Q2")

a = CD.fin_facts(ROWS, "dart_2024_11011_CFS", 2024, "11011", "연결")
# 사업보고서는 누계 개념이 없으므로 계정당 한 줄씩 → 2줄
check("사업보고서에서 2줄", len(a), 2)
check("사업보고서 basis 는 연간",
      next(f["basis"] for f in a if f["metric_id"] == "revenue_total"), "연간")

# ── 직원 현황 — 사업부문·성별로 여러 줄이 와서 합쳐야 한다 ────────────────
EMP = [
    {"fo_bbm": "통신", "sexdstn": "남", "rgllbr_co": "10,000", "cnttk_co": "500",
     "sm": "10,500", "fyer_salary_totamt": "900,000,000,000"},
    {"fo_bbm": "통신", "sexdstn": "여", "rgllbr_co": "3,000", "cnttk_co": "200",
     "sm": "3,200", "fyer_salary_totamt": "200,000,000,000"},
]
e = CD.emp_facts(EMP, "dart_2024_emp", 2024, "11011")
byid = {f["metric_id"]: f for f in e}
check("직원 합계 13,700명", byid["employees"]["value"], 13700.0)
check("정규직 13,000명", byid["employees_regular"]["value"], 13000.0)
check("기간제 700명", byid["employees_contract"]["value"], 700.0)
check("급여총액 1.1조 = 11,000억", byid["opex_labor_disclosed"]["value"], 11000.0)
check("인원 단위는 명", byid["employees"]["unit"], "명")
check("급여 단위는 억원", byid["opex_labor_disclosed"]["unit"], "억원")
check("빈 응답은 빈 결과", CD.emp_facts([], "x", 2024, "11011"), [])

# ── 연도 인자 ─────────────────────────────────────────────────────────────
# ── 자본변동표(SCE) 중복 걸러내기 ★ ──────────────────────────────────────
# 2024년 연결 실측: equity_total 이 BS 1줄 + SCE 8줄로 9번, net_profit 이
# IS·CIS·SCE 합쳐 10번 들어왔다. SCE 는 자본 항목별 증감이라 총계가 아니다.
DUP = (
    [{"sj_div": "BS", "account_id": "ifrs-full_Equity", "account_nm": "자본총계",
      "thstrm_amount": "10,000,000,000,000"}]
    + [{"sj_div": "SCE", "account_id": "ifrs-full_Equity", "account_nm": "자본총계",
        "thstrm_amount": "1,000,000,000"} for _ in range(8)]
    + [{"sj_div": "IS", "account_id": "ifrs-full_ProfitLoss", "account_nm": "당기순이익",
        "thstrm_amount": "500,000,000,000"},
       {"sj_div": "CIS", "account_id": "ifrs-full_ProfitLoss", "account_nm": "당기순이익",
        "thstrm_amount": "500,000,000,000"}]
)
dfacts = CD.fin_facts(DUP, "dart_2024_11011_CFS", 2024, "11011", "연결")
check("SCE 8줄을 걷어내고 자본총계는 한 줄", len(dfacts), 2)
check("자본총계는 BS 값 (10조 = 100,000억)",
      next(f["value"] for f in dfacts if f["metric_id"] == "equity_total"), 100000.0)
check("IS·CIS 중복도 한 줄",
      sum(1 for f in dfacts if f["metric_id"] == "net_profit"), 1)

check("범위", CD.parse_years("2015-2018"), [2015, 2016, 2017, 2018])
check("한 해", CD.parse_years("2024"), [2024])

print()
if FAIL:
    print(f"실패 {FAIL}건")
    sys.exit(1)
print("모두 통과")
