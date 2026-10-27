# -*- coding: utf-8 -*-
"""引擎单测：python -m unittest -v"""

import json
import os
import unittest

import doudizhu as d


class TestClassify(unittest.TestCase):
    def test_basic_types(self):
        cases = {
            "3": "single",
            "33": "pair",
            "333": "trio",
            "3334": "trio_single",
            "33344": "trio_pair",
            "34567": "straight",
            "334455": "double_straight",
            "333444": "airplane",
            "33344455": "airplane_single",
            "3334445566": "airplane_pair",
            "3333": "bomb",
            "333344": "four_two",
            "33334455": "four_two_pair",
            "xX": "rocket",
        }
        for text, expected in cases.items():
            self.assertEqual(d.classify(list(text))["type"], expected, text)

    def test_rank_order(self):
        self.assertLess(d.classify(list("3"))["rank"], d.classify(list("2"))["rank"])
        self.assertLess(d.classify(list("A"))["rank"], d.classify(list("2"))["rank"])
        self.assertLess(d.classify(list("x"))["rank"], d.classify(list("X"))["rank"])

    def test_illegal(self):
        for text in ["34", "2345", "23456", "JQKA2", "3334445556", "33344455566"]:
            self.assertIsNone(d.classify(list(text)), text)

    def test_straight_limits(self):
        # 顺子至少 5 张，且不含 2 和王
        self.assertIsNone(d.classify(list("3456")))
        self.assertIsNone(d.classify(list("JQKA2")))
        self.assertIsNone(d.classify(list("TJQKx")))
        self.assertIsNotNone(d.classify(list("TJQKA")))


class TestBeats(unittest.TestCase):
    def c(self, text):
        return d.classify(list(text))

    def test_same_type(self):
        self.assertTrue(d.beats(self.c("44"), self.c("33")))
        self.assertFalse(d.beats(self.c("33"), self.c("44")))
        # 牌型不同不能比
        self.assertFalse(d.beats(self.c("34567"), self.c("33")))

    def test_length(self):
        self.assertFalse(d.beats(self.c("345678"), self.c("34567")))

    def test_bomb_and_rocket(self):
        self.assertTrue(d.beats(self.c("3333"), self.c("222")))
        self.assertTrue(d.beats(self.c("3333"), self.c("34567")))
        self.assertTrue(d.beats(self.c("4444"), self.c("3333")))
        self.assertFalse(d.beats(self.c("3333"), self.c("4444")))
        self.assertTrue(d.beats(self.c("xX"), self.c("2222")))
        self.assertFalse(d.beats(self.c("2222"), self.c("xX")))

    def test_joker_single(self):
        self.assertTrue(d.beats(self.c("x"), self.c("2")))
        self.assertTrue(d.beats(self.c("X"), self.c("x")))


class TestParse(unittest.TestCase):
    def test_parse(self):
        hand = list("334455")
        self.assertEqual(d.parse_cards("3 4 5", hand), d.sort_cards(list("345")))
        self.assertEqual(d.parse_cards("10", list("T")), ["T"])
        with self.assertRaises(d.IllegalMove):
            d.parse_cards("３４", list("34"))  # 全角数字不是合法牌面

    def test_parse_errors(self):
        hand = list("33")
        with self.assertRaises(d.IllegalMove):
            d.parse_cards("333", hand)  # 手里只有两张 3
        with self.assertRaises(d.IllegalMove):
            d.parse_cards("4", hand)
        with self.assertRaises(d.IllegalMove):
            d.parse_cards("", hand)


class TestFlow(unittest.TestCase):
    def make(self):
        return d.new_game([list("34567"), list("45678")], steps=3, names=["你", "左家"])

    def test_win_in_one(self):
        st = self.make()
        r = d.play_turn(st, "34567")
        self.assertEqual(r["status"], "win")

    def test_cannot_beat(self):
        st = d.new_game([list("3"), list("4")], steps=2, names=["你", "左家"])
        r = d.play_turn(st, "3")
        # 玩家出 3 后手牌清空，直接获胜，AI 没机会出 4
        self.assertEqual(r["status"], "win")

    def test_illegal_move_keeps_state(self):
        st = d.new_game([list("34"), list("5")], steps=2, names=["你", "左家"])
        r = d.play_turn(st, "4 4")
        self.assertFalse(r["ok"])
        self.assertEqual(r["state"]["seats"][0]["hand"], d.sort_cards(list("34")))

    def test_pass_when_leading_is_illegal(self):
        st = d.new_game([list("34"), list("5")], steps=2, names=["你", "左家"])
        r = d.play_turn(st, "过")
        self.assertFalse(r["ok"])

    def test_steps_exhausted(self):
        st = d.new_game([list("34"), list("56")], steps=2, names=["你", "左家"])
        r1 = d.play_turn(st, "3")   # AI 出 5，玩家管不上
        r2 = d.play_turn(r1["state"], "4")  # 管不上 5
        self.assertFalse(r2["ok"])

    def test_ai_is_deterministic(self):
        st = d.new_game([list("3345"), list("45678")], steps=3, names=["你", "左家"])
        a = d.run_ai(d.apply_move(st, 0, list("33")))
        b = d.run_ai(d.apply_move(st, 0, list("33")))
        self.assertEqual(a["seats"][1]["hand"], b["seats"][1]["hand"])
        self.assertEqual(a["turn"], 0)


class TestPuzzles(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = os.path.join(os.path.dirname(__file__), "puzzles.json")
        with open(path, encoding="utf-8") as f:
            cls.data = json.load(f)

    def test_count_and_deck(self):
        self.assertEqual(self.data["count"], len(self.data["puzzles"]))
        self.assertGreaterEqual(len(self.data["puzzles"]), 20)
        for p in self.data["puzzles"]:
            all_cards = [c for hand in p["hands"] for c in hand]
            counts = {}
            for c in all_cards:
                counts[c] = counts.get(c, 0) + 1
            for c, n in counts.items():
                limit = 1 if c in "xX" else 4
                self.assertLessEqual(n, limit, "%s 超过牌堆上限" % p["id"])

    def test_solution_replays_to_win(self):
        for p in self.data["puzzles"]:
            st = d.new_game([list(h) for h in p["hands"]], steps=p["steps"],
                            names=p["names"], lead=0, title=p["title"])
            for i, move in enumerate(p["solution"]):
                if st["status"] != "playing":
                    self.fail("%s 在解法的第 %d 步前已经结束" % (p["id"], i))
                st = d.run_ai(d.apply_move(st, 0, move))
            self.assertEqual(st["status"], "win", "%s 解法没能获胜" % p["id"])
            self.assertLessEqual(len(p["solution"]), p["steps"])

    def test_hint_matches_solution(self):
        for p in self.data["puzzles"]:
            first = p["solution"][0]
            tip = "过" if first is None else d.pretty(first)
            self.assertIn(tip, p["hint"], p["id"])

    def test_solver_agrees(self):
        for p in self.data["puzzles"][:10]:
            st = d.new_game([list(h) for h in p["hands"]], steps=p["steps"],
                            names=p["names"], lead=0)
            self.assertIsNotNone(d.solve(st, max_depth=p["steps"]), p["id"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
