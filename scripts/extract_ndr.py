#!/usr/bin/env python3
"""NDR 프레젠테이션(PDF)에서 **사업부문별 분기 매출**을 뽑는다.

    python3 scripts/extract_ndr.py --report
    python3 scripts/extract_ndr.py

무선·유선·미디어 같은 **부문별 매출은 여기에만 있다.** Financial Indicator 는
매출을 서비스/단말로만 쪼개고, DART 재무제표 본문에도 부문 정보가 없다.

## 차트 안 숫자를 좌표로 짝짓는다 ★

값이 표가 아니라 **막대그래프 위 라벨**로 박혀 있다. 글자만 뽑으면
(`pdftotext`) 막대 높이 순서대로 뒤섞여 나와 어느 분기 것인지 알 수 없다:

        1,733.6   1,735.7          ← 높은 막대가 먼저 나온다
    1,704.8
                    1,683.0   1,674.9

그래서 `pdftotext -bbox-layout` 으로 **낱말마다 좌표**를 받아, 가로축의 분기
라벨과 **x 가 가장 가까운 값**을 짝짓는다. 실측(2026Q2 자료):

    값    x =  74.9  118.9  163.0  207.0  251.0
    라벨  x =  79.4  123.4  167.5  211.5  255.6   (2Q25 3Q25 4Q25 1Q26 2Q26)

어긋남이 5pt 안쪽이라 이웃과 헷갈릴 여지가 없다(막대 간격은 44pt).

## 단위

차트에 `(단위: 십억원)` 이라고 적혀 있고, 이번엔 **실제로 십억원이 맞다**.
그래도 값 범위로 확인한다 — 다른 자료에서 머리글이 두 번이나 거짓이었다.
"""

from __future__ import annotations

import argparse
import csv
import html
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import factstore as FS  # noqa: E402

REPO_DIR = Path(__file__).resolve().parent.parent
PREFIX = "ndr_"

# 부문 제목 → 지표. PDF 쪽수 제목에서 찾는다.
SEGMENTS = {
    "무선": "revenue_wireless",
    "wireless": "revenue_wireless",
}

# 분기 무선 서비스매출이 들어갈 만한 범위(십억원). KT 는 1.5~2.0조 선이다.
RANGE_십억 = (1_200, 2_400)

_WORD = re.compile(
    r'<word xMin="([\d.eE+-]+)" yMin="([\d.eE+-]+)" '
    r'xMax="([\d.eE+-]+)" yMax="([\d.eE+-]+)">(.*?)</word>', re.S)
_PAGE = re.compile(r'<page width="[\d.]+" height="[\d.]+">(.*?)</page>', re.S)
_QLABEL = re.compile(r"^([1-4])Q\s?'?(\d{2})$", re.I)
# 차트 값. **소수점이 없는 자료가 많다** — 2015년 무선 서비스 매출은
# `1,654` 처럼 정수로 적혀 있어서, 소수점을 요구했더니 2021년 이전이 통째로
# 안 잡혔다(72건 중 62건 실패의 주된 원인).
#
# **천 단위 쉼표는 반드시 요구한다.** 쉼표 없는 네 자리를 받으면 연도(`2015`)가
# 값 범위(1,200~2,400)에 들어와 매출로 둔갑한다.
_NUM = re.compile(r"^\d{1,3}(?:,\d{3})+(?:\.\d+)?$")


def pdf_words(path: Path) -> list[list[tuple[float, float, str]]]:
    """쪽마다 `(x, y, 글자)` 목록. 실패하면 빈 목록."""
    try:
        out = subprocess.run(["pdftotext", "-bbox-layout", str(path), "-"],
                             capture_output=True, timeout=120)
    except Exception:
        return []
    if out.returncode != 0:
        return []
    xml = out.stdout.decode("utf-8", "replace")
    pages = []
    for body in _PAGE.findall(xml):
        ws = [(float(a), float(b), html.unescape(t).strip())
              for a, b, _, _, t in _WORD.findall(body)]
        pages.append([w for w in ws if w[2]])
    return pages


def find_axis(words) -> tuple[float, list[tuple[float, str]]]:
    """가로축의 분기 라벨을 찾는다 — **같은 y 에 4개 이상** 늘어선 것.

    쪽에 차트가 여럿이라 축도 여럿이다. 가장 왼쪽에 있는 축을 고른다
    (서비스매출 차트가 왼쪽, ARPU·보급률이 오른쪽에 오는 배치다).
    """
    rows: dict[int, list[tuple[float, str]]] = {}
    for x, y, t in words:
        m = _QLABEL.match(t)
        if m:
            year = 2000 + int(m.group(2))
            rows.setdefault(round(y), []).append((x, f"{year}Q{m.group(1)}"))
    axes = [(y, sorted(v)) for y, v in rows.items() if len(v) >= 4]
    if not axes:
        return 0.0, []
    # 차트가 여럿이면 가장 왼쪽 축(서비스매출)을 고른다.
    return min(axes, key=lambda a: a[1][0][0])


