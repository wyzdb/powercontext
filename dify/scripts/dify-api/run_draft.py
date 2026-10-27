# -*- coding: utf-8 -*-
"""跑草稿工作流；支持复用会话，验证牌局状态与记忆。"""

import json
import os
import sys
import urllib.error
import urllib.request

BASE = "http://localhost:8080"
APP_ID = "ab2c10d4-71c8-45e6-80ac-30e7f02b0cf0"


def token():
    with open(os.path.join(os.environ["TEMP"], "dify_token.txt"), encoding="utf-8") as f:
        return f.read().strip()


def run(query, conv_id=None, player_id="tester", quiet=False):
    payload = {
        "inputs": {"player_id": player_id},
        "files": [],
        "query": query,
        "conversation_id": conv_id,
    }
    req = urllib.request.Request(
        BASE + "/console/api/apps/%s/advanced-chat/workflows/draft/run" % APP_ID,
        data=json.dumps(payload).encode(),
        method="POST",
    )
    req.add_header("Authorization", "Bearer " + token())
    req.add_header("Content-Type", "application/json")
    try:
        r = urllib.request.urlopen(req, timeout=180)
    except urllib.error.HTTPError as e:
        print("HTTP", e.code, e.read().decode("utf-8", "replace")[:1500])
        return None, None, None

    conv = conv_id
    answer = None
    failed = None
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
            conv = ev["conversation_id"]
        e = ev.get("event")
        if e == "node_finished" and not quiet:
            d = ev.get("data", {})
            if d.get("status") != "succeeded":
                print("[node-fail] %s %s" % (d.get("title"), str(d.get("error"))[:300]))
        elif e == "workflow_finished":
            d = ev.get("data", {})
            if d.get("status") != "succeeded":
                failed = d.get("error")
            outs = d.get("outputs") or {}
            answer = outs.get("answer")
        elif e == "error":
            failed = ev

    if failed:
        print("[FAILED]", str(failed)[:800])
    if answer is not None:
        print(answer)
    return conv, answer, failed


if __name__ == "__main__":
    q = sys.argv[1] if len(sys.argv) > 1 else "开始"
    cid = sys.argv[2] if len(sys.argv) > 2 else None
    conv, _, _ = run(q, cid)
    print("\n--- conversation_id:", conv)
