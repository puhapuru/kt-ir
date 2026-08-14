#!/usr/bin/env python3
"""
kt-ir 수집 스크립드

kt.com 모바일 IR 데이터 페이지 API로 프레젠테이션/재무데이터/가입자현황
목록을 가져와 메타데이터를 축적한다.

- 목록 API: POST https://m.rdi.kt.com/corp/reports/v1.0/BS00000008/files
- 파일 다운로드 호스트: https://corp.kt.com/attach/irdata/<bno>/<파일명>
- 축적 대상: 메타데이터만 (원본 파일은 별도 스토리지)

사용:
  python3 collect.py                      # 전체 수집 + 메타데이터 갱신
  python3 collect.py --download           # 신규 파일 임시 다운로드(data/)
  python3 collect.py --list-only          # 목록만 출력하고 저장 안 함
  python3 collect.py --dry-run            # 실제 저장 없이 신규 항목만 출력
  python3 collect.py --tab 03             # 프레젠테이션만
  python3 collect.py --year 2026          # 특정 연도만
"""

import argparse
import csv
import hashlib
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "scripts"))
import period as P  # noqa: E402  — 제목에서 종류·기간을 뽑는다

# ── 상수 ──────────────────────────────────────────────────────────────────────
M_RDI = "https://m.rdi.kt.com"
CORP = "https://corp.kt.com"
M_CORP = "https://m.corp.kt.com"

API_FILES = "/corp/reports/v1.0/BS00000008/files"
API_YEARS = "/corp/reports/v1.0/BS00000008/years"

# 탭 구분 (genlCtgType → 이름)
CTG = {
    "01": "가입자현황",
    "02": "재무데이터",
    "03": "프리젠테이션",
}

UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
REFERRER = M_CORP + "/html/investors/resources/data.html"

REPO_DIR = Path(__file__).resolve().parent
METADATA_FILE = REPO_DIR / "metadata" / "ir_metadata.json"
DATA_DIR = REPO_DIR / "data"
RAW_DIR = REPO_DIR / "raw"                      # 원본을 기간별로 둔다
REPORTS_CSV = DATA_DIR / "reports.csv"

REPORTS_COLUMNS = [
    "report_id", "doc_kind", "period", "period_type", "published_at",
    "title", "category", "url", "filename", "sha256", "bytes", "local_path",
]

# 내려받은 것이 진짜 문서인지 보는 최소 크기. KT 서버는 실패해도 200 과 함께
# **1,832바이트짜리 오류 안내 HTML** 을 준다 — 그대로 저장하면 PDF 인 줄 알고
# 넘어간다(실제로 `65_kthp1314690005566.pdf` 가 그렇게 들어와 있었다).
MIN_FILE_BYTES = 5_000

# 파일 앞머리로 형식을 본다. 오류 페이지는 `<!DOCTYPE`·`<html` 로 시작한다.
MAGIC = {
    b"%PDF": "pdf",
    b"PK\x03\x04": "zip",       # xlsx·pptx 는 zip 이다
    b"\xd0\xcf\x11\xe0": "ole",  # 옛 xls·ppt
}

