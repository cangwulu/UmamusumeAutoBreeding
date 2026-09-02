"""manifest.get_event_choice 集成冒烟（需 uat 环境: colorlog/cv2）。

运行（uat）:
    python tests/test_event_choice_manifest.py
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from module.umamusume.script.cultivate_task.event import manifest


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
    turn_operation = None  # scenario_event 会读 .turn_operation_type

    def __init__(self):
        self.turn_operation = None


class _Detail:
    def __init__(self):
        self.expect_attribute = [1200, 900, 800, 600, 700]
        self.turn_info = _Turn()
        self.learn_skill_list = [["直線加速"]]
        self.learn_skill_blacklist = []


class _Ctx:
    cultivate_detail = _Detail()


ctx = _Ctx()

_PASS = 0
_FAIL = []


def check(name, cond, detail=""):
    global _PASS
    if cond:
        _PASS += 1
    else:
        _FAIL.append(name)
        print("[FAIL] %s %s" % (name, detail))


# 1) 硬编码事件优先：新年的抱负（固定返回 int 或 callable 结果 2/3）
r = manifest.get_event_choice(ctx, "新年的抱负")
check("硬编码'新年的抱负' → 2或3", r in (2, 3), "got %r" % r)

# 2) 库命中但不在硬编码表 → 智能打分
#    选一个 event_db 内确定存在且带选项的事件（避开硬编码 6 个）
#    先探测可用名：取库内第一个含选项、非硬编码表内的事件名
import importlib.util
_asset = os.path.join(ROOT, "module", "umamusume", "asset", "event_db.py")
_spec = importlib.util.spec_from_file_location("_mfe", _asset)
_mfe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mfe)
_db = _mfe.get_event_db()
_hard = {"安心～针灸师，登☆场", "新年的抱负", "新年参拜", "新年祈福",
         "新手教程", "团队成员终于集结完毕!"}
_probe = None
for _e in _db.events:
    if _e.get("name") not in _hard and _e.get("choices"):
        _probe = _e
        break
if _probe is None:
    print("SKIP: 事件库无可用探测事件")
else:
    pname = _probe["name"]
    r2 = manifest.get_event_choice(ctx, pname)
    n = len(_probe.get("choices") or [])
    check("库命中智能打分:%s -> 1..%d" % (pname, n), 1 <= r2 <= n,
          "got %r (choices=%d)" % (r2, n))

# 3) 完全未知 → 默认 1（不抛异常）
r4 = manifest.get_event_choice(ctx, "完全不存在的虚构事件XYZ")
check("未知事件 → 默认1", r4 == 1, "got %r" % r4)

print("")
print("manifest 集成：%d 项断言全过" % _PASS if not _FAIL else
      "manifest 集成：%d/%d 通过，失败：%s" % (_PASS, _PASS + len(_FAIL), _FAIL))
sys.exit(0 if not _FAIL else 1)
