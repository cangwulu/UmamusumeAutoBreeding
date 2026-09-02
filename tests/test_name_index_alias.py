"""P4/P5 回归：事件简中名桥接 + 技能/角色重名 prefer 解析。

运行：
    python tests/test_name_index_alias.py

验证：
  P4 — chara_events 的国服简中事件名经桥接后可解析到 event 规范键
       （build_name_index.py 步骤 5b，从 55.5% 提升到 97.2%）
  P5 — 同名既作角色又作技能时（如「一往无前」= 目白莱恩称号 &
        技能 ひたむき前進 国服名），canonical(prefer=...) 按期望类型命中
"""

import importlib.util
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

_NR = os.path.join(ROOT, "module", "umamusume", "name_resolver.py")
_spec = importlib.util.spec_from_file_location("_nr", _NR)
nr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(nr)
rslv = nr.get_resolver(reload=True)

_PASS = 0
_FAIL = []


def check(name, cond, detail=""):
    global _PASS
    if cond:
        _PASS += 1
    else:
        _FAIL.append(name)
        print("[FAIL] %s %s" % (name, detail))


# ---- P4：事件简中名桥接 ----
ce_path = os.path.join(ROOT, "resource", "umamusume", "data", "chara_events.json")
ce = json.load(open(ce_path, encoding="utf-8"))
hit = miss = 0
junk = 0
MISS_SAMPLE = []
for c in ce["characters"]:
    for e in c.get("events", []):
        m = e.get("meta") or {}
        cn = (m.get("简中名") or m.get("中文名") or "").strip()
        if not cn:
            continue
        if "未实装" in cn:
            junk += 1
            continue
        key, sc = rslv.canonical(cn)
        if key and rslv.kind(key) == "event":
            hit += 1
        else:
            miss += 1
            if len(MISS_SAMPLE) < 5:
                MISS_SAMPLE.append((cn, key, round(sc, 2)))
check("P4 事件简中名命中率 ≥95%%（got %.1f%%）" % (hit / max(1, hit + miss) * 100),
      hit / max(1, hit + miss) >= 0.95,
      "hit=%d miss=%d junk=%d 样例%s" % (hit, miss, junk, MISS_SAMPLE))

# 抽样桥接名可反查
for sample in ["还早了100年！", "小革与最强使魔", "学园里传承的咒语？",
               "安心～针灸师，登☆场"]:
    key, sc = rslv.canonical(sample)
    check("P4 桥接命中:%s" % sample,
          key is not None and rslv.kind(key) == "event",
          "key=%r kind=%r" % (key, rslv.kind(key)))


# ---- P5：技能/角色重名 prefer ----
# 「一往无前」：目白莱恩(char) 与 技能ひたむき前進 共用
k_none, _ = rslv.canonical("一往无前")
check("P5 无 prefer 保持原行为(→角色)", k_none == "目白莱恩", "got %r" % k_none)
k_skill, sc = rslv.canonical("一往无前", prefer="skill")
check("P5 prefer=skill → 技能键", k_skill == "ひたむき前進"
      and rslv.kind(k_skill) == "skill", "got %r kind=%r" % (k_skill, rslv.kind(k_skill)))
k_chara, _ = rslv.canonical("一往无前", prefer="chara")
check("P5 prefer=chara → 角色键", k_chara == "目白莱恩", "got %r" % k_chara)
# 纯技能名不受 prefer 干扰
k2, _ = rslv.canonical("直线一气", prefer="skill")
check("P5 普通技能 prefer=skill 正常", k2 is not None
      and rslv.kind(k2) == "skill", "got %r" % k2)
# 纯形态名 prefer=skill 不应误配
k3, _ = rslv.canonical("无声无瑕", prefer="skill")
check("P5 形态名 prefer=skill → None(不误配)",
      k3 is None, "got %r" % k3)

print("")
print("P4/P5 回归：%d 项断言全过" % _PASS if not _FAIL else
      "P4/P5 回归：%d/%d 通过，失败：%s" % (_PASS, _PASS + len(_FAIL), _FAIL))
sys.exit(0 if not _FAIL else 1)
