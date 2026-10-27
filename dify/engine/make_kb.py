# -*- coding: utf-8 -*-
"""从 puzzles.json 生成知识库文档：data/kb/01-残局讲解.md

只写「思路」，不写具体解牌顺序的牌面，避免检索结果把标准解直接漏给 LLM。

    python make_kb.py
"""

import json
import os

import doudizhu as d

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "data", "kb", "01-残局讲解.md")

MISTAKE = {
    "straight": "先把小单张打掉，会丢先手，顺子还没出手步数就用完了。",
    "double_straight": "拆开连对去跟单张，是最常见的输法。",
    "airplane": "飞机拆成三张一张张出，等于把最大的牌型浪费掉。",
    "trio_pair": "先出对子会被压，三带二反而出不去了。",
    "trio_single": "把三张拆开当单张用，等于自废武功。",
    "bomb": "炸弹留到最后，往往已经没有出牌机会了。",
    "rocket": "王炸拆开单出，就再也压不住对手了。",
    "pair": "先出小对子会被压，大对子要留到关键的一手。",
    "single": "一味出最小的单张，等于把先手让给对手。",
}


def combo_summary(cards):
    cl = d.classify(cards)
    if not cl:
        return "一张牌"
    return "%d 张%s" % (cl["n"], d.combo_name(cl))


def main():
    with open(os.path.join(HERE, "puzzles.json"), encoding="utf-8") as f:
        data = json.load(f)

    lines = [
        "# 斗地主残局讲解库",
        "",
        "每一关都是「在限定步数内出完手牌」。下面的思路只讲方向，不讲具体出牌顺序。",
        "玩家问「这关怎么打」时，可以用这里的思路提示他，但不要直接把答案念出来。",
        "",
    ]

    for p in data["puzzles"]:
        hand = p["hands"][0]
        others = p["hands"][1:]
        seats = len(p["hands"])
        first_type = (d.classify(p["solution"][0]) or {}).get("type", "single")
        steps_text = " → ".join(combo_summary(m) for m in p["solution"] if m)

        lines += [
            "## %s" % p["title"],
            "",
            "- 人数：%d 人残局（你 vs %s）" % (seats, "、".join(p["names"][1:])),
            "- 步数预算：%d 步" % p["steps"],
            "- 你的手牌：%s（%d 张）" % (d.pretty(hand), len(hand)),
            "- 对手剩牌：%s" % "、".join("%s %d 张" % (n, len(h)) for n, h in zip(p["names"][1:], others)),
            "- 思路：一共 %d 步，%s。" % (len(p["solution"]), steps_text),
            "- 常见错法：%s" % MISTAKE.get(first_type, "先出小牌丢先手。"),
            "",
        ]

    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines))
    print("wrote %s (%d 关)" % (os.path.abspath(OUT), len(data["puzzles"])))


if __name__ == "__main__":
    main()
