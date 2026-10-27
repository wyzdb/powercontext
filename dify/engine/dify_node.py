# -*- coding: utf-8 -*-
"""斗地主残局引擎（纯标准库，无第三方依赖）

设计目标：
1. 可在本地用 Python 直接跑、直接单测；
2. 整个文件可以直接粘进 Dify 的「代码执行」节点（入口 `main` 在文件末尾）；
3. 规则判定、AI 出牌、胜负结算全部确定性——同样的输入永远得到同样的输出，
   这样残局「几步通关」才是可验证、可复现的。

牌面表示：单字符 "3".."9" / "T"(10) / "J" / "Q" / "K" / "A" / "2" / "x"(小王) / "X"(大王)
座位：0 = 玩家（地主），1..n = AI（农民）
"""

from __future__ import annotations

import json
from collections import Counter
from functools import lru_cache
from itertools import combinations

RANKS = "3456789TJQKA2"
VALUE = {r: i + 3 for i, r in enumerate(RANKS)}
VALUE["x"] = 16
VALUE["X"] = 17
DISPLAY = {r: r for r in RANKS}
DISPLAY["T"] = "10"
DISPLAY["x"] = "小王"
DISPLAY["X"] = "大王"

MAX_STRAIGHT_RANK = 14  # 顺子/连对/飞机最高到 A，不含 2 和王


class IllegalMove(Exception):
    """非法出牌。"""


# ---------------------------------------------------------------- 基础工具


def sort_cards(cards):
    return sorted(cards, key=lambda c: (VALUE[c], c))


def pretty(cards):
    if not cards:
        return "（无）"
    return " ".join(DISPLAY[c] for c in sort_cards(cards))


def parse_cards(text, hand):
    """把玩家输入解析成手牌子集；无法解析时抛 IllegalMove。

    容忍空格、逗号、中文逗号；"10" 自动折算成 "T"。
    """
    raw = (text or "").strip()
    if not raw:
        raise IllegalMove("没有输入牌")
    raw = raw.replace("，", ",").replace("、", ",").replace(" ", "").replace(",", "")
    raw = raw.replace("10", "T")
    cards = []
    for ch in raw:
        if ch not in VALUE:
            raise IllegalMove("看不懂这张牌：%s" % ch)
        cards.append(ch)
    # 逐张核对，防止输入比手牌还多
    pool = list(hand)
    for c in cards:
        if c not in pool:
            raise IllegalMove("手里没有这张牌：%s" % DISPLAY[c])
        pool.remove(c)
    return sort_cards(cards)


# ---------------------------------------------------------------- 牌型判定


def _is_run(ranks, length):
    if len(ranks) != length or not ranks:
        return False
    if ranks[-1] > MAX_STRAIGHT_RANK:
        return False
    return ranks == list(range(ranks[0], ranks[0] + length))


def classify(cards):
    """返回 {'type': 牌型, 'n': 张数, 'rank': 比较用主牌值}，非法返回 None。"""
    return _classify_cached(tuple(cards))


