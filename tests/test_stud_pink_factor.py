"""
红因子继承概率模型（P2）—— 与 uma-tools SuccessionPlanner 的移植对齐

验证 stud_planner.py 里抄入的概率模型与参考实现数值一致：
  red_factor_prob       单颗红因子单次继承判定概率 = base×(1+相性/100)
  red_factor_reach_prob 2 次继承机会内至少成功一次 = 1-(1-p)^2
  pink_prob_plan        把「概率性阶段」折算成红因子计划
  pink_need             带 compat 的粉因子需求

运行：
    python tests/test_stud_pink_factor.py
"""

import importlib.util
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

_ASSET = os.path.join(ROOT, "module", "umamusume", "asset")

# asset/__init__.py 会 import cv2 → 用 importlib 按文件路径加载单文件绕开
_spec = importlib.util.spec_from_file_location(
    "_sp_stud", os.path.join(_ASSET, "stud_planner.py"))
sp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sp)

_PASS = 0
_FAIL = []


def check(name, cond, detail=""):
    global _PASS
    if cond:
        _PASS += 1
    else:
        _FAIL.append("%s %s" % (name, detail))
        print("[FAIL] %s %s" % (name, detail))


# --- red_factor_prob：基础概率 + 相性加成 + 封顶 ---
check("1★/0相性=1%", abs(sp.red_factor_prob(1, 0) - 0.01) < 1e-9)
check("2★/0相性=3%", abs(sp.red_factor_prob(2, 0) - 0.03) < 1e-9)
check("3★/0相性=5%", abs(sp.red_factor_prob(3, 0) - 0.05) < 1e-9)
check("1★/100相性=2%（×2）", abs(sp.red_factor_prob(1, 100) - 0.02) < 1e-9)
check("1★/60相性=1.6%（uma-tools 对齐）",
      abs(sp.red_factor_prob(1, 60) - 0.016) < 1e-9)
check("超高相性封顶 1.0", abs(sp.red_factor_prob(3, 99999) - 1.0) < 1e-9)

# --- red_factor_reach_prob：2 次机会聚合 ---
check("p=1%/2次=1.99%", abs(sp.red_factor_reach_prob(0.01, 2) - 0.0199) < 1e-9)
check("p=2%/2次=3.96%", abs(sp.red_factor_reach_prob(0.02, 2) - 0.0396) < 1e-9)
check("0 次机会=0", sp.red_factor_reach_prob(0.01, 0) == 0.0)

# --- pink_prob_plan：概率阶段折算 ---
pp0 = sp.pink_prob_plan(0, 50)
check("无概率阶段→stage_up=0 且 prob=None",
      pp0["stage_up"] == 0 and pp0["prob_reach"] is None)
pp1 = sp.pink_prob_plan(1, 0)
check("1 概率阶段→需 1 颗", pp1["stage_up"] == 1)
check("1 概率阶段/0相性→继承率≈1.99%",
      abs(pp1["prob_reach"] - 0.0199) < 1e-3, repr(pp1["prob_reach"]))
pp2 = sp.pink_prob_plan(1, 151)
check("双圈(151)比三角(0)继承率高",
      pp2["prob_reach"] > pp1["prob_reach"])
pp3 = sp.pink_prob_plan(3, 0)
check("3 概率阶段→需 7 颗", pp3["stage_up"] == 7)

# --- pink_need：带 compat 的适性改造需求 ---
pn = sp.pink_need("C", "S", compat=100)
check("C→S：总 3 阶段 / 初始 2 / 概率 1", pn["stages"] == 3
      and pn["initial_stages"] == 2 and pn["prob_stages"] == 1)
check("C→S：概率段折算 1 颗", pn["prob"]["stage_up"] == 1)
check("C→S：prob 非空", pn["prob"] is not None)
check("S→S：prob=None", sp.pink_need("S", "S").get("prob") is None)
pnA = sp.pink_need("A", "S", compat=30)
check("A→S：初始 0 / 概率 1（封顶 A）", pnA["initial_stages"] == 0
      and pnA["prob_stages"] == 1)

print("")
print("红因子概率模型：%d 项断言全过" % _PASS if not _FAIL else
      "红因子概率模型：%d/%d 通过，失败项：%s" % (_PASS, _PASS + len(_FAIL), _FAIL))
sys.exit(0 if not _FAIL else 1)