# ── API 호출 ──────────────────────────────────────────────────────────────────
def api_post(path: str, data: dict, referer: str = REFERRER) -> dict:
    """m.rdi.kt.com 으로 POST해서 JSON 응답 반환."""
    body = urllib.parse.urlencode(data).encode()
    headers = {
        "User-Agent": UA,
        "Accept": "application/json, text/javascript, */*; q=0.8",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
        "Origin": M_RDI,
        "Referer": referer,
    }
    req = urllib.request.Request(M_RDI + path, data=body, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        body_bytes = e.read()
        try:
            return json.loads(body_bytes.decode("utf-8", "replace"))
        except Exception:
            print(f"[API 오류] {path} : HTTP {e.code}", file=sys.stderr)
            print(f"  body: {body_bytes.decode('utf-8','replace')[:300]}", file=sys.stderr)
            raise
    except Exception as e:
        print(f"[API 예외] {path} : {type(e).__name__}: {e}", file=sys.stderr)
        raise


def list_all(ctg_type: str, year: str | None = None) -> list[dict]:
    """특정 탭의 전체 목록을 가져온다 (페이지네이션 처리)."""
    page = 1
    limit = 100
    all_items: list[dict] = []
    while True:
        payload = {
            "limit": str(limit),
            "offset": str(limit * (page - 1) + 1),
            "genlCtgType": ctg_type,
            "page": str(page),
        }
        if year:
            payload["yyInfo"] = year
        res = api_post(API_FILES, payload)
        data = res.get("data", {})
        items = data.get("reportList", [])
        if not items:
            break
        all_items.extend(items)
        tot = int(data.get("totCnt", 0))
        if len(all_items) >= tot:
            break
        page += 1
        if page > 200:
            print(f"[경고] {ctg_type} 탭 페이지 200 초과 — 중단", file=sys.stderr)
            break
    return all_items


def build_download_url(bno: str, save_file_nm: str, save_file_path: str = "") -> str:
    """실제 다운로드 URL 조립.

    **경로 방식이 두 가지다.** API 의 `saveFilePath` 를 그대로 쓰는 것이 맞다.

        최신  /attach/irdata/10893/      → corp.kt.com/attach/irdata/10893/<파일>
        옛것  /data/attach/144/          → corp.kt.com/data/attach/144/<파일>

    `bno` 로 `/attach/irdata/<bno>/` 를 만들어 붙이던 방식은 옛 자료에서
    **HTTP 200 과 함께 1,832바이트 오류 HTML** 을 돌려받는다. 실패가 아니라
    성공처럼 보여서, 최소 크기·앞머리 검사가 없었으면 그대로 저장될 뻔했다.
    482건 중 **304건이 이 경로**였다.
    """
    encoded_nm = urllib.parse.quote(save_file_nm, safe="")
    path = (save_file_path or "").strip()
    if path:
        return f"{CORP}/{path.strip('/')}/{encoded_nm}"
    return f"{CORP}/attach/irdata/{bno}/{encoded_nm}"


def infer_year_from_reg(reg_date: str) -> str | None:
    """regDate(예: 2026.08.12 09:52:17:359)에서 연도 추출."""
    m = re.match(r"(\d{4})\.", reg_date)
    return m.group(1) if m else None


# ── 메타데이터 로드/저장 ──────────────────────────────────────────────────────
def load_metadata() -> dict:
    """기존 메타데이터를 로드. 없으면 빈 구조 반환."""
    if METADATA_FILE.exists():
        with open(METADATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"items": [], "lastCollected": None, "apiVersion": "BS00000008"}


def save_metadata(meta: dict) -> None:
    """메타데이터를 파일에 저장."""
    METADATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    out = {
        "lastCollected": meta.get("lastCollected"),
        "apiVersion": meta.get("apiVersion", "BS00000008"),
        "counts": {
            ctg: sum(1 for it in meta["items"] if it["genlCtgType"] == ctg)
            for ctg in CTG
        },
        "items": meta["items"],
    }
    tmp = METADATA_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2, sort_keys=False)
    tmp.replace(METADATA_FILE)


# ── 항목 정규화 ───────────────────────────────────────────────────────────────
def normalize_item(item: dict) -> dict:
    """API 응답 항목을 메타데이터 스키마로 변환."""
    files = item.get("atcFileList", [])
    primary = files[0] if files else {}
    bno = item.get("bno", "")
    save_file_nm = primary.get("saveFileNm", "")
    return {
        "bno": bno,
        "genlCtgType": item.get("genlCtgType", ""),
        "genlCtgTypeNm": item.get("genlCtgTypeNm", ""),
        "btitle": item.get("btitle", ""),
        "regDate": item.get("regDate", ""),
        "fileNo": primary.get("fileNo", ""),
        "saveFileNm": save_file_nm,
        "saveFileSize": primary.get("saveFileSize", "0"),
        "saveFilePath": primary.get("saveFilePath", "") or "",
        "downloadUrl": (
            build_download_url(bno, save_file_nm, primary.get("saveFilePath", ""))
            if save_file_nm else ""
        ),
        "collectedAt": datetime.now(timezone.utc).isoformat(),
    }


# ── 신규 항목 판별 ────────────────────────────────────────────────────────────
def find_new_items(existing: list[dict], fresh: list[dict]) -> list[dict]:
    """기존 메타데이터에 없는 신규 항목만 반환."""
    existing_keys = {(it["bno"], it["genlCtgType"]) for it in existing}
    new: list[dict] = []
    for it in fresh:
        key = (it.get("bno", ""), it.get("genlCtgType", ""))
        if key not in existing_keys:
            new.append(it)
    return new


# ── 다운로드 (옵션) ───────────────────────────────────────────────────────────
def report_id(item: dict, doc: dict) -> str:
    """`facts.csv` 에서 사람이 알아볼 수 있으면서 겹치지 않는 id.

    `bno` 만 쓰면 짧지만 `10893` 이 무슨 자료인지 알 수 없다. 사람이 수치를
    손으로 적어 넣을 때 이 id 를 써야 하므로 읽히는 편이 낫다. 뒤에 `bno` 를
    붙여 유일성을 보장한다 — 같은 분기에 국문·영문 NDR 이 따로 올라온다.
    """
    return f"{doc['doc_kind']}_{doc['period'] or 'undated'}_{item['bno']}"


