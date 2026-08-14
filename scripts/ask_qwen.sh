#!/usr/bin/env bash
# 정형화된 코드 조각을 로컬 Qwen에 위임한다. CLAUDE.md의 "Qwen 위임 정책" 참조.
# 사용: ./scripts/ask_qwen.sh "명세 텍스트"  또는  ./scripts/ask_qwen.sh -f spec.md
set -euo pipefail
: "${QWEN_HOST:=http://100.99.168.90:11434}"   # 데스크톱, Tailscale 주소
: "${QWEN_MODEL:=qwen2.5-coder:14b-instruct}"

if [[ "${1:-}" == "-f" ]]; then
  PROMPT="$(cat "$2")"
else
  PROMPT="${1:?사용법: ask_qwen.sh \"명세\" 또는 ask_qwen.sh -f spec.md}"
fi

# 규칙 파일을 명세 앞에 붙인다. **짧게 유지하는 것이 핵심이다.**
#
# 2026-08-11 qwen-harness 실측(과제 5개 × 3회, 과제 완전통과 기준):
#   규칙 1,822자  0%   ← 길게 쌓은 규칙은 아예 해롭다
#   규칙 없음     20%
#   규칙 191자    40%  ← 짧게 줄이니 가장 좋다
#
# 길면 왜 나쁜가: 규칙이 *다른 과제의* 실패담이라 이번 과제엔 잡음이고,
# 증상만 부분적으로 흉내 낸다(WHERE 절을 안 쓰면서 job_id 만 파라미터에 넣는 식).
# **규칙을 늘리고 싶으면 먼저 하네스로 재 볼 것.** 늘리는 게 개선이라는
# 보장이 없다는 것이 이 실측의 결론이다.
RULES=""
for f in "$HOME/qwen-rules.md" "QWEN.md"; do
  [[ -f "$f" ]] && RULES+="$(cat "$f")"$'\n\n'
done
[[ -n "$RULES" ]] && PROMPT="${RULES}---

아래가 이번에 작성할 코드의 명세다.

${PROMPT}"

python3 - "$QWEN_HOST" "$QWEN_MODEL" "$PROMPT" <<'PYEOF'
import json
import sys
import urllib.request

host, model, prompt = sys.argv[1], sys.argv[2], sys.argv[3]

payload = {
    "model": model,
    "messages": [
        {"role": "system", "content": "You are a Python code generator. Output only code. No explanation, no markdown fences."},
        {"role": "user", "content": prompt},
    ],
    # GPT-SoVITS 상주 VRAM 사용량은 실측 2.55GB뿐이라(RX 9070, 16GB), 14b
    # 모델과 동시에 GPU에 있어도 넉넉하다 — CPU로 강제하지 않는다.
    "options": {"temperature": 0.1},
    "stream": False,
}

req = urllib.request.Request(
    f"{host}/api/chat",
    data=json.dumps(payload).encode("utf-8"),
    headers={"Content-Type": "application/json"},
)
with urllib.request.urlopen(req, timeout=300) as resp:
    data = json.load(resp)

content = data["message"]["content"].strip()
# 지시해도 마크다운 펜스로 감싸는 경우가 있어 벗겨낸다.
if content.startswith("```"):
    lines = content.split("\n")
    if lines[-1].strip() == "```":
        lines = lines[1:-1]
    else:
        lines = lines[1:]
    content = "\n".join(lines)

print(content)
PYEOF