@lru_cache(maxsize=8192)
def _classify_cached(cards):
    if not cards:
        return None
    try:
        vals = [VALUE[c] for c in cards]
    except KeyError:
        return None
    n = len(vals)
    cnt = Counter(vals)
    keys = sorted(cnt)

    if n == 2 and set(vals) == {16, 17}:
        return {"type": "rocket", "n": 2, "rank": 17}
    if n == 4 and len(cnt) == 1:
        return {"type": "bomb", "n": 4, "rank": keys[0]}
    if n == 1:
        return {"type": "single", "n": 1, "rank": keys[0]}
    if n == 2 and len(cnt) == 1:
        return {"type": "pair", "n": 2, "rank": keys[0]}
    if n == 3 and len(cnt) == 1:
        return {"type": "trio", "n": 3, "rank": keys[0]}

    if n >= 5 and n <= 12 and all(c == 1 for c in cnt.values()) and _is_run(keys, n):
        return {"type": "straight", "n": n, "rank": keys[-1]}
    if n >= 6 and n % 2 == 0 and all(c == 2 for c in cnt.values()) and _is_run(keys, n // 2):
        return {"type": "double_straight", "n": n, "rank": keys[-1]}
    if n >= 6 and n % 3 == 0 and all(c == 3 for c in cnt.values()) and _is_run(keys, n // 3):
        return {"type": "airplane", "n": n, "rank": keys[-1]}

    if n == 4:
        for r, c in cnt.items():
            if c == 3:
                return {"type": "trio_single", "n": 4, "rank": r}
    if n == 5:
        for r, c in cnt.items():
            if c == 3 and any(rr != r and cc == 2 for rr, cc in cnt.items()):
                return {"type": "trio_pair", "n": 5, "rank": r}

    trio_ranks = [r for r in keys if cnt[r] >= 3]
    for i in range(len(trio_ranks)):
        for j in range(i + 2, len(trio_ranks) + 1):
            run = trio_ranks[i:j]
            if not _is_run(run, len(run)):
                continue
            t = len(run)
            rest = n - 3 * t
            if rest == 0:
                continue
            if rest == t:
                return {"type": "airplane_single", "n": n, "rank": run[-1]}
            if rest == 2 * t:
                rest_cnt = Counter({r: cnt[r] for r in cnt if r not in run})
                if len(rest_cnt) == t and all(c == 2 for c in rest_cnt.values()):
                    return {"type": "airplane_pair", "n": n, "rank": run[-1]}

    if n == 6:
        for r, c in cnt.items():
            if c == 4:
                return {"type": "four_two", "n": 6, "rank": r}
    if n == 8:
        for r, c in cnt.items():
            if c == 4:
                rest_cnt = Counter({rr: cc for rr, cc in cnt.items() if rr != r})
                if len(rest_cnt) == 2 and all(c2 == 2 for c2 in rest_cnt.values()):
                    return {"type": "four_two_pair", "n": 8, "rank": r}
    return None


def combo_name(cl):
    return {
        "single": "单张",
        "pair": "对子",
        "trio": "三张",
        "trio_single": "三带一",
        "trio_pair": "三带二",
        "straight": "顺子",
        "double_straight": "连对",
        "airplane": "飞机",
        "airplane_single": "飞机带单",
        "airplane_pair": "飞机带对",
        "four_two": "四带二",
        "four_two_pair": "四带两对",
        "bomb": "炸弹",
        "rocket": "王炸",
    }.get(cl["type"], cl["type"]) if cl else ""


def beats(a, b):
    """a 能否管上 b。"""
    if a is None or b is None:
        return False
    if a["type"] == "rocket":
        return b["type"] != "rocket"
    if b["type"] == "rocket":
        return False
    if a["type"] == "bomb" and b["type"] != "bomb":
        return True
    if b["type"] == "bomb" and a["type"] != "bomb":
        return False
    if a["type"] != b["type"] or a["n"] != b["n"]:
        return False
    return a["rank"] > b["rank"]


# ---------------------------------------------------------------- 走子生成


def gen_moves(hand):
    """枚举手牌所有合法牌型（去重，已按牌面排序）。"""
    return [list(m) for m in _gen_moves_cached(tuple(sort_cards(hand)))]


@lru_cache(maxsize=4096)
def _gen_moves_cached(hand):
    found = set()
    cnt = Counter(VALUE[c] for c in hand)
    by_val = {}
    for c in sort_cards(hand):
        by_val.setdefault(VALUE[c], []).append(c)
    vals = sorted(cnt)

    def add(cards):
        cl = classify(cards)
        if cl:
            found.add(tuple(sort_cards(cards)))

    for v in vals:
        k = cnt[v]
        add(by_val[v][:1])
        if k >= 2:
            add(by_val[v][:2])
        if k >= 3:
            add(by_val[v][:3])
        if k == 4:
            add(by_val[v])
    if 16 in cnt and 17 in cnt:
        add([by_val[16][0], by_val[17][0]])

    for v in vals:
        if cnt[v] < 3:
            continue
        trio = by_val[v][:3]
        for w in vals:
            if w == v:
                continue
            add(trio + [by_val[w][0]])
            if cnt[w] >= 2:
                add(trio + by_val[w][:2])

    for length in range(5, 13):
        for start in range(3, MAX_STRAIGHT_RANK - length + 2):
            ranks = list(range(start, start + length))
            if all(cnt.get(r, 0) >= 1 for r in ranks):
                add([by_val[r][0] for r in ranks])

    for length in range(3, 11):
        for start in range(3, MAX_STRAIGHT_RANK - length + 2):
            ranks = list(range(start, start + length))
            if all(cnt.get(r, 0) >= 2 for r in ranks):
                add([c for r in ranks for c in by_val[r][:2]])

    for length in range(2, 7):
        for start in range(3, MAX_STRAIGHT_RANK - length + 2):
            ranks = list(range(start, start + length))
            if not all(cnt.get(r, 0) >= 3 for r in ranks):
                continue
            base = [c for r in ranks for c in by_val[r][:3]]
            add(base)
            rest = [c for c in hand if VALUE[c] not in ranks]
            if len(rest) >= length:
                for comb in combinations(rest, length):
                    add(base + list(comb))
            pair_ranks = sorted({VALUE[c] for c in rest if sum(1 for x in rest if VALUE[x] == VALUE[c]) >= 2})
            if len(pair_ranks) >= length:
                for comb in combinations(pair_ranks, length):
                    add(base + [c for r in comb for c in by_val[r][:2]])

    for v in vals:
        if cnt[v] != 4:
            continue
        quad = list(by_val[v])
        rest = [c for c in hand if VALUE[c] != v]
        if len(rest) >= 2:
            for comb in combinations(rest, 2):
                add(quad + list(comb))
        pair_ranks = sorted({VALUE[c] for c in rest if sum(1 for x in rest if VALUE[x] == VALUE[c]) >= 2})
        if len(pair_ranks) >= 2:
            for comb in combinations(pair_ranks, 2):
                add(quad + [c for r in comb for c in by_val[r][:2]])

    return tuple(sorted(found, key=lambda t: (len(t), tuple(VALUE[c] for c in t))))


# ---------------------------------------------------------------- 对局状态


def new_game(hands, steps=3, names=None, lead=0, title=""):
    names = names or ["你", "左家", "右家"]
    seats = [{"name": names[i] if i < len(names) else "玩家%d" % i, "hand": sort_cards(h)}
             for i, h in enumerate(hands)]
    return {
        "title": title,
        "seats": seats,
        "turn": lead,
        "last": None,
        "passes": 0,
        "steps": steps,
        "steps_left": steps,
        "status": "playing",
        "reason": "",
        "history": [],
    }


def _copy(state):
    return {
        "title": state.get("title", ""),
        "seats": [{"name": s["name"], "hand": list(s["hand"])} for s in state["seats"]],
        "turn": state["turn"],
        "last": None if not state["last"] else {"seat": state["last"]["seat"], "cards": list(state["last"]["cards"])},
        "passes": state["passes"],
        "steps": state["steps"],
        "steps_left": state["steps_left"],
        "status": state["status"],
        "reason": state.get("reason", ""),
        "history": [dict(h) for h in state.get("history", [])],
    }


def last_combo(state):
    if not state["last"]:
        return None
    return classify(state["last"]["cards"])


def _tick(state, seat):
    if seat != 0:
        return state
    state["steps_left"] = max(0, state["steps_left"] - 1)
    if state["status"] == "playing" and state["steps_left"] <= 0:
        state["status"] = "lose"
        state["reason"] = "步数用尽，牌没出完"
    return state


def apply_move(state, seat, cards):
    """执行一步；cards=None 表示过。返回新状态，非法时抛 IllegalMove。"""
    if state["status"] != "playing":
        raise IllegalMove("牌局已经结束")
    if seat != state["turn"]:
        raise IllegalMove("还没轮到你")
    s = _copy(state)
    hand = s["seats"][seat]["hand"]

    if cards is None:
        if s["last"] is None or s["last"]["seat"] == seat:
            raise IllegalMove("你是先手，必须出牌")
        s["history"].append({"seat": seat, "cards": None})
        s["passes"] += 1
        if s["passes"] >= len(s["seats"]) - 1:
            s["turn"] = s["last"]["seat"]
            s["last"] = None
            s["passes"] = 0
        else:
            s["turn"] = (seat + 1) % len(s["seats"])
        return _tick(s, seat)

    cards = sort_cards(cards)
    cl = classify(cards)
    if cl is None:
        raise IllegalMove("这不是合法牌型")
    pool = list(hand)
    for c in cards:
        if c not in pool:
            raise IllegalMove("手里没有这张牌：%s" % DISPLAY[c])
        pool.remove(c)
    if s["last"] is not None and s["last"]["seat"] != seat:
        if not beats(cl, last_combo(s)):
            raise IllegalMove("管不上上家的%s" % combo_name(last_combo(s)))

    s["seats"][seat]["hand"] = pool
    s["last"] = {"seat": seat, "cards": cards}
    s["passes"] = 0
    s["history"].append({"seat": seat, "cards": cards})
    if not pool:
        s["status"] = "win" if seat == 0 else "lose"
        s["reason"] = "你出完了" if seat == 0 else "%s出完了" % s["seats"][seat]["name"]
        return _tick(s, seat)
    s["turn"] = (seat + 1) % len(s["seats"])
    return _tick(s, seat)


# ---------------------------------------------------------------- AI


def _move_key(move):
    cl = classify(move)
    bombish = 1 if cl and cl["type"] in ("bomb", "rocket") else 0
    return (bombish, cl["rank"] if cl else 0, -len(move), tuple(move))


def ai_pick(state, seat):
    """返回 AI 要出的牌（list）或 None（过）。策略确定、无随机。"""
    hand = state["seats"][seat]["hand"]
    last = last_combo(state)
    last_seat = state["last"]["seat"] if state["last"] else None
    moves = gen_moves(hand)

    # 队友出的牌不压（除非能一把走完）
    if last is not None and last_seat != 0:
        finishers = [m for m in moves if len(m) == len(hand) and beats(classify(m), last)]
        return finishers[0] if finishers else None

    legal = [m for m in moves if last is None or beats(classify(m), last)]
    if not legal:
        return None

    player_left = len(state["seats"][0]["hand"])
    if last is not None and player_left <= 2:
        # 对手快走完了：优先用最小的非炸弹管上，但尽量压大
        return min(legal, key=lambda m: (_move_key(m)[0], -_move_key(m)[1], len(m), tuple(m)))
    return min(legal, key=_move_key)


def run_ai(state, guard=16):
    s = state
    steps = 0
    while s["status"] == "playing" and s["turn"] != 0:
        seat = s["turn"]
        s = apply_move(s, seat, ai_pick(s, seat))
        steps += 1
        if steps > guard:
            break
    return s


def player_moves(state):
    """玩家在当前局面下的合法走子；无牌可出时返回 [None]（过）。"""
    hand = state["seats"][0]["hand"]
    last = last_combo(state)
    moves = [m for m in gen_moves(hand) if last is None or beats(classify(m), last)]
    return moves or [None]


# ---------------------------------------------------------------- 求解器


def solve(state, max_depth=6, max_nodes=200000):
    """在 AI 确定性策略下，求玩家在 max_depth 步内走完的着法序列；无解返回 None。"""
    memo = {}
    budget = {"nodes": 0}

    def key(s):
        return (
            tuple(tuple(x["hand"]) for x in s["seats"]),
            s["turn"],
            None if not s["last"] else (s["last"]["seat"], tuple(s["last"]["cards"])),
            s["steps_left"],
            s["status"],
        )

    def dfs(s):
        if s["status"] == "win":
            return []
        if s["status"] != "playing" or s["steps_left"] <= 0:
            return None
        k = key(s)
        if k in memo:
            return memo[k]
        budget["nodes"] += 1
        if budget["nodes"] > max_nodes:
            return None

        hand = s["seats"][0]["hand"]
        last = last_combo(s)
        legal = [m for m in gen_moves(hand) if last is None or beats(classify(m), last)]
        # 能一手走完就直接走完 —— 玩家出完即胜，AI 再没有出牌机会
        for m in legal:
            if len(m) == len(hand):
                memo[k] = [m]
                return memo[k]
        if s["steps_left"] <= 1:
            memo[k] = None
            return None

        memo[k] = None
        # 大牌型优先：先试探「一把清掉更多牌」的走法，能显著减少搜索
        must_pass = not legal
        legal = [m for m in legal if m]
        legal.sort(key=lambda m: (-len(m), -classify(m)["rank"]))
        if must_pass:
            legal = [None]
        for m in legal:
            try:
                ns = run_ai(apply_move(s, 0, m))
            except IllegalMove:
                continue
            if ns["status"] == "win":
                memo[k] = [m]
                return [m]
            if ns["status"] != "playing":
                continue
            tail = dfs(ns)
            if tail is not None:
                memo[k] = [m] + tail
                return memo[k]
        return None

    return dfs(state)


# ---------------------------------------------------------------- 渲染


def render_table(state):
    s = state
    lines = []
    if s.get("title"):
        lines.append("【%s】" % s["title"])
    lines.append("你的手牌（%d 张）：%s" % (len(s["seats"][0]["hand"]), pretty(s["seats"][0]["hand"])))
    for i in range(1, len(s["seats"])):
        seat = s["seats"][i]
        lines.append("%s：剩 %d 张" % (seat["name"], len(seat["hand"])))
    if s["last"]:
        who = s["seats"][s["last"]["seat"]]["name"]
        lines.append("上家出牌：%s 出了 %s（%s）" % (who, pretty(s["last"]["cards"]), combo_name(classify(s["last"]["cards"]))))
    else:
        lines.append("轮到你自由出牌")
    lines.append("剩余步数：%d" % s["steps_left"])
    return "\n".join(lines)


def render_result(state):
    if state["status"] == "win":
        return "你赢了！%s" % state["reason"]
    if state["status"] == "lose":
        return "你输了：%s" % state["reason"]
    return ""


# ---------------------------------------------------------------- 回合入口


PASS_WORDS = {"过", "不要", "要不起", "pass", "PASS", "Pass", "不出", "管不上"}


def play_turn(state, text):
    """处理玩家一句话，返回 {ok, message, state, status, steps_left}。

    state 为 dict（也接受 JSON 字符串），返回值里的 state 是 dict。
    """
    s = json.loads(state) if isinstance(state, str) else _copy(state)
    text = (text or "").strip()

    if s["status"] != "playing":
        return {"ok": False, "message": "本局已结束。发「重开」再打一局。", "state": s,
                "status": s["status"], "steps_left": s["steps_left"]}

    # 指令
    if text in ("重开", "再来一局", "restart"):
        return {"ok": False, "message": "残局是固定的，换一关请对我说「下一关」。", "state": s,
                "status": s["status"], "steps_left": s["steps_left"]}
    if text in ("提示", "hint", "帮我"):
        line = solve(s, max_depth=max(1, s["steps_left"]))
        if not line:
            return {"ok": True, "message": "这一步已经无解了，试试「重开本关」。", "state": s,
                    "status": s["status"], "steps_left": s["steps_left"]}
        first = line[0]
        tip = "过" if first is None else pretty(first)
        return {"ok": True, "message": "提示：先出 %s（这局共 %d 步可解）" % (tip, len(line)), "state": s,
                "status": s["status"], "steps_left": s["steps_left"]}
    if text in ("认输", "投降", "give up"):
        s = _copy(s)
        s["status"] = "lose"
        s["reason"] = "你认输了"
        return {"ok": True, "message": render_result(s), "state": s,
                "status": s["status"], "steps_left": s["steps_left"]}

    # 出牌 / 过
    try:
        if text in PASS_WORDS:
            ns = apply_move(s, 0, None)
        else:
            cards = parse_cards(text, s["seats"][0]["hand"])
            ns = apply_move(s, 0, cards)
    except IllegalMove as e:
        return {"ok": False, "message": "出不了：%s" % e, "state": s,
                "status": s["status"], "steps_left": s["steps_left"]}

    ns = run_ai(ns)
    msg = render_result(ns) if ns["status"] != "playing" else render_table(ns)
    return {"ok": True, "message": msg, "state": ns, "status": ns["status"], "steps_left": ns["steps_left"]}


PUZZLES = {'version': 1,
 'puzzles': [{'id': 'p01',
              'title': '第 1 关 · 顺子开路',
              'seats': 2,
              'steps': 2,
              'names': ['你', '左家'],
              'hands': [['3', '3', '5', '6', '7', '8', '9'], ['6', '9', 'K']]},
             {'id': 'p02',
              'title': '第 2 关 · 一条龙',
              'seats': 2,
              'steps': 2,
              'names': ['你', '左家'],
              'hands': [['5', '5', '7', '8', '9', 'T', 'J'], ['4', '8', 'K', 'K', '2']]},
             {'id': 'p03',
              'title': '第 3 关 · 五张连珠',
              'seats': 3,
              'steps': 2,
              'names': ['你', '左家', '右家'],
              'hands': [['5', '6', '7', '8', '9', 'K', 'K'], ['6', '8', 'J', 'A', '2'], ['4', '8', 'Q']]},
             {'id': 'p04',
              'title': '第 4 关 · 顺子开路',
              'seats': 3,
              'steps': 2,
              'names': ['你', '左家', '右家'],
              'hands': [['4', '5', '6', '7', '8', '9', 'K', 'K'], ['T', 'J', 'Q', 'A'], ['3', '4', 'Q']]},
             {'id': 'p05',
              'title': '第 5 关 · 一条龙',
              'seats': 2,
              'steps': 2,
              'names': ['你', '左家'],
              'hands': [['3', '3', '9', 'T', 'J', 'Q', 'K', 'A'], ['3', 'T', 'J', 'Q', 'K']]},
             {'id': 'p06',
              'title': '第 6 关 · 五张连珠',
              'seats': 2,
              'steps': 3,
              'names': ['你', '左家'],
              'hands': [['7', '9', 'T', 'J', 'Q', 'K', '2'], ['4', '8', 'J']]},
             {'id': 'p07',
              'title': '第 7 关 · 顺子开路',
              'seats': 2,
              'steps': 3,
              'names': ['你', '左家'],
              'hands': [['4', '6', '7', '8', '9', 'T', 'A'], ['6', '9', 'Q']]},
             {'id': 'p08',
              'title': '第 8 关 · 三连对',
              'seats': 2,
              'steps': 2,
              'names': ['你', '左家'],
              'hands': [['4', '4', 'J', 'J', 'Q', 'Q', 'K', 'K'], ['8', '8', 'A', '2']]},
             {'id': 'p09',
              'title': '第 9 关 · 连对压制',
              'seats': 2,
              'steps': 3,
              'names': ['你', '左家'],
              'hands': [['T', 'T', 'J', 'J', 'Q', 'Q', 'K', '2'], ['6', '8', '9', 'K', 'K']]},
             {'id': 'p10',
              'title': '第 10 关 · 三连对',
              'seats': 3,
              'steps': 3,
              'names': ['你', '左家', '右家'],
              'hands': [['4', '7', '7', '8', '8', '9', '9', 'T'], ['6', '9'], ['6', 'T', 'Q']]},
             {'id': 'p11',
              'title': '第 11 关 · 三带二',
              'seats': 2,
              'steps': 2,
              'names': ['你', '左家'],
              'hands': [['3', '3', '8', '8', '8', 'J', 'J'], ['J', 'K', 'X']]},
             {'id': 'p12',
              'title': '第 12 关 · 带对压人',
              'seats': 3,
              'steps': 2,
              'names': ['你', '左家', '右家'],
              'hands': [['4', '4', 'T', 'T', 'Q', 'Q', 'Q'], ['K', 'X'], ['4', '2']]},
             {'id': 'p13',
              'title': '第 13 关 · 三带一',
              'seats': 2,
              'steps': 3,
              'names': ['你', '左家'],
              'hands': [['T', 'K', 'K', 'K', '2', '2'], ['7', '7', '9', 'x', 'X']]},
             {'id': 'p14',
              'title': '第 14 关 · 四个的脾气',
              'seats': 2,
              'steps': 2,
              'names': ['你', '左家'],
              'hands': [['4', '4', '4', '6', '2', '2', '2', '2'], ['T', 'J', 'J', 'J', 'J']]},
             {'id': 'p15',
              'title': '第 15 关 · 一对定输赢',
              'seats': 3,
              'steps': 3,
              'names': ['你', '左家', '右家'],
              'hands': [['4', '4', '9', '9', '2', '2'], ['5', 'J', 'J', 'K'], ['5', '6', '6', '7', 'X']]},
             {'id': 'p16',
              'title': '第 16 关 · 成双成对',
              'seats': 2,
              'steps': 3,
              'names': ['你', '左家'],
              'hands': [['5', '5', 'J', 'J', '2', '2'], ['4', '8', 'K']]},
             {'id': 'p17',
              'title': '第 17 关 · 拆对子的人',
              'seats': 2,
              'steps': 3,
              'names': ['你', '左家'],
              'hands': [['5', '5', '9', '9', '2', '2'], ['4', 'J', 'A']]},
             {'id': 'p18',
              'title': '第 18 关 · 手里有货',
              'seats': 2,
              'steps': 2,
              'names': ['你', '左家'],
              'hands': [['6', '6', '6', 'x', 'X'], ['9', 'Q', 'Q', 'Q', '2']]},
             {'id': 'p19',
              'title': '第 19 关 · 三张的底气',
              'seats': 2,
              'steps': 3,
              'names': ['你', '左家'],
              'hands': [['3', '3', '3', '9', '9', '9', '9'], ['5', '7', 'x', 'X']]},
             {'id': 'p20',
              'title': '第 20 关 · 三连击',
              'seats': 3,
              'steps': 3,
              'names': ['你', '左家', '右家'],
              'hands': [['5', '5', '5', 'T', 'T', 'T', 'T'], ['5', 'K', 'A'], ['J', '2', 'x', 'X']]}]}


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
        msg += "\n\n通关！说「下一关」继续。"
    elif res["status"] == "lose":
        msg += "\n\n说「重开」再打一次。"
    return {"ok": res["ok"], "message": msg,
            "state": json.dumps(res["state"], ensure_ascii=False),
            "status": res["status"], "steps_left": res["steps_left"],
            "level": lv, "title": cur.get("title", ""),
            "settled": settled, "summary": summary}
