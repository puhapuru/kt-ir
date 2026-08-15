#!/usr/bin/env python3
"""서로 다른 출처가 같은 숫자를 말하는지 본다.

    python3 scripts/crosscheck.py

DART(공시)와 IR 자료(Financial Indicator)는 **완전히 다른 경로**로 들어온다 —
하나는 XBRL 구조화 데이터, 하나는 엑셀에서 단위를 추정해 뽑은 값이다.
그 둘이 맞으면 양쪽 다 믿을 수 있고, 어긋나면 **어느 한쪽이 틀린 것**이다.

IR 쪽 추출기는 단위를 값 크기로 **추정**한다(엑셀 머리글이 거짓이라 그렇다).
그 추정이 언제 깨질지 모르니, 이 대조를 회귀 시험처럼 돌린다.

맞지 않는 것이 있으면 종료 코드 1.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
DB = REPO_DIR / "build" / "kt_ir.sqlite"

# 두 출처에 모두 있고 정의가 같은 지표만 견준다.
METRICS = ["revenue_total", "operating_profit", "net_profit"]
TOLERANCE = 0.005          # 0.5% — 반올림 차이는 넘어간다


def main() -> None:
    if not DB.exists():
        sys.exit(f"{DB} 가 없다. 먼저:  python3 scripts/build_db.py")
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)

    bad = restated = 0
    checked = 0
    for metric in METRICS:
        print(f"\n■ {metric} (연결, 연간, 억원)")
        print(f"  {'연도':<6}{'DART':>12}{'IR':>12}{'차이':>10}")
        for (year,) in c.execute(
            "SELECT DISTINCT period FROM facts WHERE period_type='year' ORDER BY period"
        ):
            d = c.execute("""
                SELECT value FROM facts WHERE metric_id=? AND consolidation='연결'
                AND period=? AND report_id LIKE 'dart_%_11011_CFS'""",
                (metric, year)).fetchone()
            i = c.execute("""
                SELECT f.value FROM facts f JOIN reports r ON r.report_id=f.report_id
                WHERE f.metric_id=? AND f.consolidation='연결' AND f.period=?
                AND f.report_id LIKE 'financial_indicator_%'
                ORDER BY r.published_at DESC LIMIT 1""",
                (metric, year)).fetchone()
            if not d or not i or not i[0]:
                continue                      # 한쪽에만 있는 해는 견줄 수 없다
            checked += 1
            diff = d[0] - i[0]
            if abs(diff) / abs(i[0]) <= TOLERANCE:
                print(f"  {year:<6}{d[0]:>12,.0f}{i[0]:>12,.0f}{diff:>10,.0f}  ✓")
                continue

            # **어긋났다고 곧바로 오류가 아니다.** KT 가 과거 수치를 고치면
            # DART 원공시와 IR 최신본이 다른 것이 정상이다. 실제로 2019년
            # 순이익이 6,693억 → 6,659억으로 바뀌었다(2021-02-09 자료부터).
            #
            # 가르는 법: IR 쪽에 그 해 값이 **여러 가지**로 있으면 재작성이고,
            # 하나뿐인데 DART 와 다르면 어느 한쪽 추출이 틀린 것이다.
            n_ir = c.execute("""
                SELECT COUNT(DISTINCT ROUND(value, 0)) FROM facts
                WHERE metric_id=? AND consolidation='연결' AND period=?
                AND report_id LIKE 'financial_indicator_%'""",
                (metric, year)).fetchone()[0]
            if n_ir > 1:
                restated += 1
                print(f"  {year:<6}{d[0]:>12,.0f}{i[0]:>12,.0f}{diff:>10,.0f}  "
                      f"↻ 재작성(IR 에 {n_ir}가지)")
            else:
                bad += 1
                print(f"  {year:<6}{d[0]:>12,.0f}{i[0]:>12,.0f}{diff:>10,.0f}  ⚠ 추출의심")

    print(f"\n대조 {checked}건 · 일치 {checked - bad - restated}건 · "
          f"재작성 {restated}건 · 추출의심 {bad}건")
    if bad:
        print("추출의심이 있다. 어느 쪽이 틀렸는지 원본을 봐야 한다.", file=sys.stderr)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
