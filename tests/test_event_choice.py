"""event_choice 效果解析 + 打分测试（P2 事件识别接入）。

运行：
    python tests/test_event_choice.py
"""

import importlib.util
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

_EV = os.path.join(ROOT, "module", "umamusume", "script",
                   "cultivate_task", "event", "event_choice.py")
_spec = importlib.util.spec_from_file_location("_ec", _EV)
ec = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ec)

_PASS = 0
_FAIL = []


def check(name, cond, detail=""):
    global _PASS
    if cond:
        _PASS += 1
    else:
        _FAIL.append(name)
        print("[FAIL] %s %s" % (name, detail))


# ---- 效果解析 ----
check("属性+20", ec.parse_effect("スピード(速度)+20") == [("speed", 20.0, "speed +20")],
      repr(ec.parse_effect("スピード(速度)+20")))

check("属性区间10~20取中值15",
      abs(ec.parse_effect("賢さ(智力)+10~20")[0][1] - 15) < 1e-6,
      repr(ec.parse_effect("賢さ(智力)+10~20")))
check("根性(毅力)+20", ec.parse_effect("根性(毅力)+20")[0][0] == "guts",
      repr(ec.parse_effect("根性(毅力)+20")))
check("技能点", ec.parse_effect("スキルPt(技能点数)+10") == [("skill_pt", 10.0, "技能点 +10")],
      repr(ec.parse_effect("スキルPt(技能点数)+10")))
check("技能提示", ec.parse_effect("『勢い任せ』のヒントLv+1")[0][0] == "hint",
      repr(ec.parse_effect("『勢い任せ』のヒントLv+1")))
check("技能提示Lv+3", ec.parse_effect("『アオハル点火・速』のヒントLv+1~3")[0][1] == 1,
      repr(ec.parse_effect("『アオハル点火・速』のヒントLv+1~3")))
check("干劲提升", ec.parse_effect("やる気(干劲)アップ(提升)")[0] == ("motivation", 1, "干劲 +1 段"),
      repr(ec.parse_effect("やる気(干劲)アップ(提升)")))
check("干劲3段降", ec.parse_effect("やる気(干劲)3段階ダウン(下降)")[0][1] == -3,
      repr(ec.parse_effect("やる気(干劲)3段階ダウン(下降)")))
check("体力扣", ec.parse_effect("体力-20")[0] == ("stamina", -20, "体力 -20"),
      repr(ec.parse_effect("体力-20")))
check("羁绊", ec.parse_effect("カレンチャンの絆ゲージ+5")[0] == ("gauge", 5, "羁绊 +5"),
      repr(ec.parse_effect("カレンチャンの絆ゲージ+5")))
check("随机属性区间", ec.parse_effect("5種ステータス(能力)からランダムに(随机)1種を+5~10")[0][0] == "random_attr",
      repr(ec.parse_effect("5種ステータス(能力)からランダムに(随机)1種を+5~10")))
check("未知效果不炸", len(ec.parse_effect("効果なし")) >= 1)
check("空效果", ec.parse_effect("") == [])


# ---- 打分：构造 ctx 桩 ----
class _Attr:
    speed = 600
    stamina = 400
    power = 500
    guts = 300
    wisdom = 500
    skill_point = 100


class _TurnInfo:
    date = 30
    remain_stamina = 50


class _Detail:
    def __init__(self):
        self.expect_attribute = [1200, 900, 800, 600, 700]  # 速耐大缺口
        self.turn_info = _TurnInfo()
        self.turn_info.uma_attribute = _Attr()
        self.learn_skill_list = [["直線加速"]]


class _Ctx:
    cultivate_detail = _Detail()


def _choice(effects, text="选项"):
    return {"text": text, "effects": effects}


ctx = _Ctx()

# 速度缺口 600 → 权重 3；耐力缺口 500 → 权重 2；技能点 30 回合 → 权重 1
c1 = ec.score_choice(ctx, _choice(["スピード(速度)+20"]), 1)
check("速度+20 高权重分>50", c1.total > 50, "got %.1f" % c1.total)
c2 = ec.score_choice(ctx, _choice(["スタミナ(耐力)+20"]), 2)
check("耐力+20 次高(<速度但>0)", 20 < c2.total < c1.total,
      "stamina=%.1f speed=%.1f" % (c2.total, c1.total))
c3 = ec.score_choice(ctx, _choice(["スキルPt(技能点数)+50"]), 3)
check("技能点50≈50分", 45 <= c3.total <= 55, "got %.1f" % c3.total)
# 技能提示命中想学技能
c4 = ec.score_choice(ctx, _choice(["『直線加速』のヒントLv+1"]), 4)
check("命中想学技能提示高分", c4.total >= 100, "got %.1f" % c4.total)
# 干劲下降负分
c5 = ec.score_choice(ctx, _choice(["やる気(干劲)ダウン(下降)"]), 5)
check("干劲下降负分", c5.total < 0, "got %.1f" % c5.total)

# pick_best_choice：速度20 vs 智力20 → 应选速度（缺口大）
ev = {"name": "测试事件",
      "choices": [_choice(["賢さ(智力)+20"], "智力"),
                  _choice(["スピード(速度)+20"], "速度")]}
check("缺口导向选速度(选项2)", ec.pick_best_choice(ctx, ev) == 2,
      "got %d" % ec.pick_best_choice(ctx, ev))

# 无选项默认1 / 全负默认1
check("无选项→1", ec.pick_best_choice(ctx, {"name": "x", "choices": []}) == 1)
check("全负→1", ec.pick_best_choice(
    ctx, {"name": "x", "choices": [_choice(["やる気(干劲)ダウン(下降)"]),
                                   _choice(["体力-30"])]}) == 1)

print("")
print("event_choice 测试：%d 项断言全过" % _PASS if not _FAIL else
      "event_choice 测试：%d/%d 通过，失败：%s" % (_PASS, _PASS + len(_FAIL), _FAIL))
sys.exit(0 if not _FAIL else 1)
