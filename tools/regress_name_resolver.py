# -*- coding: utf-8 -*-
"""name_resolver + 3 个试点模块的回归测试。

通过 importlib 加载 asset/ 下模块（绕开 asset/__init__.py 的 cv2 依赖），
对已知案例断言解析结果。全部通过则退出码 0，否则非 0。

核心语义：BWIKI 中文形态名与 pretty-derby 中文形态名可能不同，但它们指向同一
个日文形态规范键（form key）。chara_skills 的 card_jp 正是这个键。因此：
  - 无声无邪(derby) 与 无声无瑕(BWIKI) 共享 form key サイレントイノセンス
    => 两者都命中 chara_skills 的「无声无邪」卡，这是正确的（同一形态）。
  - 真正的「多形态不同技能」对比应取 derby 里不同的 form key（如
    无声无邪 vs 波浪间的绿宝石）。
"""
import os
import sys
import importlib.util

PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJ not in sys.path:
    sys.path.insert(0, PROJ)


def _load(mod_path, mod_name):
    spec = importlib.util.spec_from_file_location(mod_name, mod_path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


cs = _load(os.path.join(PROJ, "module/umamusume/asset/chara_skills.py"), "_cs")
so = _load(os.path.join(PROJ, "module/umamusume/asset/skill_order.py"), "_so")
sp = _load(os.path.join(PROJ, "module/umamusume/asset/stud_planner.py"), "_sp")
from module.umamusume.name_resolver import get_resolver

r = get_resolver()
failures = []


def check(label, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    print("[%s] %s%s" % (status, label, (" :: " + detail) if detail else ""))
    if not cond:
        failures.append(label)


# ---------- 试点1：chara_skills ----------
# (surface, expect_card_name)  expect_card_name=None 表示角色级（无卡）
cases_chara = [
    ("无声无邪", "无声无邪"),            # derby 短名 -> 形态卡
    ("无声无瑕", "无声无邪"),            # BWIKI 名 -> 同一 form key -> 无声无邪 卡（正确）
    ("【无声无瑕】无声铃鹿", "无声无邪"),  # BWIKI 全形态名 -> 无声无邪 卡
    ("浪间翠玉", "波浪间的绿宝石"),
    ("波浪间的绿宝石", "波浪间的绿宝石"),
    ("无声铃鹿", None),                 # 角色级 -> 无卡
]
for surface, expect_card in cases_chara:
    rec, matched, score, card = cs.get_db().match(surface)
    got_card = card.get("card_name") if card else None
    ok = rec is not None and (got_card == expect_card)
    check("chara_skills.match(%s) -> card=%s (got=%s)" % (surface, expect_card, got_card),
          ok, "score=%.2f" % score)

# ---------- 试点2：skill_order ----------
db_so = so.get_skill_db()
bwiki_name = "直线恢复"
rec, real, src = db_so.match(bwiki_name)
check("skill_order.match(%s) source=bwiki" % bwiki_name,
      rec is not None and src == "bwiki", "src=%s" % src)

# derby 兜底：取一个在 derby 表里的日文技能名，经 resolver 命中 derby
derby_smoke = next((s["name_jp"] for s in db_so.skills if s.get("name_jp")), None)
if derby_smoke:
    rec, real, src = db_so.match(derby_smoke)
    check("skill_order.match(%s) 经 resolver 命中" % derby_smoke,
          rec is not None, "src=%s" % src)

# ---------- 试点3：stud_planner 形态解析 ----------
class _C:
    def __init__(self, name, card_name):
        self.name = name
        self.card_name = card_name


# (chara, full_bwiki_form) -> 期望命中的 form key（resolver 的 form 键）
forms_sp = [
    ("无声铃鹿", "【无声无瑕】无声铃鹿", "サイレントイノセンス"),
    ("无声铃鹿", "【浪间翠玉】无声铃鹿", "波間のエメラルド"),
    ("爱丽速子", "【Lunatic Lab】爱丽速子", "Lunatic Lab"),
    ("爱丽速子", "【tach-nology】爱丽速子", "tach-nology"),
    ("丸善斯基", "【绯红方程式】丸善斯基", "フォーミュラオブルージュ"),
    ("丸善斯基", "【飞跃☆夏夜】丸善斯基", "ぶっとび☆さまーナイト"),
]
for chara_name, full, expect_key in forms_sp:
    c = _C(chara_name, full)
    card = sp._resolve_form_card(c)
    got = card.get("card_jp") if card else None
    ok = card is not None and got == expect_key
    check("stud_planner._resolve_form_card(%s) -> card_jp=%s (got=%s)"
          % (full, expect_key, got), ok)

# 同角色两形态初始技能应不同（取 derby 里两个不同 form）
c1 = _C("无声铃鹿", "【无声无瑕】无声铃鹿")   # -> 无声无邪 形态
c2 = _C("无声铃鹿", "【浪间翠玉】无声铃鹿")    # -> 波浪间的绿宝石 形态
fs1 = sp.form_skills(c1).get("initial") or []
fs2 = sp.form_skills(c2).get("initial") or []
check("stud_planner 无声铃鹿两形态初始技能不同 (f1=%d f2=%d)" % (len(fs1), len(fs2)),
      fs1 != fs2)

# ---------- resolver 直接用例 ----------
resolver_cases = [
    ("无声无邪", "サイレントイノセンス"),
    ("无声无瑕", "サイレントイノセンス"),
    ("【无声无瑕】无声铃鹿", "サイレントイノセンス"),
    ("无声铃鹿", "サイレンススズカ"),
    ("サイレントイノセンス", "サイレントイノセンス"),
    ("#LookatCurren", "#LookatCurren"),
]
for surf, expect in resolver_cases:
    k, s = r.canonical(surf)
    check("resolver.canonical(%s)=%s (got=%s,%.2f)" % (surf, expect, k, s),
          k == expect, "score=%.2f" % s)

# ---------- event / race 覆盖（扩展后）----------
resolver_event_race = [
    ("#Curren找到了", "#Currenみつけた", "event"),
    ("新年参拜", "初詣", "event"),
    ("团队成员终于集结完毕!", "ついに集まったチームメンバー！", "event"),
    ("二月锦标赛", "フェブラリーステークス", "race"),
    ("皋月奖", "皐月賞", "race"),
    ("菊花奖", "菊花賞", "race"),
]
for surf, expect, kind in resolver_event_race:
    k, s = r.canonical(surf)
    ok = (k == expect) and (r.kind(k) == kind)
    check("resolver.canonical(%s)=%s/%s (got=%s/%s,%.2f)" % (surf, expect, kind, k, r.kind(k), s),
          ok, "score=%.2f" % s)

if failures:
    print("\nFAILED: %d" % len(failures))
    for f in failures:
        print("  - " + f)
    sys.exit(1)
else:
    print("\nALL PASS (%d checks)" % (
        len(cases_chara) + 2 + len(forms_sp) + 1 + len(resolver_cases)))
