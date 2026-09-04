# -*- coding: utf-8 -*-
"""生成 docs/stud_planner_example.md（演示「按形态区分技能」输出）。

用一份虚构测试库存（含多形态角色，尤其无声铃鹿两形态）跑规划器，
证明不同形态会列出不同初始技能。不触碰用户真实的 my_inventory/ 模板。
"""
import os
import sys
import tempfile
import csv
import importlib.util

from module.umamusume.card_level import LEVEL_HEADER, AWAKEN_HEADER

PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJ not in sys.path:
    sys.path.insert(0, PROJ)
EXAMPLE = os.path.join(PROJ, "docs", "stud_planner_example.md")


def _load_planner():
    spec = importlib.util.spec_from_file_location(
        "_sp_stud", os.path.join(PROJ, "module/umamusume/asset/stud_planner.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


# 虚构库存：形态名必须是 character_bwiki 里的真实全形态名，才能补全适性/成长率
OWNED_FORMS = [
    # 形态名, 角色名, 星级, 觉醒
    ("【无声无瑕】无声铃鹿", "无声铃鹿", 3, 3),
    ("【浪间翠玉】无声铃鹿", "无声铃鹿", 3, 3),
    ("【喜乐无边】东海帝王", "东海帝王", 3, 2),
    ("【飞跃地平线】东海帝王", "东海帝王", 3, 2),
    ("【Lunatic Lab】爱丽速子", "爱丽速子", 3, 4),
    ("【tach-nology】爱丽速子", "爱丽速子", 3, 4),
    ("【特别追梦者】特别周", "特别周", 3, 3),
    ("【绯红方程式】丸善斯基", "丸善斯基", 3, 2),
    ("【Maverick】成田白仁", "成田白仁", 3, 3),
    ("【皇帝】鲁道夫象征", "鲁道夫象征", 3, 3),
]

CARDS = [
    ("【独享冰凉？】东商变革", "东商变革", "速度", "SSR"),
    ("【比翼的华尔兹】东海帝王", "东海帝王", "速度", "SSR"),
    ("【静寂之夜的奇迹】无声铃鹿", "无声铃鹿", "速度", "SSR"),
    ("【知识的探求】爱丽速子", "爱丽速子", "智力", "SSR"),
    ("【大家的太阳】好歌剧", "好歌剧", "耐力", "SSR"),
]

STUDS = [
    # 种马角色名,速度,耐力,力量,根性,智力,蓝因子,粉因子,白因子技能,绿因子,跑过的G1
    ("演示种马", 1100, 900, 800, 500, 700,
     "耐力3星,速度2星", "中距离3星", "地固,弧线教授",
     "无声铃鹿固有", "皋月奖,日本德比,菊花奖"),
]


def main():
    d = tempfile.mkdtemp(prefix="inv_demo_")
    # 马娘
    p = os.path.join(d, "my_characters.csv")
    with open(p, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["形态名", "角色名", "拥有(1/0)", "星级(1-5)", "觉醒等级(0-5)", "备注"])
        for fn, nm, st, aw in OWNED_FORMS:
            w.writerow([fn, nm, 1, st, aw, ""])
    # 协助卡
    p = os.path.join(d, "my_support_cards.csv")
    with open(p, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["卡名", "关联马娘", "类型", "稀有度", "拥有(1/0)", AWAKEN_HEADER, LEVEL_HEADER, "备注"])
        for nm, ch, tp, rr in CARDS:
            w.writerow([nm, ch, tp, rr, 1, 0, 1, ""])
    # 种马
    p = os.path.join(d, "my_studs.csv")
    with open(p, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["种马角色名", "速度", "耐力", "力量", "根性", "智力",
                    "蓝因子(如:速度3星,耐力2星)", "粉因子(如:中距离3星)",
                    "白因子技能(逗号分隔)", "绿因子(继承固有)", "跑过的G1(逗号分隔)", "备注"])
        for row in STUDS:
            w.writerow(list(row) + [""])

    m = _load_planner()
    inv = m.load_inventory(d)
    print("载入马娘 %d 只 / 卡 %d 张 / 种马 %d 只" % (
        len(inv.characters), len(inv.cards), len(inv.studs)))

    track = m.Track(venue="中山", distance=2500, surface="草地",
                    direction="右", weather="晴", condition="良")
    res = m.plan(track, inv, style="差", top=10)
    report = m.render_report(res, inv)

    header = (
        "# ⚠ 这是**示例报告**（演示输出格式）\n\n"
        "生成条件：赛道 = 中山草地 2500m 长距离右回 / 晴 / 良场，跑法 = 差马。\n"
        "库存用一份**虚构测试库存**（%d 只马娘含多形态角色 + %d 张卡 + %d 只种马），只为展示输出长什么样，**推荐不代表你的账号**。\n\n"
        "想生成你自己的报告：填 my_inventory/ 下两个 CSV，然后跑：\n"
        "python module/umamusume/asset/stud_planner.py --venue 中山 --distance 2500 --track 草地 --direction 右 --weather 晴 --condition 良 --style 差\n\n"
        "引擎现已接入「按形态区分技能」：每只候选/种马都会列出其**形态专属的固有 / 觉醒 / 初始技能**，"
        "同批马的不同形态初始技能确实不同（见无声铃鹿两形态）。\n\n"
    ) % (len(inv.characters), len(inv.cards), len(inv.studs))

    with open(EXAMPLE, "w", encoding="utf-8") as f:
        f.write(header + report)
    print("示例报告已写入：%s" % EXAMPLE)


if __name__ == "__main__":
    main()
