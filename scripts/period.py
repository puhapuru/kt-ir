#!/usr/bin/env python3
"""자료 제목·파일명에서 **종류와 대상 기간**을 뽑는다.

`collect.py` 가 `reports.csv` 를 쓸 때 쓴다. 여기서 정한 `period` 가
나중에 `facts.csv` 와 이어지는 열쇠라, 표기가 흔들려도 같은 값이 나와야 한다.

**표기가 여러 가지다** — 25년치라 그렇다. 실제로 확인한 것:

    2026년 2분기 국문 NDR 자료      2007년 2분기 실적 NDR자료
    2026 2Q Financial Indicator    2007 1Q Overseas NDR
    IR Factsheet 2026, 6월호        IR Fact sheet 2001.11월호

**2005년 이전 프리젠테이션은 분기 자료가 아니다.** 컨퍼런스·로드쇼·주주방문
자료라 대상 분기라는 것이 없다(48건). 억지로 기간을 붙이면 안 된다 —
`해외 주요 주주방문(2004.2)` 의 `2004.2` 는 **행사 날짜**지 실적 기간이 아니고,
그걸 2004Q1 로 적어 넣으면 그 분기 실적을 찾을 때 엉뚱한 자료가 섞인다.
그래서 **기간을 못 정하면 빈칸으로 둔다.**
"""

from __future__ import annotations

import html
import re

# ── 종류 ──────────────────────────────────────────────────────────────────────
KIND_NDR = "ndr"                    # 분기 실적 발표(NDR) 자료
KIND_FININD = "financial_indicator"  # 분기 재무지표 (xlsx — 표라서 추출이 쉽다)
KIND_FACTSHEET = "factsheet"        # 월간 IR Factsheet (가입자·ARPU)
KIND_CONFERENCE = "conference"      # 컨퍼런스·로드쇼·주주방문 (기간 없음)

# ── 기간 표기 ────────────────────────────────────────────────────────────────
# `2026년 2분기` · `2026년2분기`
_Q_KO = re.compile(r"(20\d{2})\s*년?\s*([1-4])\s*분기")
# `2026 2Q` · `2007 1Q Overseas NDR`
_Q_EN = re.compile(r"(20\d{2})\s*[-_ ]?\s*([1-4])\s*Q(?![a-z])", re.I)
# 파일명 쪽 `2Q26_` · `4Q25_KT_NDR` — 연도가 **뒤에** 오고 두 자리다
_Q_FILE = re.compile(r"(?<![0-9A-Za-z])([1-4])\s*Q\s*(\d{2})(?![0-9])", re.I)

# `2026, 6월호` · `2001.11월호` · `2013년 5월` · `26.06`
# 구분자에 `년` 을 꼭 넣어 둘 것 — 빼 놨더니 `2013년 5월` 한 건이 조용히
# 기간 없음으로 빠졌다(482건 전체에 돌려 보고서야 찾았다).
_M_KO = re.compile(r"(20\d{2})\s*[년,.\s]\s*(1[0-2]|0?[1-9])\s*월")
_M_FILE = re.compile(r"(?<!\d)(\d{2})[.\-_](1[0-2]|0[1-9])(?!\d)")

_CONFERENCE_HINT = re.compile(
    r"컨퍼런스|conference|summit|로드\s*쇼|roadshow|road\s*show|주주\s*방문|"
    r"기업설명회|브리핑|briefing|analyst|forum|kse|매각",
    re.I,
)


def _clean(text: str) -> str:
    """제목의 HTML 엔티티를 푼다.

    목록 API 가 괄호를 `&#40;` `&#41;` 로 준다. 안 풀면 괄호 안 날짜를
    못 읽고, 사람이 볼 때도 그대로 보인다.
    """
    return html.unescape(text or "").strip()


def _yy_to_year(yy: str) -> int:
    """두 자리 연도를 네 자리로. KT 자료는 2000년 이후뿐이다."""
    n = int(yy)
    return 2000 + n if n <= 50 else 1900 + n


def classify(title: str, filename: str, category: str) -> str:
    """자료 종류를 정한다. `category` 는 API 의 `genlCtgTypeNm`."""
    t = _clean(title)
    f = filename or ""

    if "재무" in category or re.search(r"financial\s*indicator", t + f, re.I):
        return KIND_FININD
    if "가입자" in category or re.search(r"fact\s*sheet", t + f, re.I):
        return KIND_FACTSHEET
    if re.search(r"NDR", t + f, re.I) and (_Q_KO.search(t) or _Q_EN.search(t) or _Q_FILE.search(f)):
        return KIND_NDR
    # 분기 표기가 있는 실적 자료는 NDR 로 본다 (`2007년 2분기 실적 NDR자료`)
    if (_Q_KO.search(t) or _Q_EN.search(t)) and not _CONFERENCE_HINT.search(t):
        return KIND_NDR
    if _CONFERENCE_HINT.search(t):
        return KIND_CONFERENCE
    return KIND_CONFERENCE


def parse_period(title: str, filename: str, kind: str) -> tuple[str, str]:
    """`(period, period_type)` 을 돌려준다. 못 정하면 `("", "")`.

    **컨퍼런스 자료는 아예 보지 않는다** — 제목에 든 날짜는 행사일이지
    실적 기간이 아니다.
    """
    if kind == KIND_CONFERENCE:
        return "", ""

    t = _clean(title)
    f = filename or ""

    if kind == KIND_FACTSHEET:
        m = _M_KO.search(t)
        if m:
            return f"{m.group(1)}-{int(m.group(2)):02d}", "month"
        m = _M_FILE.search(f)
        if m:
            return f"{_yy_to_year(m.group(1))}-{int(m.group(2)):02d}", "month"
        return "", ""

    # 분기 — 제목을 먼저 본다. 파일명은 `_0811_FF` 같은 잡음이 많다.
    m = _Q_KO.search(t) or _Q_EN.search(t)
    if m:
        return f"{m.group(1)}Q{m.group(2)}", "quarter"
    m = _Q_FILE.search(f)
    if m:
        return f"{_yy_to_year(m.group(2))}Q{m.group(1)}", "quarter"
    return "", ""


def parse_doc(title: str, filename: str, category: str) -> dict:
    """종류와 기간을 한 번에. `collect.py` 가 부르는 입구."""
    kind = classify(title, filename, category)
    period, period_type = parse_period(title, filename, kind)
    return {
        "doc_kind": kind,
        "period": period,
        "period_type": period_type,
        "title": _clean(title),
    }


def raw_dir(period: str) -> str:
    """원본을 둘 폴더 이름. 기간을 모르면 한곳에 모은다."""
    return period if period else "undated"
