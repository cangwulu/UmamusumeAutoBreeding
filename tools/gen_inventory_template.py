# -*- coding: utf-8 -*-
"""生成「我的库存」填报模板（CSV，UTF-8-BOM，Excel 直接打开不乱码）。

一次性工具，不参与运行时。

产出目录：<项目根>/my_inventory/
    my_characters.csv     预填 139 个马娘形态，只填「拥有 / 星级 / 觉醒等级」
    my_support_cards.csv  预填 316 张协助卡（简中名 + 类型 + 稀有度），只填「拥有 / 突破数 / 等级」
    my_studs.csv          已成品种马记录（可留空；没有种马记录时规划器按「从零规划」跑）

用法：
    python tools/gen_inventory_template.py [--out DIR] [--force]
"""

import argparse
import csv
import json
import os
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from module.umamusume.card_level import (LEVEL_HEADER, AWAKEN_HEADER,
                                         RARITY_BASE_LEVEL, LEVEL_PER_AWAKEN,
                                         MAX_AWAKEN, KNOWN_RARITIES)

DATA = os.path.join(_PROJECT_ROOT, "resource", "umamusume", "data")
DEFAULT_OUT = os.path.join(_PROJECT_ROOT, "my_inventory")

CHAR_HEADERS = ["形态名", "角色名", "拥有(1/0)", "星级(1-5)", "觉醒等级(0-5)", "备注"]
# 等级上限随「稀有度 + 突破数」变化（规则见 module/umamusume/card_level.py），
# 所以表头不再写死「等级(1-50)」。老表头仍可被读取（向后兼容）。
CARD_HEADERS = ["卡名", "关联马娘", "类型", "稀有度", "拥有(1/0)",
                AWAKEN_HEADER, LEVEL_HEADER, "备注"]
STUD_HEADERS = ["种马角色名", "速度", "耐力", "力量", "根性", "智力",
                "蓝因子(如:速度3星,耐力2星)", "粉因子(如:中距离3星)",
                "白因子技能(逗号分隔)", "绿因子(继承固有)", "跑过的G1(逗号分隔)", "备注"]

STUD_SAMPLE = [
    "示例马娘", "1100", "900", "800", "500", "700",
    "耐力3星,速度2星", "中距离3星",
    "地固,弧线教授", "丸善斯基固有",
    "皋月奖,日本德比,菊花奖", "删掉本行开始填",
]


def _load(name):
    with open(os.path.join(DATA, name), encoding="utf-8") as f:
        return json.load(f)


def write_csv(path, headers, rows, force=False):
    if os.path.exists(path) and not force:
        print("[跳过] 已存在：%s（用 --force 覆盖）" % path)
        return False
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(headers)
        w.writerows(rows)
    print("[生成] %s  %d 行" % (path, len(rows)))
    return True


def gen_characters(out, force):
    data = _load("character_bwiki.json")
    chars = data["characters"]
    # 按角色名排序，同角色的形态聚在一起
    chars = sorted(chars, key=lambda c: (c.get("name") or "", c.get("card_name") or ""))
    rows = []
    for c in chars:
        card_name = c.get("card_name") or ""
        name = c.get("name") or ""
        adapt = c.get("adapt") or {}
        dist = "/".join("%s%s" % (x["item"], x["grade"])
                        for x in (adapt.get("距离适应性") or []))
        rows.append([card_name, name, "", "", "", "距离适性:%s" % dist])
    return write_csv(os.path.join(out, "my_characters.csv"),
                     CHAR_HEADERS, rows, force)


def gen_cards(out, force):
    data = _load("support_card_bwiki.json")
    cards = data["cards"]
    order = {"速度": 0, "耐力": 1, "力量": 2, "根性": 3, "智力": 4, "友人": 5, "团队": 6}
    rank = {"SSR": 0, "SR": 1, "R": 2}
    cards = sorted(cards, key=lambda c: (order.get(c.get("type"), 9),
                                         rank.get(c.get("rarity"), 9),
                                         c.get("chara") or ""))
    rows = []
    for c in cards:
        rows.append([c.get("name") or "", c.get("chara") or "",
                     c.get("type") or "", c.get("rarity") or "", "", "", "", ""])
    return write_csv(os.path.join(out, "my_support_cards.csv"),
                     CARD_HEADERS, rows, force)


def gen_studs(out, force):
    return write_csv(os.path.join(out, "my_studs.csv"),
                     STUD_HEADERS, [STUD_SAMPLE], force)


def main(argv=None):
    ap = argparse.ArgumentParser(description="生成我的库存填报模板")
    ap.add_argument("--out", default=DEFAULT_OUT, help="输出目录")
    ap.add_argument("--force", action="store_true", help="覆盖已存在文件")
    args = ap.parse_args(argv)

    out = args.out
    if not os.path.isdir(out):
        os.makedirs(out)
        print("[创建目录] %s" % out)

    gen_characters(out, args.force)
    gen_cards(out, args.force)
    gen_studs(out, args.force)
    print("\n填写说明：")
    print("  1) my_characters.csv    —— 在「拥有(1/0)」列填 1；星级/觉醒等级可选填")
    print("  2) my_support_cards.csv —— 在「拥有(1/0)」列填 1；突破数(0-4)建议填，影响配卡推荐质量")
    print("       等级上限 = 稀有度基准(%(base)s) + %(per)d × 突破数（上限随突破数涨，最高 %(max)d 级）"
          % {"base": "/".join("%s %d" % (r, RARITY_BASE_LEVEL[r]) for r in KNOWN_RARITIES),
             "per": LEVEL_PER_AWAKEN, "max": max(RARITY_BASE_LEVEL.values()) + LEVEL_PER_AWAKEN * MAX_AWAKEN})
    print("  3) my_studs.csv         —— 已成品种马记录；没有就删掉示例行留空（规划器按从零规划跑）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
