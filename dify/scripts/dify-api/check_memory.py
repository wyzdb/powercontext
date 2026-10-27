# -*- coding: utf-8 -*-
"""查看 PowerContext 里某个存档的案卷。"""

import json
import sys
import urllib.request

BASE = "http://localhost:8000"


def post(path, obj):
    req = urllib.request.Request(BASE + path, data=json.dumps(obj).encode("utf-8"), method="POST")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    title = sys.argv[1] if len(sys.argv) > 1 else "ddz-tester"
    scopes = get("/v1/scopes")["items"]
    scope = next((s for s in scopes if s["title"] == title), None)
    if not scope:
        print("scope not found:", title, "available:", [s["title"] for s in scopes])
        return
    print("scope:", scope["scope_id"], scope["title"])
    data = post("/v1/atomic-memory/list", {"scope_id": scope["scope_id"], "limit": 30})
    items = data.get("items") or []
    print("memories:", len(items))
    for it in items:
        print("  [%s] %s" % (it.get("kind"), it.get("text")))


if __name__ == "__main__":
    main()
