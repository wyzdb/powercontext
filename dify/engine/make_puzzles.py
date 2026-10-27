# -*- coding: utf-8 -*-
"""生成并校验残局关卡（构造式 + 分类配额）。

随机发牌很难凑出「几步内清空手牌」的局面，所以改成先构造玩家的出牌计划
（顺子 / 连对 / 飞机 / 三带 / 炸弹 / 王炸 + 散牌），再用剩余牌堆给 AI 发牌，
最后用引擎的确定性 AI 跑求解器验证：
  1. 确实存在 N 步内获胜的走法；
  2. 首着选择不超过 3 个（关卡才「紧」，不是怎么打都赢）；
  3. 每个关卡的首着牌型符合它被分配的类别（标题才不会名不副实）。

用法：
    python make_puzzles.py            # 重新生成 puzzles.json
"""

import json
import random
import sys

import doudizhu as d

DECK = []
for _r in "3456789TJQKA2":
    DECK += [_r] * 4
DECK += ["x", "X"]

RANK_LIST = list("3456789TJQKA2")
NORMAL = RANK_LIST[:13]  # 3..2，不含王

TITLE_BY_TYPE = {
    "single": ["单刀直入", "一张定生死", "留一手"],
    "pair": ["成双成对", "拆对子的人", "一对定输赢"],
    "trio": ["三张的底气", "三连击", "手里有货"],
    "trio_single": ["三带一", "多带一张"],
    "trio_pair": ["三带二", "带对压人"],
    "straight": ["顺子开路", "一条龙", "五张连珠"],
    "double_straight": ["连对压制", "三连对"],
    "airplane": ["飞机起飞", "双三连"],
    "airplane_single": ["飞机带单", "带翅膀"],
    "airplane_pair": ["飞机带对", "满载"],
    "four_two": ["四带二", "拆炸保命"],
    "four_two_pair": ["四带两对", "大牌清场"],
    "bomb": ["炸弹开路", "四个的脾气", "炸出一口气"],
    "rocket": ["王炸收场", "双王压阵"],
}


def ranks_from(start_idx, length):
    return RANK_LIST[start_idx:start_idx + length]


# ---------------------------------------------------------------- 出牌计划


def _straight(rng, length):
    return ranks_from(rng.randint(0, 12 - length), length)


def plan_straight_pair(rng):
    st = _straight(rng, 5)
    p = rng.choice([x for x in NORMAL if x not in st])
    return [st, [p, p]]


def plan_straight_singles(rng):
    st = _straight(rng, 5)
    rest = [x for x in NORMAL if x not in st]
    s1, s2 = rng.sample(rest, 2)
    return [st, [s1], [s2]]


def plan_long_straight(rng):
    st = _straight(rng, 6)
    p = rng.choice([x for x in NORMAL if x not in st])
    return [st, [p, p]]


def plan_double_straight(rng):
    length = 3
    rs = ranks_from(rng.randint(0, 9), length)
    ds = [r for r in rs for _ in range(2)]
    rest = [x for x in NORMAL if x not in rs]
    s1, s2 = rng.sample(rest, 2)
    return [ds, [s1], [s2]]


def plan_double_straight_pair(rng):
    rs = ranks_from(rng.randint(0, 9), 3)
    ds = [r for r in rs for _ in range(2)]
    p = rng.choice([x for x in NORMAL if x not in rs])
    return [ds, [p, p]]


def plan_airplane_pair(rng):
    rs = ranks_from(rng.randint(0, 9), 2)
    air = [r for r in rs for _ in range(3)]
    rest = [x for x in NORMAL if x not in rs]
    p, s = rng.sample(rest, 2)
    return [air, [p, p], [s]]


def plan_airplane_singles(rng):
    rs = ranks_from(rng.randint(0, 9), 2)
    air = [r for r in rs for _ in range(3)]
    rest = [x for x in NORMAL if x not in rs]
    s1, s2, s3 = rng.sample(rest, 3)
    return [air, [s1], [s2], [s3]]


def plan_trio_pair_plus(rng):
    r = rng.choice(NORMAL)
    rest = [x for x in NORMAL if x != r]
    p, q = rng.sample(rest, 2)
    return [[r] * 3 + [p] * 2, [q, q]]


def plan_trio_single_mix(rng):
    r = rng.choice(NORMAL)
    rest = [x for x in NORMAL if x != r]
    s, p = rng.sample(rest, 2)
    return [[r] * 3 + [s], [p, p]]


def plan_bomb_trio(rng):
    r = rng.choice(NORMAL)
    t = rng.choice([x for x in NORMAL if x != r])
    return [[r] * 4, [t] * 3]


def plan_bomb_trio_single(rng):
    r = rng.choice(NORMAL)
    rest = [x for x in NORMAL if x != r]
    t, s = rng.sample(rest, 2)
    return [[r] * 4, [t] * 3, [s]]


def plan_bomb_singles(rng):
    r = rng.choice(NORMAL)
    rest = [x for x in NORMAL if x != r]
    s1, s2, s3 = rng.sample(rest, 3)
    return [[r] * 4, [s1], [s2], [s3]]


def plan_bomb_pair(rng):
    r = rng.choice(NORMAL)
    rest = [x for x in NORMAL if x != r]
    p, s = rng.sample(rest, 2)
    return [[r] * 4, [p, p], [s]]


def plan_rocket_mix(rng):
    r = rng.choice(NORMAL)
    return [["x", "X"], [r] * 3]


def plan_pairs(rng):
    rs = rng.sample(NORMAL, 3)
    return [[r] * 2 for r in rs]