def looks_like_document(data: bytes) -> str | None:
    """앞머리를 보고 형식을 돌려준다. 문서가 아니면 None."""
    for magic, kind in MAGIC.items():
        if data.startswith(magic):
            return kind
    return None


def download_file(item: dict, doc: dict) -> dict | None:
    """원본을 `raw/<기간>/` 에 받는다. 이미 있으면 받지 않는다.

    **이미 있으면 건너뛰는 것이 중요하다.** git 은 바이너리를 버전마다 통째로
    저장한다. 매번 다시 받아 덮어쓰면 바이트가 1비트만 달라도 300MB 짜리
    사본이 계속 쌓인다. IR 자료는 한 번 공시되면 안 바뀌니 파일이 있으면
    그대로 두면 된다.
    """
    url = item.get("downloadUrl", "")
    fname = item.get("saveFileNm", "")
    if not url or not fname:
        return None

    dest_dir = RAW_DIR / P.raw_dir(doc["period"])
    dest = dest_dir / fname
    rel = str(dest.relative_to(REPO_DIR))

    if dest.exists() and dest.stat().st_size >= MIN_FILE_BYTES:
        data = dest.read_bytes()
        return {"sha256": hashlib.sha256(data).hexdigest(),
                "bytes": len(data), "local_path": rel, "skipped": True}

    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0",
        "Referer": REFERRER,
        "Accept": "*/*",
    }
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = resp.read()
    except Exception as e:
        print(f"  [실패] {fname}: {type(e).__name__}: {e}", file=sys.stderr)
        return None

    # 서버가 200 으로 오류 페이지를 주는 일이 있다. 두 겹으로 거른다.
    if len(data) < MIN_FILE_BYTES:
        print(f"  [의심] {fname}: 너무 작다 ({len(data)}바이트) — 오류 페이지로 보고 버린다",
              file=sys.stderr)
        return None
    if looks_like_document(data) is None:
        head = data[:16].decode("latin-1", "replace")
        print(f"  [의심] {fname}: 문서가 아니다 (앞머리 {head!r}) — 버린다", file=sys.stderr)
        return None

    dest_dir.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    print(f"  받음: {rel} ({len(data):,}바이트)")
    return {"sha256": hashlib.sha256(data).hexdigest(),
            "bytes": len(data), "local_path": rel, "skipped": False}


# ── reports.csv ───────────────────────────────────────────────────────────────
def load_reports() -> dict[str, dict]:
    """기존 `reports.csv` 를 report_id 로 색인해 읽는다."""
    if not REPORTS_CSV.exists():
        return {}
    with REPORTS_CSV.open(newline="", encoding="utf-8") as f:
        return {r["report_id"]: r for r in csv.DictReader(f) if r.get("report_id")}


