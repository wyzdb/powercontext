# -*- coding: utf-8 -*-
"""把引擎 + 关卡数据打包成「可以直接粘进 Dify 代码节点」的单文件。

    python build_dify_node.py     # 生成 dify_node.py

生成的 dify_node.py 只依赖标准库，入口：

    main(state: str, move: str, level: int) -> dict
"""

import io
import json
import os
import pprint

HERE = os.path.dirname(os.path.abspath(__file__))
MARKER = "# ---------------------------------------------------------------- Dify 代码节点入口"

WRAPPER = '''

# ---------------------------------------------------------------- Dify 节点入口

LEVELS = PUZZLES["puzzles"]


def _start_level(level):
    lv = int(level or 1)
    lv = max(1, min(lv, len(LEVELS)))
    p = LEVELS[lv - 1]
    st = new_game([list(h) for h in p["hands"]], steps=p["steps"],
                  names=p["names"], lead=0, title=p["title"])
    return st, lv


def main(state: str, move: str, level: int) -> dict:
    """Dify 代码节点入口。

    输入：
        state  —— 会话变量里的牌局 JSON（首次为空字符串）
        move   —— 玩家这一句输入
        level  —— 会话变量里的关卡号（首次为 1）
    输出：
        ok / message / state / status / steps_left / level / title
    """
    try:
        cur = json.loads(state) if state else None
    except Exception:
        cur = None
    text = (move or "").strip()
    lv = int(level or 1)

    # 第一回合：开局
    if not cur:
        st, lv = _start_level(lv)
        return {"ok": True, "message": render_table(st),
                "state": json.dumps(st, ensure_ascii=False),
                "status": "playing", "steps_left": st["steps_left"],
                "level": lv, "title": st.get("title", ""),
                "settled": False, "summary": ""}

    # 换关 / 重开
    if text in ("下一关", "next", "重开", "再来一局", "重新开始"):
        nxt = lv + 1 if cur.get("status") == "win" else lv
        st, lv = _start_level(nxt)
        return {"ok": True, "message": render_table(st),
                "state": json.dumps(st, ensure_ascii=False),
                "status": "playing", "steps_left": st["steps_left"],
                "level": lv, "title": st.get("title", ""),
                "settled": False, "summary": ""}

    # 本关已结束
    if cur.get("status") != "playing":
        tip = "通关了！说「下一关」继续。" if cur.get("status") == "win" else "这关没过，说「重开」再来一次。"
        return {"ok": False, "message": tip,
                "state": json.dumps(cur, ensure_ascii=False),
                "status": cur.get("status"), "steps_left": cur.get("steps_left", 0),
                "level": lv, "title": cur.get("title", ""),
                "settled": False, "summary": ""}

    res = play_turn(cur, text)
    msg = res["message"]
    settled = cur.get("status") == "playing" and res["status"] != "playing"
    summary = ""
    if settled:
        used = int(cur.get("steps", 0)) - int(res.get("steps_left", 0))
        summary = "%s：%s（%d 步预算，用了 %d 步）" % (
            cur.get("title", ""), "通关" if res["status"] == "win" else "失败", cur.get("steps", 0), used)
    if res["status"] == "win":
        msg += "\\n\\n通关！说「下一关」继续。"
    elif res["status"] == "lose":
        msg += "\\n\\n说「重开」再打一次。"
    return {"ok": res["ok"], "message": msg,
            "state": json.dumps(res["state"], ensure_ascii=False),
            "status": res["status"], "steps_left": res["steps_left"],
            "level": lv, "title": cur.get("title", ""),
            "settled": settled, "summary": summary}
'''


def main():
    with io.open(os.path.join(HERE, "doudizhu.py"), encoding="utf-8") as f:
        src = f.read()
    head = src.split(MARKER)[0].rstrip()

    with io.open(os.path.join(HERE, "puzzles.json"), encoding="utf-8") as f:
        data = json.load(f)
    # 代码节点里只需要运行期字段；solution/hint/tags 是给文档和测试用的，去掉能省一半体积
    slim = {
        "version": data.get("version", 1),
        "puzzles": [
            {k: p[k] for k in ("id", "title", "seats", "steps", "names", "hands")}
            for p in data["puzzles"]
        ],
    }
    # 用 Python 字面量而不是 JSON：JSON 的 null 在代码里不是合法名字
    puzzles_literal = "PUZZLES = " + pprint.pformat(slim, width=110, sort_dicts=False)

    out = head + "\n\n\n" + puzzles_literal + "\n" + WRAPPER
    path = os.path.join(HERE, "dify_node.py")
    with io.open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(out)
    print("wrote %s (%d bytes, %d lines)" % (path, len(out.encode("utf-8")), out.count("\n")))


if __name__ == "__main__":
    main()