def match_values(words, axis_y: float, axis) -> dict[str, float]:
    """축 라벨과 **x 가 가장 가까운** 숫자를 짝짓는다.

    축의 y 는 `find_axis` 가 그대로 넘겨준다. 예전에는 여기서 다시 찾았는데,
    쪽에 차트가 여럿이라 **다른 차트의 라벨을 집어** 축이 위쪽으로 잡히고
    정작 값이 전부 걸러졌다(8건 중 4건이 그래서 빈손이었다).
    """
    xs = [x for x, _ in axis]
    span = min(b - a for a, b in zip(xs, xs[1:])) if len(xs) > 1 else 40.0

    out: dict[str, float] = {}
    for x, y, t in words:
        if not _NUM.match(t):
            continue
        if y >= axis_y:            # 축보다 아래는 다른 차트다
            continue
        v = float(t.replace(",", ""))
        if not (RANGE_십억[0] <= v <= RANGE_십억[1]):
            continue
        # 가장 가까운 라벨. 절반 간격보다 멀면 그 차트 것이 아니다.
        ax, period = min(axis, key=lambda a: abs(a[0] - x))
        if abs(ax - x) > span * 0.5:
            continue
        if period not in out:
            out[period] = v
    return out


def read_pdf(path: Path, report_id: str, warn: list) -> list[dict]:
    """PDF 한 개에서 무선 서비스매출을 뽑는다."""
    facts = []
    for page in pdf_words(path):
        text = " ".join(t for _, _, t in page)
        # `KT – 무선` 쪽이고 서비스매출 차트가 있는 쪽만 본다.
        flat = text.replace(" ", "")
        if "무선" not in text or "서비스매출" not in flat:
            continue
        axis_y, axis = find_axis(page)
        if not axis:
            continue
        got = match_values(page, axis_y, axis)
        # **막대마다 값 라벨이 붙는다.** 축 라벨 수와 값 개수가 다르면 짝짓기가
        # 어긋난 것이라 통째로 버린다.
        #
        # 이 조건이 없을 때 2023Q3 자료가 라벨 5개 중 3개만 짝지어 **엉뚱한
        # 분기에 값을 붙였다** — 2023Q2 매출이 보고서마다 15,620 / 17,222 /
        # 16,344 억으로 갈렸다. 실제 재작성은 이 정도로 벌어지지 않는다.
        if len(got) != len(axis):
            warn.append(f"{report_id}: 값 {len(got)}개 ≠ 분기 {len(axis)}개 — 버림")
            continue
        for period, v in got.items():
            facts.append({
                "report_id": report_id, "period": period, "period_type": "quarter",
                "basis": "단일분기", "consolidation": "별도", "accounting": "K-IFRS",
                "metric_id": "revenue_wireless", "label_raw": "서비스매출(무선)",
                "value": round(v * 10, 2),          # 십억원 → 억원
                "unit": "억원", "page": "", "confidence": "auto",
            })
        break                                        # 무선 쪽은 하나뿐이다
    if not facts:
        warn.append(f"{report_id}: 무선 매출 차트를 못 찾음")
    return facts


def dedupe(facts, published) -> list[dict]:
    """같은 분기가 여러 자료에 나온다. 값이 다를 때만 남긴다(재작성)."""
    best = {}
    for f in facts:
        key = (f["metric_id"], f["period"], round(f["value"], 1))
        cur = best.get(key)
        if cur is None or published.get(f["report_id"], "") > published.get(cur["report_id"], ""):
            best[key] = f
    return list(best.values())


def main() -> None:
    ap = argparse.ArgumentParser(description="NDR PDF → facts.csv (부문별 매출)")
    ap.add_argument("--report", action="store_true", help="파일을 쓰지 않고 진단만")
    ap.add_argument("--limit", type=int, help="최근 N건만")
    args = ap.parse_args()

    reports = [r for r in csv.DictReader((REPO_DIR / "data" / "reports.csv").open(encoding="utf-8"))
               if r["doc_kind"] == "ndr" and r["local_path"].lower().endswith(".pdf")]
    reports.sort(key=lambda r: r["period"])
    if args.limit:
        reports = reports[-args.limit:]

    published = {r["report_id"]: r.get("published_at", "") for r in reports}
    facts, warn = [], []
    for r in reports:
        facts.extend(read_pdf(REPO_DIR / r["local_path"], r["report_id"], warn))

    print(f"NDR {len(reports)}건 · 차트 못 찾음 {len(warn)}건 · 수치 {len(facts)}개")
    facts = dedupe(facts, published)
    print(f"중복을 접은 뒤: {len(facts)}개")
    if facts:
        ps = sorted(f["period"] for f in facts)
        print(f"기간 {ps[0]} ~ {ps[-1]} ({len(set(ps))}개 분기)")
    if warn:
        print(f"\n못 찾은 자료 {len(warn)}건 (앞 8)")
        for w in warn[:8]:
            print("   ", w)

    if args.report:
        print("\n(--report 라 파일을 쓰지 않았다)")
        return
    removed, added = FS.replace_facts(PREFIX, facts)
    print(f"\nfacts.csv — ndr 줄 {removed}개 걷어내고 {added}개 넣음")


if __name__ == "__main__":
    main()