def save_reports(rows: dict[str, dict]) -> None:
    """`reports.csv` 를 통째로 다시 쓴다. 기간·공시일 순으로 정렬한다.

    정렬을 고정하는 이유는 **git diff 를 읽히게** 하려는 것이다. 순서가
    들쭉날쭉하면 한 줄 추가에도 파일 전체가 바뀐 것처럼 보인다.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ordered = sorted(rows.values(),
                     key=lambda r: (r.get("period") or "", r.get("published_at") or "",
                                    r.get("report_id") or ""))
    tmp = REPORTS_CSV.with_suffix(".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=REPORTS_COLUMNS)
        w.writeheader()
        for r in ordered:
            w.writerow({c: r.get(c, "") for c in REPORTS_COLUMNS})
    tmp.replace(REPORTS_CSV)


# ── 메인 ──────────────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(description="KT IR 자료 메타데이터 수집")
    parser.add_argument("--download", action="store_true",
                        help="원본을 raw/<기간>/ 에 받고 reports.csv 에 기록")
    parser.add_argument("--all", action="store_true",
                        help="--download 대상을 누적 전체로 (이미 받은 것은 건너뛴다)")
    parser.add_argument("--list-only", action="store_true",
                        help="목록만 출력하고 저장하지 않음")
    parser.add_argument("--tab", choices=["01", "02", "03"],
                        help="특정 탭만 수집 (기본: 전체)")
    parser.add_argument("--year", type=str,
                        help="특정 연도만 필터링 (예: 2026)")
    parser.add_argument("--dry-run", action="store_true",
                        help="실제 저장 없이 신규 항목만 출력")
    args = parser.parse_args()

    tabs = [args.tab] if args.tab else ["01", "02", "03"]

    print(f"===== KT IR 수집 시작 ({datetime.now(timezone.utc).isoformat()}) =====")
    print(f"  대상 탭: {', '.join(tabs)}  ( {', '.join(CTG[t] for t in tabs)} )")
    if args.year:
        print(f"  연도 필터: {args.year}")

    existing = load_metadata()
    existing_items = existing.get("items", [])
    print(f"  기존 누적 항목: {len(existing_items)}건")

    fresh_all: list[dict] = []
    for ctg in tabs:
        print(f"\n--- 탭 {ctg} ({CTG[ctg]}) ---")
        try:
            items = list_all(ctg, args.year)
            print(f"  가져온 항목: {len(items)}건")
        except Exception as e:
            print(f"  [탭 {ctg} 수집 실패] {e}", file=sys.stderr)
            continue
        fresh_all.extend(items)

    normalized = [normalize_item(it) for it in fresh_all]
    print(f"\n전체 정규화 완료: {len(normalized)}건")

    if args.list_only:
        print("\n===== 목록 (정규화) =====")
        for it in sorted(normalized, key=lambda x: x["regDate"], reverse=True):
            print(f"  [{it['genlCtgType']}] {it['btitle']}")
            print(f"       reg={it['regDate']} bno={it['bno']} file={it['saveFileNm']} size={it['saveFileSize']}")
            print(f"       download: {it['downloadUrl']}")
        return

    new_items = find_new_items(existing_items, normalized)
    print(f"\n신규 항목: {len(new_items)}건")

    if args.dry_run:
        print("\n===== 신규 항목 (dry-run) =====")
        for it in sorted(new_items, key=lambda x: x["regDate"], reverse=True):
            print(f"  [{it['genlCtgType']}] {it['btitle']}")
            print(f"       reg={it['regDate']} bno={it['bno']} file={it['saveFileNm']}")
            print(f"       download: {it['downloadUrl']}")
        return

    if args.download:
        # `--all` 이면 누적 전체를 대상으로 한다. 이미 받은 것은 건너뛰므로
        # 여러 번 돌려도 안전하고, 중간에 끊긴 수집을 이어받을 때 쓴다.
        targets = (existing_items + new_items) if args.all else new_items
        reports = load_reports()
        got = skipped = failed = 0
        print(f"\n--- 원본 내려받기 (raw/) — 대상 {len(targets)}건 ---")
        for it in targets:
            doc = P.parse_doc(it.get("btitle", ""), it.get("saveFileNm", ""),
                              it.get("genlCtgTypeNm", ""))
            rid = report_id(it, doc)
            info = download_file(it, doc)
            if info is None:
                failed += 1
                continue
            skipped += info["skipped"]
            got += not info["skipped"]
            reports[rid] = {
                "report_id": rid,
                "doc_kind": doc["doc_kind"],
                "period": doc["period"],
                "period_type": doc["period_type"],
                "published_at": (it.get("regDate") or "")[:10].replace(".", "-"),
                "title": doc["title"],
                "category": it.get("genlCtgTypeNm", ""),
                "url": it.get("downloadUrl", ""),
                "filename": it.get("saveFileNm", ""),
                "sha256": info["sha256"],
                "bytes": info["bytes"],
                "local_path": info["local_path"],
            }
        save_reports(reports)
        print(f"내려받기 끝 — 새로 {got}건 · 이미 있어 건너뜀 {skipped}건 · 실패 {failed}건")
        print(f"reports.csv: 누적 {len(reports)}건")

    merged_items = existing_items + new_items
    seen: dict[tuple, dict] = {}
    for it in merged_items:
        key = (it["bno"], it["genlCtgType"])
        if key not in seen or it["collectedAt"] > seen[key]["collectedAt"]:
            seen[key] = it
    merged_items = list(seen.values())
    merged_items.sort(key=lambda x: x["regDate"], reverse=True)

    meta = {
        "items": merged_items,
        "lastCollected": datetime.now(timezone.utc).isoformat(),
        "apiVersion": "BS00000008",
    }
    save_metadata(meta)

    counts = {ctg: sum(1 for it in merged_items if it["genlCtgType"] == ctg) for ctg in CTG}
    print(f"\n===== 수집 완료 =====")
    print(f"  누적 메타데이터: {len(merged_items)}건")
    for ctg in CTG:
        print(f"    {CTG[ctg]}: {counts[ctg]}건")
    print(f"  마지막 수집: {meta['lastCollected']}")


if __name__ == "__main__":
    main()
