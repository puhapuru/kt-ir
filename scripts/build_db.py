#!/usr/bin/env python3
"""`data/` 의 CSV 를 읽어 조회용 SQLite 를 만든다.

    python3 scripts/build_db.py --check

**CSV 가 정본이고 이 DB 는 산출물이다.** `build/` 는 `.gitignore` 로 막혀 있다.
정본을 텍스트로 두는 이유는 git diff 가 읽히고 사람이 리뷰할 수 있어서다 —
SQLite 를 커밋하면 무엇이 바뀌었는지 아무도 못 본다. 대신 질의는 SQL 이
편하니 필요할 때 만들어 쓴다.

    sqlite3 build/kt_ir.sqlite \\
      "SELECT period, value FROM facts WHERE metric_id='arpu_wireless' ORDER BY period"
"""

from __future__ import annotations

import argparse
import csv
import sqlite3
import sys
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_DIR / "data"

TABLES = {
    "reports": [
        "report_id", "doc_kind", "period", "period_type", "published_at",
        "title", "category", "url", "filename", "sha256", "bytes", "local_path",
    ],
    "metrics": [
        "metric_id", "name", "category", "unit", "parent_id", "description",
    ],
    "facts": [
        "report_id", "period", "period_type", "basis", "consolidation",
        "accounting", "metric_id", "label_raw", "value", "unit", "page",
        "confidence",
    ],
}


def create_schema(conn: sqlite3.Connection) -> None:
    """표 세 개와 인덱스를 만든다.

    외래키는 **선언만 하고 강제하지 않는다**(`PRAGMA foreign_keys` 를 켜지
    않는다). 수치를 먼저 넣고 지표 사전을 나중에 채우는 일이 흔한데, 강제하면
    그때마다 적재가 통째로 실패한다. 대신 `--check` 가 끊긴 참조를 알려 준다.
    """
    c = conn.cursor()
    c.execute("""
        CREATE TABLE reports (
            report_id    TEXT PRIMARY KEY,
            doc_kind     TEXT,
            period       TEXT,
            period_type  TEXT,
            published_at TEXT,
            title        TEXT,
            category     TEXT,
            url          TEXT,
            filename     TEXT,
            sha256       TEXT,
            bytes        INTEGER,
            local_path   TEXT
        )
    """)
    c.execute("""
        CREATE TABLE metrics (
            metric_id   TEXT PRIMARY KEY,
            name        TEXT,
            category    TEXT,
            unit        TEXT,
            parent_id   TEXT,
            description TEXT
        )
    """)
    c.execute("""
        CREATE TABLE facts (
            report_id     TEXT,
            period        TEXT,
            period_type   TEXT,
            basis         TEXT,
            consolidation TEXT,
            accounting    TEXT,
            metric_id     TEXT,
            label_raw     TEXT,
            value         REAL,
            unit          TEXT,
            page          INTEGER,
            confidence    TEXT,
            FOREIGN KEY (report_id) REFERENCES reports(report_id),
            FOREIGN KEY (metric_id) REFERENCES metrics(metric_id)
        )
    """)
    for stmt in (
        "CREATE INDEX idx_facts_period    ON facts(period)",
        "CREATE INDEX idx_facts_metric    ON facts(metric_id)",
        "CREATE INDEX idx_facts_report    ON facts(report_id)",
        "CREATE INDEX idx_reports_period  ON reports(period)",
    ):
        c.execute(stmt)
    conn.commit()


def load_csv(conn: sqlite3.Connection, table: str, path: Path, columns: list[str]) -> int:
    """CSV 한 장을 적재한다. 파일이 없으면 빈 표로 두고 경고만 찍는다."""
    if not path.exists():
        print(f"경고: {path.name} 이 없다 — {table} 는 빈 표로 둔다.", file=sys.stderr)
        return 0

    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        missing = [c for c in columns if c not in (reader.fieldnames or [])]
        if missing:
            print(f"경고: {path.name} 에 칸이 없다 — {missing}", file=sys.stderr)
        rows = []
        for row in reader:
            # 빈 문자열은 NULL 로. 0 은 살려야 하므로 `or None` 을 쓰지 않는다.
            rows.append([
                (row.get(c) if (row.get(c) or "") != "" else None) for c in columns
            ])

    if rows:
        marks = ", ".join("?" * len(columns))
        cols = ", ".join(columns)
        conn.executemany(f"INSERT INTO {table} ({cols}) VALUES ({marks})", rows)
        conn.commit()
    return len(rows)


def run_checks(conn: sqlite3.Connection) -> int:
    """행 수와 끊긴 참조를 보여 준다. 문제 건수를 돌려준다."""
    c = conn.cursor()
    print("\n행 수")
    for t in ("reports", "metrics", "facts"):
        n = c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"  {t:<9} {n:>6}")

    problems = 0
    for label, sql in (
        ("metrics 에 없는 metric_id",
         "SELECT DISTINCT metric_id FROM facts "
         "WHERE metric_id IS NOT NULL AND metric_id NOT IN (SELECT metric_id FROM metrics) LIMIT 10"),
        ("reports 에 없는 report_id",
         "SELECT DISTINCT report_id FROM facts "
         "WHERE report_id IS NOT NULL AND report_id NOT IN (SELECT report_id FROM reports) LIMIT 10"),
    ):
        bad = [r[0] for r in c.execute(sql)]
        problems += len(bad)
        print(f"\n{label}: {bad if bad else '없음 ✓'}")
    return problems


def main() -> None:
    ap = argparse.ArgumentParser(description="data/*.csv → SQLite")
    ap.add_argument("--out", default=str(REPO_DIR / "build" / "kt_ir.sqlite"),
                    help="만들 SQLite 경로")
    ap.add_argument("--check", action="store_true", help="만든 뒤 점검 결과를 찍는다")
    args = ap.parse_args()

    db_path = Path(args.out)
    db_path.parent.mkdir(parents=True, exist_ok=True)   # build/ 가 없으면 연결이 실패한다
    if db_path.exists():
        db_path.unlink()

    conn = sqlite3.connect(db_path)
    try:
        create_schema(conn)
        # reports → metrics → facts 순. facts 가 나머지를 참조한다.
        total = 0
        for table in ("reports", "metrics", "facts"):
            n = load_csv(conn, table, DATA_DIR / f"{table}.csv", TABLES[table])
            total += n
        print(f"{db_path} 생성 — {total}행 적재")
        problems = run_checks(conn) if args.check else 0
    finally:
        conn.close()

    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
