# -*- coding: utf-8 -*-
"""端到端验证：新玩家开局 → 出顺子 → 出对子通关 → 下一关；并导出 DSL。"""

import json
import os
import sys
import urllib.error
import urllib.request

BASE = "http://localhost:8080"
APP = "ab2c10d4-71c8-45e6-80ac-30e7f02b0cf0"
HERE = os.path.dirname(os.path.abspath(__file__))


def token():
    with open(os.path.join(os.environ["TEMP"], "dify_token.txt"), encoding="utf-8") as f:
        return f.read().strip()


def call(method, path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Authorization", "Bearer " + token())
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def turn(query, conv, player):
    payload = {"inputs": {"player_id": player}, "files": [], "query": query, "conversation_id": conv}
    req = urllib.request.Request(
        BASE + "/console/api/apps/%s/advanced-chat/workflows/draft/run" % APP,
        data=json.dumps(payload).encode(), method="POST")
    req.add_header("Authorization", "Bearer " + token())
    req.add_header("Content-Type", "application/json")
    r = urllib.request.urlopen(req, timeout=180)
    conv_out, answer, status = conv, None, None
    for raw in r:
        line = raw.decode("utf-8", "replace").strip()
        if not line.startswith("data:"):
            continue
        body = line[5:].strip()
        if body == "[DONE]":
            break
        try:
            ev = json.loads(body)
        except Exception:
            continue
        if ev.get("conversation_id"):
            conv_out = ev["conversation_id"]
        if ev.get("event") == "workflow_finished":
            d = ev.get("data", {})
            status = d.get("status")
            answer = (d.get("outputs") or {}).get("answer")
    return conv_out, answer, status


def main():
    player = sys.argv[1] if len(sys.argv) > 1 else "replay1"
    conv = None
    for q in ["开始", "5 6 7 8 9", "3 3", "下一关"]:
        conv, ans, status = turn(q, conv, player)
        print("=" * 60)
        print("玩家>", q, "  [", status, "]")
        print(ans)
    print("\nconversation_id:", conv)

    # 导出 DSL
    st, body = call("GET", "/console/api/apps/%s/export?include_secret=false" % APP)
    print("\nexport dsl ->", st, len(body))
    if st == 200:
        d = os.path.join(HERE, "..", "dsl")
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, "斗地主-读心牌桌.yml")
        with open(path, "wb") as f:
            f.write(body)
        print("saved:", os.path.abspath(path))


if __name__ == "__main__":
    main()
