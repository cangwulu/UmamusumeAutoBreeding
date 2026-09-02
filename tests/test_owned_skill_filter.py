"""P7 集成冒烟：cultivate._filter_owned_skills 全链路（需 uat: cv2/colorlog）。

运行（uat）：
    python tests/test_owned_skill_filter.py
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# 桩 ctx（不真正驱动模拟器）
from module.umamusume.script.cultivate_task.cultivate import _filter_owned_skills


class _Detail:
    cultivate_chara = "特别周"


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


# 1) 配置马娘 → 自带技能被剔除
out = _filter_owned_skills(ctx, [["圆弧艺术家", "流星", "一阵狂风"]])
flat = [s for g in out for s in g]
check("剔除马娘自带技能(流星)", "流星" not in flat, "out=%s" % out)
check("保留非自带技能", "圆弧艺术家" in flat, "out=%s" % out)

# 2) 未配置马娘 → 原样返回
ctx2 = _Ctx()
ctx2.cultivate_detail.cultivate_chara = ""
out2 = _filter_owned_skills(ctx2, [["圆弧艺术家", "流星"]])
check("未配置马娘原样返回", len(out2) == 1 and len(out2[0]) == 2, "out=%s" % out2)

# 3) 全被剔光 → 维持原列表（防误伤）
ctx3 = _Ctx()
ctx3.cultivate_detail.cultivate_chara = "特别周"
out3 = _filter_owned_skills(ctx3, [["流星"]])
check("全被剔光维持原列表", len(out3) == 1 and out3[0] == ["流星"], "out=%s" % out3)

# 4) 多组过滤
out4 = _filter_owned_skills(ctx, [["圆弧艺术家"], ["流星", "专注力"]])
flat4 = [s for g in out4 for s in g]
check("多组过滤(保留有值组)", "圆弧艺术家" in flat4 and "专注力" in flat4
      and "流星" not in flat4, "out=%s" % out4)

print("")
print("P7 过滤集成：%d 项断言全过" % _PASS if not _FAIL else
      "P7 过滤集成：%d/%d 通过，失败：%s" % (_PASS, _PASS + len(_FAIL), _FAIL))
sys.exit(0 if not _FAIL else 1)