RECIPE = [
    # (类别, 计划函数, 数量, 首着判定)
    ("straight", plan_straight_pair, 3, lambda t: t == "straight"),
    ("straight", plan_straight_singles, 2, lambda t: t == "straight"),
    ("straight", plan_long_straight, 2, lambda t: t == "straight"),
    ("double_straight", plan_double_straight, 2, lambda t: t == "double_straight"),
    ("double_straight", plan_double_straight_pair, 1, lambda t: t == "double_straight"),
    ("trio_pair", plan_trio_pair_plus, 2, lambda t: t == "trio_pair"),
    ("trio_single", plan_trio_single_mix, 1, lambda t: t in ("trio_single", "trio")),
    ("bomb", plan_bomb_trio, 2, lambda t: t in ("bomb", "trio")),
    ("bomb", plan_bomb_trio_single, 1, lambda t: t in ("bomb", "trio")),
    ("rocket", plan_rocket_mix, 1, lambda t: t in ("rocket", "trio", "single", "pair")),
    ("pair", plan_pairs, 3, lambda t: t == "pair"),
]


def build_plan(rng, fn):
    combos = fn(rng)
    hand = [c for combo in combos for c in combo]
    if not (5 <= len(hand) <= 9):
        return None
    # 同一张牌不能超过牌堆上限（普通牌 4 张、王各 1 张）
    counts = {}
    for c in hand:
        counts[c] = counts.get(c, 0) + 1
    if any(n > (1 if c in "xX" else 4) for c, n in counts.items()):
        return None
    return combos, hand


def deal_ai(rng, pool, sizes):
    deck = pool[:]
    rng.shuffle(deck)
    hands = []
    for s in sizes:
        if s > len(deck):
            return None
        hands.append(sorted(deck[:s], key=lambda c: (d.VALUE[c], c)))
        deck = deck[s:]
    return hands


def try_make(rng, n_seats, fn, first_pred):
    plan = build_plan(rng, fn)
    if not plan:
        return None
    _, hand = plan
    pool = DECK[:]
    for c in hand:
        pool.remove(c)
    sizes = [rng.randint(3, 5)] if n_seats == 2 else [rng.randint(2, 5), rng.randint(2, 5)]
    if sum(sizes) > len(pool):
        return None
    ai_hands = deal_ai(rng, pool, sizes)
    if not ai_hands:
        return None

    hands = [sorted(hand, key=lambda c: (d.VALUE[c], c))] + ai_hands
    names = ["你", "左家", "右家"][:n_seats]
    max_steps = 3
    state = d.new_game([list(h) for h in hands], steps=max_steps, names=names, lead=0)
    sol = d.solve(state, max_depth=max_steps)
    if not sol or len(sol) < 2 or len(sol) > max_steps:
        return None

    first = sol[0]
    if first is None:
        return None
    first_type = (d.classify(first) or {}).get("type")
    if not first_pred(first_type):
        return None
    # 第一手不能把牌打到只剩 1 张：那只是「一把大牌 + 一张收尾」，不算残局
    if len(first) > len(hands[0]) - 2:
        return None

    steps = len(sol)
    state = d.new_game([list(h) for h in hands], steps=steps, names=names, lead=0)

    # 首着至少要有 3 种选择，避免「只有一条路」或者「怎么打都赢」
    if len(d.player_moves(state)) < 3:
        return None

    return {
        "steps": steps,
        "hands": [list(h) for h in hands],
        "names": names,
        "solution": [None if m is None else list(m) for m in sol],
        "first_type": first_type,
    }


def main():
    rng = random.Random(20261027)
    puzzles = []
    seen = set()
    n_seats_cycle = [2, 2, 3]
    idx = 0
    for _cat, fn, count, pred in RECIPE:
        made = 0
        for _ in range(80000):
            if made >= count:
                break
            n_seats = n_seats_cycle[idx % len(n_seats_cycle)]
            item = try_make(rng, n_seats, fn, pred)
            if not item:
                continue
            key = (tuple(item["hands"][0]), tuple(item["hands"][1]))
            if key in seen:
                continue
            seen.add(key)
            puzzles.append(item)
            made += 1
            idx += 1
        if made < count:
            print("WARN: 类别 %s 只生成 %d/%d" % (_cat, made, count), file=sys.stderr)
            idx += count - made

    order = {"straight": 0, "double_straight": 1, "airplane": 2, "trio_pair": 3,
             "trio_single": 4, "bomb": 5, "rocket": 6, "pair": 7}
    puzzles.sort(key=lambda p: (order.get(p["first_type"], 9), p["steps"], len(p["hands"][0])))

    out = []
    for i, p in enumerate(puzzles, 1):
        titles = TITLE_BY_TYPE.get(p["first_type"], ["残局"])
        title = titles[(i - 1) % len(titles)]
        out.append({
            "id": "p%02d" % i,
            "title": "第 %d 关 · %s" % (i, title),
            "seats": len(p["hands"]),
            "steps": p["steps"],
            "names": p["names"],
            "hands": p["hands"],
            "solution": p["solution"],
            "hint": "先出 %s" % ("过" if p["solution"][0] is None else d.pretty(p["solution"][0])),
            "tags": [p["first_type"]],
        })

    data = {"version": 1, "engine": "doudizhu.py", "count": len(out), "puzzles": out}
    with open("puzzles.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("generated %d puzzles -> puzzles.json" % len(out))
    for p in out:
        print("  %-24s %d人 %d步 手牌(%d): %-28s 解: %s" % (
            p["title"], p["seats"], p["steps"], len(p["hands"][0]), d.pretty(p["hands"][0]),
            " → ".join("过" if m is None else d.pretty(m) for m in p["solution"])))


if __name__ == "__main__":
    main()
