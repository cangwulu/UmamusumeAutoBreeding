"""event_db 真实库端到端测试：加载事件库、匹配国服事件名、上下文打分。

运行：
    python tests/test_event_choice_db.py
（需要 resource/umamusume/data/event_db.json 存在）
"""

import importlib.util
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

_DATA = os.path.join(ROOT, "resource", "umamusume", "data", "event_db.json")
if not os.path.isfile(_DATA):
    print("SKIP: 缺少 event_db.json（先运行 tools/build_event_db.py）")
    sys.exit(0)

_ASSET = os.path.join(ROOT, "module", "umamusume", "asset", "event_db.py")
_spec = importlib.util.spec_from_file_location("_evdb", _ASSET)
evdb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(evdb)

_EV = os.path.join(ROOT, "module", "umamusume", "script",
                   "cultivate_task", "event", "event_choice.py")
_spec2 = importlib.util.spec_from_file_location("_ec", _EV)
ec = importlib.util.module_from_spec(_spec2)
_spec2.loader.exec_module(ec)

_PASS = 0
_FAIL = []


def check(name, cond, detail=""):
    global _PASS
    if cond:
        _PASS += 1
    else:
        _FAIL.append(name)
        print("[FAIL] %s %s" % (name, detail))


# ---- 真实库匹配 ----
db = evdb.get_event_db()
print("事件库已加载：%d 条" % len(db))

# 用几个真实存在的国服事件名（含 OCR 常见噪声）
for name in ["新年参拜", "新年的抱负", "安心～针灸师，登☆场", "团队成员终于集结完毕!"]:
    m = db.search_by_name([name], min_score=0.5)
    check("真实事件命中:%s" % name, m is not None and m.event is not None,
          "via=%s" % (getattr(m, "via", None) if m else None))
    if m:
        print("  命中[%s] -> %s (score=%.2f, choices=%d)"
              % (name, m.name, m.score, len(m.event.get("choices") or [])))

# 模糊 OCR 噪声：标点/全半角变体（OCR 丢字过多时任何模糊匹配都救不了，
# 那是上游 OCR 质量问题；这里验证「名字大体完整」时的容错）
for noisy in ["安心~针灸师，登☆场", "新年的抱负", "新年参拜。"]:
    m = db.search_by_name([noisy], min_score=0.45)
    check("噪声容错:%s -> %s" % (noisy, m.name if m else None),
          m is not None, "")


# ---- 真实选项打分 ----
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

# 命中库中一个带多种选项的真实事件并打分
m = db.search_by_name(["新年的抱负"], min_score=0.5)
if m and m.event.get("choices"):
    ev = m.event
    print("\n事件[%s] 选项打分：" % m.name)
    best = ec.pick_best_choice(ctx, ev)
    for i, c in enumerate(ev.get("choices") or [], 1):
        cs = ec.score_choice(ctx, c, i)
        print("  选项%d[%s]: %.1f分" % (i, c.get("text", ""), cs.total))
    check("pick_best_choice 返回合法序号", 1 <= best <= len(ev.get("choices") or []),
          "best=%d n=%d" % (best, len(ev.get("choices") or [])))
else:
    print("（'新年的抱负' 无选项数据，跳过打分断言）")

# 全库抽样：至少 20 个事件打分不抛异常
import random
random.seed(7)
events_with_choices = [e for e in db.events if e.get("choices")]
sample = random.sample(events_with_choices, min(20, len(events_with_choices)))
ok = True
for e in sample:
    try:
        ec.pick_best_choice(ctx, e)
    except Exception as exc:
        ok = False
        print("  打分异常[%s]: %s" % (e.get("name", ""), exc))
        break
check("20 个随机真实事件打分无异常", ok)

print("")
print("event_db 端到端：%d 项断言全过" % _PASS if not _FAIL else
      "event_db 端到端：%d/%d 通过，失败：%s" % (_PASS, _PASS + len(_FAIL), _FAIL))
sys.exit(0 if not _FAIL else 1)
