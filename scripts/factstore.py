#!/usr/bin/env python3
"""`data/facts.csv` 를 여러 추출기가 함께 쓰기 위한 공용 장치.

추출기가 늘어나면(Financial Indicator · DART · Factsheet …) 각자 파일을
통째로 덮어써서 **먼저 넣은 것이 사라진다.** 그래서 추출기마다 자기
`report_id` 앞머리를 정해 두고, **자기 몫만 갈아 끼운다.**

    financial_indicator_...   ← extract_findicator.py
    dart_...                  ← collect_dart.py
    factsheet_...             ← (아직 없음)
"""

from __future__ import annotations

import csv
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_DIR / "data"
FACTS_CSV = DATA_DIR / "facts.csv"
REPORTS_CSV = DATA_DIR / "reports.csv"

FACTS_COLUMNS = [
    "report_id", "period", "period_type", "basis", "consolidation", "accounting",
    "metric_id", "label_raw", "value", "unit", "page", "confidence",
]
REPORTS_COLUMNS = [
    "report_id", "doc_kind", "period", "period_type", "published_at",
    "title", "category", "url", "filename", "sha256", "bytes", "local_path",
]


def _read(path: Path, columns: list[str]) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return [{c: r.get(c, "") for c in columns} for r in csv.DictReader(f)]


def _write(path: Path, columns: list[str], rows: list[dict], sort_key) -> None:
    """임시 파일에 쓰고 갈아 끼운다 — 중간에 죽어도 원본이 안 깨진다."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    rows = sorted(rows, key=sort_key)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=columns)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in columns})
    tmp.replace(path)


def replace_facts(prefix: str, new_rows: list[dict]) -> tuple[int, int]:
    """`report_id` 가 `prefix` 로 시작하는 줄만 갈아 끼운다.

    돌려주는 값은 `(지운 줄 수, 넣은 줄 수)`.
    """
    kept = [r for r in _read(FACTS_CSV, FACTS_COLUMNS)
            if not (r.get("report_id") or "").startswith(prefix)]
    removed = len(_read(FACTS_CSV, FACTS_COLUMNS)) - len(kept)
    _write(FACTS_CSV, FACTS_COLUMNS, kept + list(new_rows),
           lambda r: (r.get("period") or "", r.get("consolidation") or "",
                      r.get("metric_id") or "", r.get("report_id") or ""))
    return removed, len(new_rows)


def upsert_reports(new_rows: list[dict]) -> int:
    """`reports.csv` 에 자료 원장을 더한다. 같은 `report_id` 는 덮어쓴다.

    DART 처럼 내려받는 파일이 없는 출처도 원장에 넣어야 `facts.report_id` 가
    끊기지 않는다(`build_db.py --check` 가 그걸 본다).
    """
    rows = {r["report_id"]: r for r in _read(REPORTS_CSV, REPORTS_COLUMNS)}
    for r in new_rows:
        rows[r["report_id"]] = {c: r.get(c, "") for c in REPORTS_COLUMNS}
    _write(REPORTS_CSV, REPORTS_COLUMNS, list(rows.values()),
           lambda r: (r.get("period") or "", r.get("published_at") or "",
                      r.get("report_id") or ""))
    return len(new_rows)
