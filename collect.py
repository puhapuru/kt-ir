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
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

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


def build_download_url(bno: str, save_file_nm: str) -> str:
    """corp.kt.com 기준 실제 다운로드 URL 조립."""
    encoded_nm = urllib.parse.quote(save_file_nm, safe="")
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
        "downloadUrl": build_download_url(bno, save_file_nm) if bno and save_file_nm else "",
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
def download_file(item: dict, dest_dir: Path) -> Path | None:
    """메타데이터 항목의 파일을 다운로드. 실패/의심 시 None."""
    url = item.get("downloadUrl", "")
    if not url:
        return None
    safe_name = f"{item['bno']}_{item['saveFileNm']}"
    dest = dest_dir / safe_name
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0",
            "Referer": REFERRER,
            "Accept": "*/*",
        }
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = resp.read()
        # 파일 시그니처 확인
        if len(data) < 5000:
            print(f"  [다운로드 의심] {safe_name}: 너무 작음 ({len(data)} bytes) — 건너뜀", file=sys.stderr)
            return None
        dest.write_bytes(data)
        print(f"  다운로드: {safe_name} ({len(data)} bytes)")
        return dest
    except Exception as e:
        print(f"  [다운로드 실패] {safe_name}: {type(e).__name__}: {e}", file=sys.stderr)
        return None


# ── 메인 ──────────────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(description="KT IR 자료 메타데이터 수집")
    parser.add_argument("--download", action="store_true",
                        help="신규 항목 파일을 data/에 임시 다운로드")
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

    if args.download and new_items:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        print(f"\n--- 신규 파일 다운로드 (data/) ---")
        downloaded = 0
        for it in new_items:
            if download_file(it, DATA_DIR):
                downloaded += 1
        print(f"다운로드 완료: {downloaded}/{len(new_items)}건")

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
