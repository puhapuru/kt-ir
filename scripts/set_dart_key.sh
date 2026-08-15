#!/usr/bin/env bash
# DART 인증키를 .env 에 넣고 바로 검증한다.
#
#   ~/kt-ir/scripts/set_dart_key.sh
#
# 키는 **화면에 찍히지 않는다**(`read -s`). 붙여넣고 엔터만 치면 된다.
# 채팅이나 명령 이력에 키가 남지 않게 하려는 것이다.

set -uo pipefail

ENV_FILE="$HOME/kt-ir/.env"

printf 'DART 인증키를 붙여넣고 엔터 (화면에 안 보입니다): '
read -rs KEY
echo

KEY="$(printf '%s' "$KEY" | tr -d '[:space:]')"

if [ -z "$KEY" ]; then
  echo "아무것도 안 들어왔다. 그만둔다." >&2
  exit 1
fi
if [ ${#KEY} -lt 20 ]; then
  echo "키가 너무 짧다(${#KEY}자). DART 키는 40자 안팎이다 — 다시 확인할 것." >&2
  exit 1
fi

echo "검증 중..."
RESP="$(curl -s -m 30 "https://opendart.fss.or.kr/api/list.json?crtfc_key=${KEY}&corp_code=00126462&bgn_de=20240101&end_de=20240131" || true)"
STATUS="$(printf '%s' "$RESP" | grep -oE '"status"[[:space:]]*:[[:space:]]*"[0-9]+"' | grep -oE '[0-9]+' | head -1)"

case "$STATUS" in
  000|013)
    echo "  키가 살아 있다 (status $STATUS)" ;;
  010)
    echo "  등록되지 않은 인증키다. 발급 메일의 키를 다시 확인할 것." >&2; exit 1 ;;
  011)
    echo "  사용할 수 없는 키다(사용중지). DART 에서 상태를 볼 것." >&2; exit 1 ;;
  020)
    echo "  요청 한도 초과. 잠시 뒤 다시." >&2; exit 1 ;;
  "")
    echo "  응답을 못 읽었다. 인터넷 상태를 확인할 것." >&2; exit 1 ;;
  *)
    echo "  status=$STATUS — 예상 밖이다. 그래도 저장할지 판단 필요." >&2; exit 1 ;;
esac

# 기존 줄이 있으면 갈아 끼운다(중복으로 쌓이면 어느 것이 쓰이는지 헷갈린다).
touch "$ENV_FILE"; chmod 600 "$ENV_FILE"
TMP="$(mktemp)"; chmod 600 "$TMP"
grep -v '^DART_API_KEY=' "$ENV_FILE" > "$TMP" 2>/dev/null || true
printf 'DART_API_KEY=%s\n' "$KEY" >> "$TMP"
mv "$TMP" "$ENV_FILE"

echo "  $ENV_FILE 에 저장했다 (${#KEY}자, 권한 600)"
echo
echo "다음:  cd ~/kt-ir && .venv/bin/python scripts/collect_dart.py --years 2015-2025"
