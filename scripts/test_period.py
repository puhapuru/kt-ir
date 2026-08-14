#!/usr/bin/env python3
"""기간 파싱 회귀 시험. 인터넷을 쓰지 않는다.

    python3 scripts/test_period.py

**실제 목록에 있던 제목을 그대로 넣어 뒀다.** 25년치라 표기가 여러 번
바뀌었고, 규칙을 손볼 때 옛 표기가 깨지는지 여기서 걸린다.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import period as P

FAIL = 0


def check(label, got, want):
    global FAIL
    if got != want:
        FAIL += 1
        print(f"  실패 | {label}\n         받은값 {got!r}\n         기대값 {want!r}")
    else:
        print(f"  통과 | {label}")


def doc(title, filename, category):
    d = P.parse_doc(title, filename, category)
    return d["doc_kind"], d["period"], d["period_type"]


# ── 분기 NDR — 최신 표기 ──────────────────────────────────────────────────
check("2026년 2분기 국문 NDR",
      doc("2026년 2분기 국문 NDR 자료", "2Q26_KT_NDR_PT_KOR_0811_FF.pdf", "프리젠테이션"),
      (P.KIND_NDR, "2026Q2", "quarter"))
check("2025년 4분기 (연도가 제목과 파일명에서 다름)",
      doc("2025년 4분기 국문 NDR 자료", "4Q25_KT_NDR_PT_KOR_FFIN_업로드용.pdf", "프리젠테이션"),
      (P.KIND_NDR, "2025Q4", "quarter"))

# ── 분기 NDR — 옛 표기 ────────────────────────────────────────────────────
# 2007년에는 `실적 NDR자료`(띄어쓰기 없음)와 영문 `1Q` 가 섞여 있었다.
check("2007년 2분기 실적 NDR자료",
      doc("2007년 2분기 실적 NDR자료", "", "프리젠테이션"),
      (P.KIND_NDR, "2007Q2", "quarter"))
check("2007 1Q Overseas NDR",
      doc("2007 1Q Overseas NDR", "", "프리젠테이션"),
      (P.KIND_NDR, "2007Q1", "quarter"))
check("2009년 1분기 국내 NDR 자료",
      doc("2009년 1분기 국내 NDR 자료", "", "프리젠테이션"),
      (P.KIND_NDR, "2009Q1", "quarter"))

# ── 재무지표 (xlsx) ───────────────────────────────────────────────────────
check("2026 2Q Financial Indicator",
      doc("2026 2Q Financial Indicator", "KT 2Q26_Financial_Indicator.xlsx", "재무 데이터"),
      (P.KIND_FININD, "2026Q2", "quarter"))
check("2011 4Q Financial Indicator (파일명이 무의미)",
      doc("2011 4Q Financial Indicator", "kthp1328490117229.xlsx", "재무 데이터"),
      (P.KIND_FININD, "2011Q4", "quarter"))

# ── 월간 Factsheet — 표기가 두 가지다 ─────────────────────────────────────
check("IR Factsheet 2026, 6월호 (쉼표)",
      doc("IR Factsheet 2026, 6월호", "KT IR Factsheet_26.06.xlsx", "가입자 현황"),
      (P.KIND_FACTSHEET, "2026-06", "month"))
check("IR Fact sheet 2001.11월호 (마침표·띄어쓰기)",
      doc("IR Fact sheet 2001.11월호", "20020928170636.pdf", "가입자 현황"),
      (P.KIND_FACTSHEET, "2001-11", "month"))
check("한 자리 월은 0을 채운다",
      doc("IR Factsheet 2026, 1월호", "KT IR Factsheet_26.01.xlsx", "가입자 현황"),
      (P.KIND_FACTSHEET, "2026-01", "month"))
# `년` 이 구분자로 오는 표기가 딱 한 건 있었다. 482건 전체에 돌려 보고서야
# 찾았다 — 표본 몇 개로 시험하면 이런 것이 그대로 빠진다.
check("IR Factsheet 2013년 5월 (월호 없음, 년 구분)",
      doc("IR Factsheet 2013년 5월", "kthp1372383810821.xlsx", "가입자 현황"),
      (P.KIND_FACTSHEET, "2013-05", "month"))

# ── 컨퍼런스 자료는 기간을 붙이지 않는다 ★ ────────────────────────────────
# 제목의 날짜는 **행사일**이다. 실적 기간으로 적어 넣으면 그 분기를 찾을 때
# 엉뚱한 자료가 섞인다.
check("해외 주요 주주방문(2004.2) — 기간 없음",
      doc("해외 주요 주주방문&#40;2004.2&#41;", "2_28_1.pdf", "프리젠테이션"),
      (P.KIND_CONFERENCE, "", ""))
check("UBS Summit — 기간 없음",
      doc("UBS Asia Pacific Tech & Telecom Summit 2004", "2_29_1.pdf", "프리젠테이션"),
      (P.KIND_CONFERENCE, "", ""))
check("2003 CEO 컨퍼런스 — 기간 없음",
      doc("2003 CEO 컨퍼런스", "2_26_1.pdf", "프리젠테이션"),
      (P.KIND_CONFERENCE, "", ""))
check("Non-Deal Roadshow - US (2003.2) — 기간 없음",
      doc("Non-Deal Roadshow - US &#40;2003.2&#41;", "", "프리젠테이션"),
      (P.KIND_CONFERENCE, "", ""))
check("2001년 상반기 기업설명회 — 상반기는 분기가 아니다",
      doc("2001년 상반기 기업설명회 &#40;2001.8.22&#41; 프레젠테이션", "", "프리젠테이션"),
      (P.KIND_CONFERENCE, "", ""))

# ── HTML 엔티티 ───────────────────────────────────────────────────────────
check("괄호 엔티티가 풀린다",
      P.parse_doc("KSE &#40;2003.6&#41;", "", "프리젠테이션")["title"],
      "KSE (2003.6)")

# ── 폴더 이름 ─────────────────────────────────────────────────────────────
check("기간이 있으면 그 이름", P.raw_dir("2026Q2"), "2026Q2")
check("없으면 undated", P.raw_dir(""), "undated")

print()
if FAIL:
    print(f"실패 {FAIL}건")
    sys.exit(1)
print("모두 통과")
