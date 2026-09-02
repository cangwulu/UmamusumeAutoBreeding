"""strategy.choose_option 优选策略入口测试（P3）。

运行：
    python tests/test_event_strategy.py
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

_ST = os.path.join(ROOT, "module", "umamusume", "script",
                   "cultivate_task", "event", "strategy.py")
_spec2 = importlib.util.spec_from_file_location("_st", _ST)
st = importlib.util.module_from_spec(_spec2)
_spec2.loader.exec_module(st)

_PASS = 0
_FAIL = []


def check(name, cond, detail=""):
    global _PASS
    if cond:
        _PASS += 1
    else:
        _FAIL.append(name)
        print("[FAIL] %s %s" % (name, detail))


# ---- ctx 桩 ----
class _Attr:
    speed = 600
    stamina = 400
    power = 500
    guts = 300
    wisdom = 500


class _Turn:
    date = 30
    remain_stamina = 50
    uma_attribute = _Attr()


class _Detail:
    def __init__(self):
        self.expect_attribute = [1200, 900, 800, 600, 700]
        self.turn_info = _Turn()
        self.learn_skill_list = []


class _Ctx:
    cultivate_detail = _Detail()


ctx = _Ctx()


def _c(effects, text="选项"):
    return {"text": text, "effects": effects}


# 1) 正常决策：速度缺口导向 → 返回 2（选项2 速度+20 分高）
ev = {"name": "测试", "choices": [_c(["賢さ(智力)+20"], "智力"),
                                 _c(["スピード(速度)+20"], "速度")]}
r = st.choose_option(ctx, "测试", ev)
check("choose_option 返回最优(2)", r == 2, "got %r" % r)

# 2) 无选项 → 1 或 None（pick_best_choice 无选项默认 1；两者行为等价=点选项1）
r2 = st.choose_option(ctx, "测试", {"name": "x", "choices": []})
check("无选项 → 1 或 None", r2 in (1, None), "got %r" % r2)

# 3) 全部负面 → 1 或 None（无正向收益不硬选）
r3 = st.choose_option(ctx, "测试", {"name": "x",
                                    "choices": [_c(["やる気(干劲)ダウン(下降)"])]})
check("全负面 → 1 或 None", r3 in (1, None), "got %r" % r3)

# 4) 异常输入（choices 结构坏）→ 不抛异常（1 或 None）
r4 = st.choose_option(ctx, "测试", {"name": "x", "choices": [{"text": "坏了"}]})
check("坏结构 → 不抛(1或None)", r4 in (1, None), "got %r" % r4)

print("")
print("strategy 测试：%d 项断言全过" % _PASS if not _FAIL else
      "strategy 测试：%d/%d 通过，失败：%s" % (_PASS, _PASS + len(_FAIL), _FAIL))
sys.exit(0 if not _FAIL else 1)
