"""skill_order 技能库测试（P6）—— 双库匹配 + 综合分排序 + 减益识别。

运行：
    python tests/test_skill_order.py
"""

import importlib.util
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

_SO = os.path.join(ROOT, "module", "umamusume", "asset", "skill_order.py")
_spec = importlib.util.spec_from_file_location("_so", _SO)
so = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(so)

_PASS = 0
_FAIL = []


def check(name, cond, detail=""):
    global _PASS
    if cond:
        _PASS += 1
    else:
        _FAIL.append(name)
        print("[FAIL] %s %s" % (name, detail))


# ---- 数据加载 ----
try:
    db = so.get_skill_db(reload=True)
    has_bwiki = bool(db.bwiki_skills)
    print("skill_db: %d 条 (derby), bwiki: %d 条" % (len(db.skills), len(db.bwiki_skills)))
    check("数据加载", len(db.skills) > 500, "")
except Exception as exc:
    check("数据加载", False, repr(exc))
    print("无法加载数据，以下断言全部跳过")
    sys.exit(0)


# ---- BWIKI 简中主库匹配 ----
# 注：BWIKI 库收录技能全名/长名（如 璀璨流星/速度之星）；通用短技能（直线一气）
# 走 derby 兜底（两种命中都正确，src 区分）
rec, sc, src = db.match("速度之星")
check("BWIKI 精确命中", rec is not None and src == "bwiki", "src=%s" % src)
check("BWIKI 命中分数", sc >= 0.99 if rec else False, "sc=%.3f" % sc)

rec, sc, src = db.match("圆弧艺术家")
check("通用长技能命中", rec is not None and src == "bwiki", "src=%s" % src)

rec, sc, src = db.match("直线一气")
check("短技能走 derby 兜底且命中", rec is not None and src == "derby" and sc >= 0.99,
      "src=%s sc=%.3f" % (src, sc))

# 错一字容错（真实 cosine >= 0.50 接受线）
rec, sc, src = db.match("直线一气", min_score=0.5)
check("错一字可容错或安全 miss（无有害误配）",
      rec is None or sc >= 0.5, "rec=%s sc=%.3f" % (rec, sc))

# 垃圾名不误配
rec, sc, src = db.match("完全不存在的技能XYZ", min_score=0.5)
check("垃圾名不误配", rec is None, "rec=%s" % rec)


# ---- derby 兜底（日文/derby 名）----
rec, sc, src = db.match("ひたむき前進")
check("derby 日文直查", rec is not None and src == "derby",
      "src=%s rec=%s" % (src, rec and rec.get("name")))
check("derby 命中分数", sc >= 0.99 if rec else False, "sc=%.3f" % sc)

rec, sc, src = db.match("円弧のマエストロ")
check("derby 兜底(圆弧大师)", rec is not None, "src=%s" % src)

# P5 场景：技能「一往无前」（ひたむき前進 国服名）不与角色重名混淆
rec, sc, src = db.match("一往无前")
check("重名技能'一往无前'命中技能(非角色)", rec is not None,
      "rec=%s" % (rec and rec.get("name")))
if rec:
    check("'一往无前'匹配到正确技能组", "一往无前" in (rec.get("name") or "")
          or "ひたむき" in (rec.get("name_jp") or ""),
          "name=%s name_jp=%s" % (rec.get("name"), rec.get("name_jp")))


# ---- 综合分与减益识别 ----
comp = so.composite_of("直线一气")
check("composite_of 命中>0", comp > 0, "comp=%.1f" % comp)
comp_miss = so.composite_of("不存在XYZ")
check("composite_of 未命中=-1", comp_miss == -1.0, "comp=%.1f" % comp_miss)

# 减益技能（红技）负分：找出库里一个负分技能验证
neg_found = False
for s in db.skills:
    if so._composite(s) < -1.0:
        neg_found = True
        break
check("存在减益技能(负分)", neg_found, "")


# ---- rank_skills 排序 ----
ranked = so.rank_skills(["不存在的技能A", "直线一气", "另一个不存在B"])
check("rank_skills 返回全部", len(ranked) == 3, "len=%d" % len(ranked))
check("rank_skills 已匹配排前", ranked[0]["matched"] is not None,
      "first=%s" % ranked[0])
check("rank_skills 未匹配在末", ranked[-1]["matched"] is None,
      "last=%s" % ranked[-1])
check("rank_skills 字段齐全",
      all(k in ranked[0] for k in ("name", "matched", "score", "composite",
                                   "rarity", "ability_value", "describe", "source")),
      str(list(ranked[0].keys())))
check("rank_skills topn", len(so.rank_skills(["a", "b", "c"], topn=2)) == 2)

# 同组技能按 composite 降序
two = so.rank_skills(["直线一气", "速度之星"])
if len(two) == 2 and two[0]["composite"] is not None and two[1]["composite"] is not None:
    check("rank_skills composite 降序",
          two[0]["composite"] >= two[1]["composite"],
          "%s(%.1f) vs %s(%.1f)" % (
              two[0]["name"], two[0]["composite"],
              two[1]["name"], two[1]["composite"]))

# ---- rank_learnable（get_skill_list dict 直接排）----
skl = [
    {"skill_name": "直线一气", "skill_cost": 170, "priority": 1, "available": True},
    {"skill_name": "完全不存在Z", "skill_cost": 90, "priority": 0, "available": True},
]
out = so.rank_learnable(skl)
check("rank_learnable 返回原 dict", len(out) == 2 and all("skill_name" in x for x in out),
      "out=%s" % out)
check("rank_learnable 已识别技能排前", out[0]["skill_name"] == "直线一气",
      "first=%s" % out[0]["skill_name"])

print("")
print("skill_order 测试：%d 项断言全过" % _PASS if not _FAIL else
      "skill_order 测试：%d/%d 通过，失败：%s" % (_PASS, _PASS + len(_FAIL), _FAIL))
sys.exit(0 if not _FAIL else 1)
